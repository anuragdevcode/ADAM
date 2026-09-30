"""Tests for ADAM API extensions (models, vocabularies, documents, precedents, sources, audit, review, preferences)."""

import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from adam.api.app import create_app
from adam.api import deps
from adam.db.models import Base, Document, DocumentVersion, Source, PrecedentReference, DocumentPage
from adam.vocabularies import Classification, DepartmentId, DocType, SourceStatus, ReviewStatus


@pytest.fixture
def ext_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def ext_client(ext_engine):
    app = create_app()

    def override_db():
        factory = sessionmaker(bind=ext_engine, autoflush=False, expire_on_commit=False)
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.get_db] = override_db

    # Seed sample records for testing
    factory = sessionmaker(bind=ext_engine, autoflush=False, expire_on_commit=False)
    session = factory()

    src = Source(
        id="src_test_treasury",
        name="Uttarakhand Treasury Orders",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        owner_name="Treasury Director",
        owner_contact="director@uk.gov.in",
        written_authority_ref="UK/FIN/AUTH/01",
        permitted_domains=["uk.gov.in"],
        access_classification=Classification.PUBLIC.value,
        status=SourceStatus.APPROVED.value,
    )
    session.add(src)
    session.flush()

    doc_pub = Document(
        id="doc_pub_01",
        source_id=src.id,
        title="Revision of Dearness Allowance 2024",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        classification=Classification.PUBLIC.value,
        doc_type=DocType.GO.value,
    )
    doc_conf = Document(
        id="doc_conf_01",
        source_id=src.id,
        title="Confidential Vigilance Review",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        classification=Classification.CONFIDENTIAL.value,
        doc_type=DocType.GO.value,
    )
    session.add_all([doc_pub, doc_conf])
    session.flush()

    ver = DocumentVersion(
        id="ver_pub_01",
        document_id=doc_pub.id,
        source_url="https://uk.gov.in/go/101.pdf",
        sha256="abc123sha",
        mime_type="application/pdf",
        byte_size=1024,
        original_object_key="storage/101.pdf",
        go_number="UK/FIN/2024/101",
    )
    session.add(ver)
    session.flush()

    page = DocumentPage(
        id="page_pub_01",
        version_id=ver.id,
        page_number=1,
        clean_text="The dearness allowance is hereby increased by 4 percent.",
        selected_text="The dearness allowance is hereby increased by 4 percent.",
        word_count=10,
        review_status=ReviewStatus.FLAGGED.value,
        text_confidence=0.82,
    )
    session.add(page)

    prec = PrecedentReference(
        id="prec_01",
        source_version_id=ver.id,
        raw_citation_text="This order supersedes GO/FIN/2022/90",
        cited_order_number="GO/FIN/2022/90",
        relation_type="SUPERSEDES",
    )
    session.add(prec)
    session.commit()
    session.close()

    with TestClient(app, headers={"X-User-Role": "OFFICER"}) as c:
        yield c


def test_system_models_returns_registered_list(ext_client):
    res = ext_client.get("/api/system/models")
    assert res.status_code == 200
    models = res.json()
    assert len(models) >= 1
    primary = next((m for m in models if m.get("is_primary")), None)
    assert primary is not None
    assert "qwen" in primary["id"].lower()


def test_system_vocabularies_returns_controlled_lists(ext_client):
    res = ext_client.get("/api/system/vocabularies")
    assert res.status_code == 200
    data = res.json()
    assert "departments" in data
    assert "classifications" in data
    assert "doc_types" in data
    assert "precedent_types" in data
    assert "FINANCE_TREASURY" in [d["id"] for d in data["departments"]]
    assert "PUBLIC" in data["classifications"]


def test_documents_list_enforces_clearance_filtering(ext_client):
    # PUBLIC user can only see PUBLIC document
    res = ext_client.get("/api/documents", headers={"X-Clearance-Level": "PUBLIC"})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == "doc_pub_01"

    # CONFIDENTIAL user can see both documents
    res_conf = ext_client.get("/api/documents", headers={"X-Clearance-Level": "CONFIDENTIAL"})
    assert res_conf.status_code == 200
    assert res_conf.json()["total"] == 2


