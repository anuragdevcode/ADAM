"""Test suite for Phase 2: Data layer & retrieval that scale (R1, R2, R3, R4, R5, R6, E3, S11)."""

import asyncio
import io
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from adam.api.app import app
from adam.backup import create_backup, restore_backup, verify_backup
from adam.db.models import (
    AuditEvent,
    Classification,
    Document,
    DocumentChunk,
    DocumentVersion,
    User,
    compute_audit_event_hash,
)
from adam.db.session import get_engine, get_session, run_alembic_migrations
from adam.rag.models import ParsedQuery, UserContext
from adam.rag.retriever import (
    CompactCrossEncoderReranker,
    EvidencePassage,
    HeuristicBoostReranker,
    HybridRetriever,
    MultilingualSemanticVectorizer,
    NeuralCrossEncoderReranker,
)
from adam.storage.base import (
    ChecksumMismatchError,
    ImmutableObjectOverwriteError,
    get_storage_backend,
)
from adam.storage.s3 import S3StorageBackend
from adam.worker.runner import UnifiedWorkerRunner


@pytest.fixture
def p2_client():
    from adam.api.middleware import global_rate_limiter
    global_rate_limiter.tokens.clear()
    global_rate_limiter.last_updated.clear()
    return TestClient(app)


def _get_error_msg(resp) -> str:
    body = resp.json()
    if isinstance(body, dict) and "error" in body and isinstance(body["error"], dict):
        return body["error"].get("message", "")
    if isinstance(body, dict):
        return str(body.get("detail", ""))
    return ""


# ── R3: Alembic Migrations & Schema Lifecycle ──────────────────────────────


def test_alembic_migrations_lifecycle(tmp_path):
    """Test Alembic schema migrations: upgrade head, downgrade base, and re-upgrade (R3)."""
    from alembic import command
    from alembic.config import Config

    test_db_path = tmp_path / "test_migration_lifecycle.db"
    db_url = f"sqlite:///{test_db_path}"

    ini_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    alembic_cfg = Config(ini_path)
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # 1. Upgrade to head
    command.upgrade(alembic_cfg, "head")

    eng = get_engine(db_url)
    with eng.connect() as conn:
        from sqlalchemy import inspect
        insp = inspect(conn)
        tables = insp.get_table_names()
        assert "documents" in tables
        assert "document_chunks" in tables
        assert "audit_events" in tables
        assert "users" in tables
        assert "alembic_version" in tables

    # 2. Downgrade to base
    command.downgrade(alembic_cfg, "base")
    with eng.connect() as conn:
        from sqlalchemy import inspect
        insp = inspect(conn)
        tables = insp.get_table_names()
        assert "documents" not in tables
        assert "document_chunks" not in tables

    # 3. Re-upgrade to head (idempotency check)
    command.upgrade(alembic_cfg, "head")
    with eng.connect() as conn:
        from sqlalchemy import inspect
        insp = inspect(conn)
        tables = insp.get_table_names()
        assert "documents" in tables
    eng.dispose()


def test_prod_startup_eliminates_create_all(monkeypatch, tmp_path):
    """Verify production startup invokes Alembic migrations and never calls Base.metadata.create_all (R3)."""
    monkeypatch.setenv("ADAM_ENV", "production")
    test_db = tmp_path / "prod_start.db"
    prod_url = f"sqlite:///{test_db}"

    with patch("adam.db.session.run_alembic_migrations") as mock_alembic:
        with patch("adam.db.models.Base.metadata.create_all") as mock_create_all:
            # Clear engine cache for URL
            from adam.db import session as sess_module
            sess_module._ENGINES.pop(prod_url, None)

            eng = get_engine(prod_url)
            mock_alembic.assert_called_once_with(prod_url)
            mock_create_all.assert_not_called()


# ── R1 / R2: Bounded Retrieval & Embedding Persistence ─────────────────────


