"""Tests for IngestionControlPlane: lifecycle states, deduplication, retry, and checkpointing."""

import time
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from adam.db.models import Base, Source, Document, DocumentVersion, IngestionJob, IngestionJobItem
from adam.db.migrations import apply_ingestion_migrations
from adam.ingest.control_plane import IngestionControlPlane
from adam.vocabularies import SourceStatus, Classification, DepartmentId


@pytest.fixture
def cp_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    apply_ingestion_migrations(engine)
    return engine


@pytest.fixture
def cp_session_factory(cp_engine):
    return sessionmaker(bind=cp_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def test_control_plane(cp_session_factory, tmp_storage, monkeypatch):
    """Fixture providing a fresh IngestionControlPlane instance with thread-safe db sessions."""
    monkeypatch.setattr("adam.ingest.control_plane.get_session", cp_session_factory)
    monkeypatch.setattr("adam.ingest.control_plane.get_storage_backend", lambda: tmp_storage)
    return IngestionControlPlane(max_workers=2)


def test_control_plane_full_lifecycle_and_deduplication(cp_session_factory, test_control_plane):
    db = cp_session_factory()

    # 1. Onboard approved source
    src = Source(
        id="src_cp_test_01",
        name="Control Plane Test Source",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        owner_name="Audit Officer",
        owner_contact="officer@uk.gov.in",
        written_authority_ref="AUTH-CP-01",
        source_type="FILE_UPLOAD",
        status=SourceStatus.APPROVED.value,
    )
    db.add(src)
    db.commit()

    # Valid PDF bytes
    pdf_1 = b"%PDF-1.4\n1 0 obj\n<< /Title (Order 1) >>\nendobj\ntrailer\n<<>>\n%%EOF"
    pdf_2 = b"%PDF-1.4\n1 0 obj\n<< /Title (Order 2) >>\nendobj\ntrailer\n<<>>\n%%EOF"

    # 2. Run Job 1 with 2 files
    job1 = test_control_plane.start_job(
        source_id="src_cp_test_01",
        job_type="FULL",
        files=[("order_1.pdf", pdf_1), ("order_2.pdf", pdf_2)],
    )

    # Wait for completion (max 5s)
    for _ in range(50):
        db.expire_all()
        j = db.query(IngestionJob).filter(IngestionJob.id == job1.id).first()
        if j and j.status in ("COMPLETED", "FAILED"):
            break
        time.sleep(0.1)

    db.expire_all()
    j1 = db.query(IngestionJob).filter(IngestionJob.id == job1.id).first()
    assert j1.status == "COMPLETED"
    assert j1.count_found == 2
    assert j1.count_ingested == 2
    assert j1.count_skipped == 0
    assert j1.count_failed == 0

    # Verify IngestionJobItem records exist in DB
    items = db.query(IngestionJobItem).filter(IngestionJobItem.job_id == job1.id).all()
    assert len(items) == 2
    assert all(it.status == "SUCCESS" for it in items)

    # Verify documents created
    docs = db.query(Document).filter(Document.source_id == "src_cp_test_01").all()
    assert len(docs) == 2

    # 3. Run Job 2 with identical files -> Deduplication must mark all as SKIPPED
    job2 = test_control_plane.start_job(
        source_id="src_cp_test_01",
        job_type="FULL",
        files=[("order_1.pdf", pdf_1), ("order_2.pdf", pdf_2)],
    )

    for _ in range(50):
        db.expire_all()
        j = db.query(IngestionJob).filter(IngestionJob.id == job2.id).first()
        if j and j.status in ("COMPLETED", "FAILED"):
            break
        time.sleep(0.1)

    db.expire_all()
    j2 = db.query(IngestionJob).filter(IngestionJob.id == job2.id).first()
    assert j2.status == "COMPLETED"
    assert j2.count_found == 2
    assert j2.count_ingested == 0
    assert j2.count_skipped == 2
    assert j2.count_failed == 0

    # Documents count remained 2 (no duplicates!)
    docs_after = db.query(Document).filter(Document.source_id == "src_cp_test_01").all()
    assert len(docs_after) == 2
    db.close()


def test_control_plane_failure_isolation_and_retry(cp_session_factory, test_control_plane):
    db = cp_session_factory()
    src = Source(
        id="src_cp_test_retry",
        name="Control Plane Retry Source",
        department_id=DepartmentId.GENERAL_ADMINISTRATION.value,
        owner_name="Admin Officer",
        owner_contact="admin@uk.gov.in",
        written_authority_ref="AUTH-CP-02",
        source_type="FILE_UPLOAD",
        status=SourceStatus.APPROVED.value,
    )
    db.add(src)
    db.commit()

    good_pdf = b"%PDF-1.4\n1 0 obj\n<< /Title (Valid Directive) >>\nendobj\ntrailer\n<<>>\n%%EOF"
    bad_file = b"MZ\x90\x00\x03\x00MALICIOUS_EXECUTABLE"  # fails content validator

    job1 = test_control_plane.start_job(
        source_id="src_cp_test_retry",
        job_type="FULL",
        files=[("good_directive.pdf", good_pdf), ("corrupt_file.pdf", bad_file)],
    )

    for _ in range(50):
        db.expire_all()
        j = db.query(IngestionJob).filter(IngestionJob.id == job1.id).first()
        if j and j.status in ("PARTIAL_SUCCESS", "COMPLETED", "FAILED"):
            break
        time.sleep(0.1)

    db.expire_all()
    j1 = db.query(IngestionJob).filter(IngestionJob.id == job1.id).first()
    assert j1.status == "PARTIAL_SUCCESS"
    assert j1.count_ingested == 1
    assert j1.count_failed == 1

    # Check IngestionJobItem records
    failed_items = (
        db.query(IngestionJobItem)
        .filter(IngestionJobItem.job_id == job1.id, IngestionJobItem.status == "FAILED")
        .all()
    )
    assert len(failed_items) == 1
    assert "corrupt_file.pdf" in failed_items[0].item_key
    assert failed_items[0].retry_count == 1

    # Now test Retry Failed Items!
    retry_job = test_control_plane.retry_job(job1.id)
    assert retry_job.job_type == "RETRY"
    assert retry_job.parent_job_id == job1.id
    assert retry_job.count_found == 1
    db.close()


def test_control_plane_stop_cancellation(cp_session_factory, test_control_plane):
    db = cp_session_factory()
    src = Source(
        id="src_cp_test_stop",
        name="Control Plane Stop Source",
        department_id=DepartmentId.RURAL_DEVELOPMENT.value,
        owner_name="Rural Officer",
        owner_contact="rural@uk.gov.in",
        written_authority_ref="AUTH-CP-03",
        source_type="FILE_UPLOAD",
        status=SourceStatus.APPROVED.value,
    )
    db.add(src)
    db.commit()

    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<< /Title (Order) >>\nendobj\ntrailer\n<<>>\n%%EOF"
    files = [(f"doc_{i}.pdf", pdf_bytes) for i in range(10)]

    job = test_control_plane.start_job(
        source_id="src_cp_test_stop",
        job_type="FULL",
        files=files,
    )

    # Immediately request stop
    time.sleep(0.02)
    stopped_job = test_control_plane.stop_job(job.id)
    assert stopped_job.status in ("CANCELLING", "CANCELLED")

    for _ in range(50):
        db.expire_all()
        j = db.query(IngestionJob).filter(IngestionJob.id == job.id).first()
        if j and j.status == "CANCELLED":
            break
        time.sleep(0.05)

    db.expire_all()
    final_j = db.query(IngestionJob).filter(IngestionJob.id == job.id).first()
    assert final_j.status == "CANCELLED"
    db.close()