def test_get_document_details_returns_full_metadata(ext_client):
    res = ext_client.get("/api/documents/doc_pub_01", headers={"X-Clearance-Level": "PUBLIC"})
    assert res.status_code == 200
    doc = res.json()
    assert doc["id"] == "doc_pub_01"
    assert doc["title"] == "Revision of Dearness Allowance 2024"
    assert len(doc["pages"]) == 1
    assert doc["pages"][0]["page_number"] == 1
    assert len(doc["precedents"]) == 1
    assert doc["precedents"][0]["relation_type"] == "SUPERSEDES"


def test_get_document_details_rejects_insufficient_clearance(ext_client):
    res = ext_client.get("/api/documents/doc_conf_01", headers={"X-Clearance-Level": "PUBLIC"})
    assert res.status_code == 403


def test_list_precedents_returns_verified_chain(ext_client):
    res = ext_client.get("/api/precedents")
    assert res.status_code == 200
    links = res.json()
    assert len(links) == 1
    assert links[0]["relation_type"] == "SUPERSEDES"
    assert links[0]["cited_order_number"] == "GO/FIN/2022/90"


def test_sources_list_and_toggle_status(ext_client):
    res = ext_client.get("/api/sources")
    assert res.status_code == 200
    sources = res.json()
    assert len(sources) >= 1
    src = sources[0]
    assert src["status"] == "APPROVED"

    # Toggle to PAUSED
    toggle_res = ext_client.post(f"/api/sources/{src['id']}/toggle-status")
    assert toggle_res.status_code == 200
    assert toggle_res.json()["status"] == "PAUSED"

    # Toggle back to APPROVED
    toggle_back = ext_client.post(f"/api/sources/{src['id']}/toggle-status")
    assert toggle_back.status_code == 200
    assert toggle_back.json()["status"] == "APPROVED"


def test_review_pages_workflow_approve_and_correct(ext_client):
    res = ext_client.get("/api/review/pages")
    assert res.status_code == 200
    pages = res.json()
    assert len(pages) == 1
    page_id = pages[0]["id"]
    assert pages[0]["review_status"] == "FLAGGED"

    # Submit correction
    corr_res = ext_client.post(
        f"/api/review/pages/{page_id}/correct",
        json={"corrected_text": "Corrected text: DA increased by 4 percent.", "reviewer": "officer_qa"},
    )
    assert corr_res.status_code == 200
    assert corr_res.json()["review_status"] == "CORRECTED"

    # Approve page
    app_res = ext_client.post(f"/api/review/pages/{page_id}/approve", headers={"X-User-Id": "officer_qa"})
    assert app_res.status_code == 200
    assert app_res.json()["review_status"] == "REVIEWED"


def test_user_preferences_lifecycle(ext_client):
    # Initial empty preferences
    get_res = ext_client.get("/api/user/preferences", headers={"X-User-Id": "user_pref_test"})
    assert get_res.status_code == 200
    assert get_res.json()["opt_in"] is False

    # Save preferences with opt-in
    post_res = ext_client.post(
        "/api/user/preferences",
        headers={"X-User-Id": "user_pref_test"},
        json={
            "opt_in": True,
            "purpose": "Language and display formatting",
            "preferences": {"language": "hi", "theme": "light"},
        },
    )
    assert post_res.status_code == 200
    assert post_res.json()["opt_in"] is True

    # Retrieve saved preferences
    saved_res = ext_client.get("/api/user/preferences", headers={"X-User-Id": "user_pref_test"})
    assert saved_res.status_code == 200
    assert saved_res.json()["opt_in"] is True
    assert saved_res.json()["preferences"]["language"] == "hi"

    # Delete preferences
    del_res = ext_client.delete("/api/user/preferences", headers={"X-User-Id": "user_pref_test"})
    assert del_res.status_code == 200