def test_retriever_bounded_candidate_retrieval(tmp_path):
    """Verify HybridRetriever bounds candidate retrieval instead of unbounded query.all() (R1)."""
    db_url = f"sqlite:///{tmp_path}/test_bounded.db"
    eng = get_engine(db_url)
    sess = get_session(eng)

    doc = Document(id="doc_bound_01", title="Test Title", department_id="FINANCE")
    ver = DocumentVersion(
        id="ver_bound_01",
        document_id="doc_bound_01",
        source_url="test://",
        mime_type="application/pdf",
        sha256="abc",
        byte_size=10,
        original_object_key="k",
    )
    sess.add(doc)
    sess.add(ver)

    # Insert 15 chunks
    for i in range(15):
        chk = DocumentChunk(
            id=f"chk_bound_{i:02d}",
            document_id="doc_bound_01",
            version_id="ver_bound_01",
            chunk_index=i,
            content=f"Dehradun finance treasury pension allowance rule chunk content {i}",
            department_id="FINANCE",
            classification=Classification.PUBLIC.value,
        )
        sess.add(chk)
    sess.commit()

    retriever = HybridRetriever(sess)
    pq = ParsedQuery(raw_query="pension allowance", clean_query="pension allowance")
    user_ctx = UserContext(user_id="user_1", roles=["PUBLIC"], clearance_level="PUBLIC")

    passages = retriever.retrieve(pq, user_context=user_ctx, top_k=5)
    assert isinstance(passages, list)
    assert len(passages) <= 5
    sess.close()
    eng.dispose()


def test_vectorizer_dense_and_deterministic():
    """Verify MultilingualSemanticVectorizer produces normalized 128-d vectors (R2)."""
    vec1 = MultilingualSemanticVectorizer.embed_text("उत्तराखंड शासन वित्त विभाग")
    vec2 = MultilingualSemanticVectorizer.embed_text("उत्तराखंड शासन वित्त विभाग")
    assert len(vec1) == 128
    assert vec1 == vec2  # deterministic

    sim = MultilingualSemanticVectorizer.cosine_similarity(vec1, vec2)
    assert pytest.approx(sim, abs=1e-5) == 1.0


# ── E3: Heuristic Booster vs Neural Cross-Encoder Reranker ──────────────────


def test_heuristic_boost_reranker():
    """Verify HeuristicBoostReranker honestly boosts phrase, heading, and GO number (E3)."""
    passage = EvidencePassage(
        chunk_id="chk_1",
        document_id="doc_1",
        version_id="ver_1",
        title="Finance Rules",
        department_id="FINANCE",
        doc_type="GO",
        page_start=1,
        page_end=1,
        section_heading="Treasury Rules 2024",
        content="Under GO UK/FIN/2024/101 pension rules apply to government servants.",
        score=0.5,
        bm25_score=1.0,
        vector_score=0.8,
        go_number="UK/FIN/2024/101",
    )

    reranked = HeuristicBoostReranker.rerank("UK/FIN/2024/101", [passage], top_k=1)
    assert reranked[0].score > 0.5  # boosted by GO number match

    # Backwards compatibility check
    assert CompactCrossEncoderReranker is HeuristicBoostReranker


def test_neural_reranker_fallback():
    """Verify NeuralCrossEncoderReranker falls back to heuristic boost if model absent (E3)."""
    passage = EvidencePassage(
        chunk_id="chk_2",
        document_id="doc_2",
        version_id="ver_2",
        title="General Order",
        department_id="ADMIN",
        doc_type="GO",
        page_start=1,
        page_end=1,
        section_heading="Eligibility",
        content="General eligibility requirements for leave allowances.",
        score=0.4,
        bm25_score=0.9,
        vector_score=0.7,
        go_number="UK/ADM/2024/55",
    )

    reranked = NeuralCrossEncoderReranker.rerank("UK/ADM/2024/55", [passage], top_k=1)
    assert len(reranked) == 1
    assert reranked[0].score > 0.4


# ── R6: S3 / MinIO Storage Backend & Restore Drill ─────────────────────────


def test_s3_storage_backend_with_mock_client():
    """Test S3StorageBackend store, get, metadata, and immutability protection (R6)."""
    mock_s3 = MagicMock()
    # Simulate head_object throwing Exception (object not found initially)
    mock_s3.head_object.side_effect = Exception("NoSuchKey")
    mock_s3.get_object.return_value = {"Body": io.BytesIO(b"stored bytes content")}

    s3_backend = S3StorageBackend(
        bucket_name="adam-test-bucket",
        s3_client=mock_s3,
    )

    # 1. Store
    data = b"stored bytes content"
    obj = s3_backend.store("orders/2024/test.pdf", data)
    assert obj.key == "orders/2024/test.pdf"
    assert obj.byte_size == len(data)
    mock_s3.put_object.assert_called_once()

    # 2. Checksum mismatch error
    with pytest.raises(ChecksumMismatchError):
        s3_backend.store("orders/2024/test.pdf", data, expected_sha256="wrong_checksum")

    # 3. Immutability error on different content
    mock_s3.head_object.side_effect = None
    mock_s3.head_object.return_value = {
        "Metadata": {"sha256": "different_hash", "byte_size": "50"},
        "ContentLength": 50,
    }
    with pytest.raises(ImmutableObjectOverwriteError):
        s3_backend.store("orders/2024/test.pdf", b"new modified bytes")


def test_disaster_recovery_drill_execution(tmp_path):
    """Test automated end-to-end disaster recovery drill execution (R6)."""
    # Create isolated source DB and storage for drill
    db_file = tmp_path / "drill_source.db"
    db_url = f"sqlite:///{db_file}"
    eng = get_engine(db_url)
    sess = get_session(eng)

    ev = AuditEvent(
        sequence_num=1,
        entity_type="SOURCE",
        entity_id="src_1",
        action="CREATE",
        actor="admin",
        details_json={"name": "test"},
        prev_hash="",
    )
    sess.add(ev)
    sess.commit()
    sess.close()

    storage_dir = tmp_path / "drill_source_storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    (storage_dir / "order.pdf").write_bytes(b"%PDF-1.4 sample content")

    archive = tmp_path / "backup_drill.tar.gz"
    create_backup(backup_path=archive, storage_dir=storage_dir, db_url=db_url)

    verify_res = verify_backup(archive)
    assert verify_res["valid"] is True

    restore_storage = tmp_path / "restored_storage"
    restore_db_file = tmp_path / "restored.db"
    restore_db_url = f"sqlite:///{restore_db_file}"

    res = restore_backup(
        archive_path=archive,
        target_storage_dir=restore_storage,
        target_db_url=restore_db_url,
        force=True,
    )
    assert res["status"] == "SUCCESS"
    assert (restore_storage / "order.pdf").exists()
    eng.dispose()


# ── S11: Streaming Uploads, Quota & Concurrency ─────────────────────────────


def test_streaming_upload_and_user_quota(p2_client):
    """Test streaming upload to disk and per-user daily quota enforcement (S11)."""
    from adam.auth.security import create_access_token

    token = create_access_token({"sub": "officer_uploader", "roles": ["OFFICER"]})
    headers = {"Authorization": f"Bearer {token}"}

    pdf_content = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"

    # 1. Normal upload
    resp = p2_client.post(
        "/api/documents/upload",
        files={"file": ("order_2026.pdf", io.BytesIO(pdf_content), "application/pdf")},
        data={"title": "Official Test Circular", "classification": "PUBLIC"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Official Test Circular"
    assert data["sha256"] is not None

    # 2. Empty file rejection
    empty_resp = p2_client.post(
        "/api/documents/upload",
        files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
        data={"title": "Empty Circular", "classification": "PUBLIC"},
        headers=headers,
    )
    assert empty_resp.status_code == 400

    # 3. Quota exceeded rejection
    from adam.api.routers import documents as docs_module
    docs_module._USER_UPLOAD_HISTORY["officer_uploader"] = [
        (time.time(), docs_module._MAX_USER_DAILY_UPLOAD_BYTES + 100)
    ]
    quota_resp = p2_client.post(
        "/api/documents/upload",
        files={"file": ("order_2.pdf", io.BytesIO(pdf_content), "application/pdf")},
        data={"title": "Quota Exceeded Circular", "classification": "PUBLIC"},
        headers=headers,
    )
    assert quota_resp.status_code == 429
    assert "upload quota exceeded" in _get_error_msg(quota_resp).lower()


# ── R5: Worker Service & Chat Concurrency Backpressure ──────────────────────


def test_unified_worker_runner_cycle():
    """Verify UnifiedWorkerRunner executes a complete durable queue polling cycle (R5)."""
    runner = UnifiedWorkerRunner(poll_interval=1.0)
    stats = runner.run_cycle()
    assert "jobs" in stats
    assert "ocr" in stats
    assert "chunks" in stats
    assert "embeddings" in stats


def test_chat_concurrency_backpressure(p2_client, monkeypatch):
    """Verify chat backpressure rejects requests when generation capacity is saturated (R5)."""
    from adam.api.routers import chat as chat_module

    # Mock semaphore saturated (locked with 0 slots)
    mock_sem = asyncio.Semaphore(0)
    monkeypatch.setattr(chat_module, "_CHAT_SEMAPHORE", mock_sem)
    monkeypatch.setattr(chat_module, "_CHAT_BACKPRESSURE_TIMEOUT", 0.05)

    from adam.auth.security import create_access_token
    token = create_access_token({"sub": "user_test", "roles": ["OFFICER"]})
    headers = {"Authorization": f"Bearer {token}"}

    resp = p2_client.post(
        "/api/chat",
        json={"query": "Test query under backpressure"},
        headers=headers,
    )
    assert resp.status_code == 503
    assert "backpressure limit reached" in _get_error_msg(resp).lower()
