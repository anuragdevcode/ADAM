"""Phase 0 Stop-Ship Security Verification Test Suite.

Asserts all Phase 0 security remediations from adam_plan.md:
- S4: Production startup secret validation (SIGNING_SECRET & DATABASE_URL)
- S3/S2: Default-deny RBAC on mutating & admin routes (403 on unauthenticated/unauthorized callers)
- S2: Document upload clearance ceiling check
- S6: Session IDOR mitigation (server-side identity derivation, cross-user denial)
- S7: Agent tools ACL filtering on database_query and compare_sources
- S8: Sandbox subprocess isolation, environment scrubbing, AST format-string protection, fail-closed
- S10: Hosted voice opt-in requirement (ADAM_ALLOW_HOSTED_VOICE=true)
- E2: Benchmark provenance metadata and /audit/benchmark/reference endpoint
"""

import ast
import multiprocessing
import os
import queue
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from adam.api.app import create_app
from adam.api import deps
from adam.config import get_signing_secret, validate_production_database_url
from adam.db.models import Base, ChatSession, Document, DocumentPage, DocumentVersion, Source
from adam.rag.models import UserContext
from adam.vocabularies import Classification, DepartmentId, DocType, LifecycleStatus, SourceStatus


# ── 1. S4: Production Secret Enforcement ─────────────────────────────────────

def test_production_signing_secret_validation(monkeypatch):
    """Refuse boot in production if SIGNING_SECRET is empty or placeholder."""
    monkeypatch.setenv("ADAM_ENV", "production")

    # Insecure placeholder secret
    monkeypatch.setenv("SIGNING_SECRET", "adam-uk-gov-default-auth-secret-key-2026")
    with pytest.raises(RuntimeError, match="insecure placeholder"):
        get_signing_secret()

    monkeypatch.setenv("SIGNING_SECRET", "change-me")
    with pytest.raises(RuntimeError, match="insecure placeholder"):
        get_signing_secret()

    # Valid secret in production
    monkeypatch.setenv("SIGNING_SECRET", "super-secure-production-random-secret-key-9999")
    secret = get_signing_secret()
    assert secret == "super-secure-production-random-secret-key-9999"


def test_production_database_url_validation(monkeypatch):
    """Refuse boot in production if DATABASE_URL contains placeholder passwords."""
    monkeypatch.setenv("ADAM_ENV", "production")

    # Placeholder password
    with pytest.raises(RuntimeError, match="placeholder password"):
        validate_production_database_url("postgresql+psycopg://adam:change-me@postgres:5432/adam")

    with pytest.raises(RuntimeError, match="placeholder password"):
        validate_production_database_url("postgresql+psycopg://adam:adam_dev_password@postgres:5432/adam")

    # Valid database URL
    valid_url = "postgresql+psycopg://adam_prod:StrongP@ssw0rd!@postgres:5432/adam_prod"
    assert validate_production_database_url(valid_url) == valid_url


# ── 2. S3/S2: Default-Deny RBAC on Mutating and Admin Routes ──────────────────

@pytest.fixture
def p0_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def p0_client(p0_engine):
    app = create_app()

    def override_db():
        factory = sessionmaker(bind=p0_engine, autoflush=False, expire_on_commit=False)
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.get_db] = override_db

    # Seed basic source
    factory = sessionmaker(bind=p0_engine, autoflush=False, expire_on_commit=False)
    session = factory()
    src = Source(
        id="src_seed_p0",
        name="P0 Test Source",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        owner_name="Admin",
        owner_contact="admin@uk.gov.in",
        written_authority_ref="GOV-REF-P0",
        status=SourceStatus.APPROVED.value,
    )
    session.add(src)
    session.commit()
    session.close()

    with TestClient(app) as c:
        yield c


def _get_error_msg(resp) -> str:
    body = resp.json()
    if isinstance(body, dict) and "error" in body and isinstance(body["error"], dict):
        return body["error"].get("message", "")
    if isinstance(body, dict):
        return str(body.get("detail", ""))
    return ""


def test_mutating_routes_reject_unauthenticated_callers(p0_client):
    """Unauthenticated or default (PUBLIC) callers are rejected with 403 on protected routes."""
    # 1. Provider routes (ADMIN)
    resp = p0_client.post("/api/system/providers", json={"name": "test", "endpoint_url": "https://api.test.org"})
    assert resp.status_code == 403
    assert "Access denied" in _get_error_msg(resp)

    resp = p0_client.delete("/api/system/providers/prov_123")
    assert resp.status_code == 403

    # 2. Source mutating routes (ADMIN, OFFICER)
    resp = p0_client.post("/api/sources", json={"name": "New Source"})
    assert resp.status_code == 403

    resp = p0_client.post("/api/sources/seed")
    assert resp.status_code == 403

    resp = p0_client.post("/api/sources/src_seed_p0/toggle-status")
    assert resp.status_code == 403

    resp = p0_client.delete("/api/sources/src_seed_p0")
    assert resp.status_code == 403

    # 3. Document upload route (ADMIN, OFFICER, RECORDS_OFFICER)
    resp = p0_client.post(
        "/api/documents/upload",
        data={"title": "Test Doc", "classification": "PUBLIC"},
        files={"file": ("test.pdf", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF", "application/pdf")},
    )
    assert resp.status_code == 403

    # 4. Review routes (ADMIN, OFFICER, REVIEWER)
    resp = p0_client.get("/api/review/pages")
    assert resp.status_code == 403

    resp = p0_client.post("/api/review/pages/page_123/approve")
    assert resp.status_code == 403

    resp = p0_client.post("/api/review/pages/page_123/correct", json={"corrected_text": "Updated text"})
    assert resp.status_code == 403

    # 5. Ingestion job control (ADMIN, OFFICER, OPERATOR)
    resp = p0_client.post("/api/ingestion/jobs", json={"source_id": "src_seed_p0"})
    assert resp.status_code == 403

    resp = p0_client.get("/api/ingestion/jobs")
    assert resp.status_code == 403

    # 6. Audit & telemetry (ADMIN, OFFICER, AUDITOR, OPERATOR)
    resp = p0_client.get("/api/audit/executions")
    assert resp.status_code == 403

    resp = p0_client.get("/api/audit/metrics")
    assert resp.status_code == 403

    resp = p0_client.get("/api/metrics")
    assert resp.status_code == 403


def test_authorized_caller_can_access_protected_routes(p0_client):
    """Callers with appropriate role headers can access protected routes."""
    # ADMIN accessing /api/metrics
    resp = p0_client.get("/api/metrics", headers={"X-User-Role": "ADMIN"})
    assert resp.status_code == 200
    assert "adam_info" in resp.text

    # OFFICER accessing /api/sources/seed
    resp = p0_client.post("/api/sources/seed", headers={"X-User-Role": "OFFICER"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # AUDITOR accessing /api/audit/metrics
    resp = p0_client.get("/api/audit/metrics", headers={"X-User-Role": "AUDITOR"})
    assert resp.status_code == 200

    # REVIEWER accessing /api/review/pages
    resp = p0_client.get("/api/review/pages", headers={"X-User-Role": "REVIEWER"})
    assert resp.status_code == 200


def test_document_upload_classification_ceiling(p0_client):
    """User cannot upload a document with classification higher than their own clearance."""
    # An OFFICER with RESTRICTED clearance attempting to upload a CONFIDENTIAL document
    resp = p0_client.post(
        "/api/documents/upload",
        data={"title": "Leaked Secret", "classification": "CONFIDENTIAL"},
        files={"file": ("secret.pdf", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF", "application/pdf")},
        headers={"X-User-Role": "OFFICER", "X-Clearance-Level": "RESTRICTED"},
    )
    assert resp.status_code == 403
    assert "exceeds user clearance ceiling" in _get_error_msg(resp)


# ── 3. S6: Session IDOR Mitigation ───────────────────────────────────────────

def test_session_idor_prevention(p0_client, p0_engine):
    """Users cannot enumerate or view other users' sessions."""
    from datetime import timedelta
    factory = sessionmaker(bind=p0_engine, autoflush=False, expire_on_commit=False)
    session = factory()
    expires = datetime.now(timezone.utc) + timedelta(days=1)
    s_alice = ChatSession(id="sess_alice_01", user_id="alice", expires_at=expires)
    s_bob = ChatSession(id="sess_bob_01", user_id="bob", expires_at=expires)
    session.add(s_alice)
    session.add(s_bob)
    session.commit()
    session.close()

    # Alice asks for her sessions
    resp_alice = p0_client.get("/api/sessions", headers={"X-User-Id": "alice"})
    assert resp_alice.status_code == 200
    session_ids = [s["session_id"] for s in resp_alice.json()]
    assert "sess_alice_01" in session_ids
    assert "sess_bob_01" not in session_ids

    # Alice attempts IDOR enumeration of Bob's sessions via query param
    resp_idor = p0_client.get("/api/sessions?user_id=bob", headers={"X-User-Id": "alice"})
    assert resp_idor.status_code == 403
    assert "Cannot list sessions for another user" in _get_error_msg(resp_idor)

    # Admin CAN view Bob's sessions
    resp_admin = p0_client.get("/api/sessions?user_id=bob", headers={"X-User-Id": "admin", "X-User-Role": "ADMIN"})
    assert resp_admin.status_code == 200
    admin_session_ids = [s["session_id"] for s in resp_admin.json()]
    assert "sess_bob_01" in admin_session_ids

    # Alice attempts to access Bob's session history directly
    resp_hist_idor = p0_client.get("/api/sessions/sess_bob_01/history", headers={"X-User-Id": "alice"})
    assert resp_hist_idor.status_code == 403

    # Alice attempts to delete Bob's session
    resp_del_idor = p0_client.delete("/api/sessions/sess_bob_01", headers={"X-User-Id": "alice"})
    assert resp_del_idor.status_code == 403


# ── 4. S7: Agent Tools ACL Enforcement ───────────────────────────────────────

def test_agent_tools_acl_filtering(p0_engine):
    """database_query and compare_sources strictly filter confidential records for public users."""
    from adam.agent.tools import ReadOnlyToolRegistry
    from adam.db.models import AccessGrant
    from adam.vocabularies import AccessAction

    factory = sessionmaker(bind=p0_engine, autoflush=False, expire_on_commit=False)
    session = factory()

    # Seed public and confidential documents
    doc_pub = Document(
        id="doc_p0_pub",
        title="Public Holiday Calendar 2026",
        department_id=DepartmentId.GENERAL_ADMINISTRATION.value,
        classification=Classification.PUBLIC.value,
        doc_type=DocType.CIRCULAR.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    doc_conf = Document(
        id="doc_p0_conf",
        title="Cabinet Confidential Security Strategy",
        department_id=DepartmentId.GENERAL_ADMINISTRATION.value,
        classification=Classification.CONFIDENTIAL.value,
        doc_type=DocType.GO.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    # Explicit need-to-know grant for director to access CONFIDENTIAL records
    grant_conf = AccessGrant(
        id="grant_director_conf",
        subject_id="director",
        classification=Classification.CONFIDENTIAL.value,
        action=AccessAction.READ.value,
    )
    session.add(doc_pub)
    session.add(doc_conf)
    session.add(grant_conf)
    session.commit()

    # 1. PUBLIC user queries Document table via database_query
    public_ctx = UserContext(user_id="citizen", roles=["PUBLIC"], clearance_level=Classification.PUBLIC.value)
    res_pub = ReadOnlyToolRegistry.execute(
        "database_query",
        {"table": "documents", "aggregate": "records"},
        user_context=public_ctx,
        session=session,
    )
    records_pub = res_pub.get("records", [])
    titles_pub = [r.get("title") for r in records_pub]
    assert "Public Holiday Calendar 2026" in titles_pub
    assert "Cabinet Confidential Security Strategy" not in titles_pub

    # Count aggregate for PUBLIC user excludes CONFIDENTIAL
    res_pub_count = ReadOnlyToolRegistry.execute(
        "database_query",
        {"table": "documents", "aggregate": "count"},
        user_context=public_ctx,
        session=session,
    )
    assert res_pub_count.get("result") == 1

    # 2. CONFIDENTIAL user queries Document table via database_query
    conf_ctx = UserContext(user_id="director", roles=["OFFICER"], clearance_level=Classification.CONFIDENTIAL.value)
    res_conf = ReadOnlyToolRegistry.execute(
        "database_query",
        {"table": "documents", "aggregate": "records"},
        user_context=conf_ctx,
        session=session,
    )
    titles_conf = [r.get("title") for r in res_conf.get("records", [])]
    assert "Public Holiday Calendar 2026" in titles_conf
    assert "Cabinet Confidential Security Strategy" in titles_conf

    # Count aggregate for CONFIDENTIAL user includes both
    res_conf_count = ReadOnlyToolRegistry.execute(
        "database_query",
        {"table": "documents", "aggregate": "count"},
        user_context=conf_ctx,
        session=session,
    )
    assert res_conf_count.get("result") == 2

    # 3. compare_sources with confidential document fails for PUBLIC user
    res_comp_pub = ReadOnlyToolRegistry.execute(
        "compare_sources",
        {"source_a": "doc_p0_pub", "source_b": "doc_p0_conf"},
        user_context=public_ctx,
        session=session,
    )
    assert res_comp_pub.get("status") == "forbidden"
    assert "access denied" in res_comp_pub.get("error", "").lower()
    # Confirm confidential title was NOT leaked in error
    assert "Cabinet Confidential" not in res_comp_pub.get("error", "")

    session.close()


# ── 5. S8: Sandbox Subprocess Isolation & Fail-Closed ────────────────────────

def test_sandbox_format_string_dunder_blocking():
    """Format string dunder access is blocked by AST verification."""
    from adam.agent.sandbox import SecurePythonSandbox

    sandbox = SecurePythonSandbox()

    # Attempt attribute traversal via format string
    exploit_code = 'payload = "{0.__class__.__mro__}".format(1)'
    res = sandbox.execute(exploit_code)
    assert res.success is False
    assert "unauthorized inspection" in res.error.lower() or "forbidden" in res.error.lower()


def test_sandbox_subprocess_worker_environment_scrubbing(monkeypatch):
    """Worker process environment scrubbing removes sensitive keys."""
    monkeypatch.setenv("SIGNING_SECRET", "super-secret-signing-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secretpass@localhost/db")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key-xyz")
    monkeypatch.setenv("SAFE_APP_VAR", "visible_constant")

    from adam.agent.sandbox import _subprocess_sandbox_worker
    q = queue.Queue()
    _subprocess_sandbox_worker("result = 1 + 1", {}, q, max_output_chars=1000)
    res = q.get()
    assert res["success"] is True
    assert res["value"] == 2
    # Verify sensitive env vars were scrubbed from process environment
    assert "SIGNING_SECRET" not in os.environ
    assert "DATABASE_URL" not in os.environ
    assert "GROQ_API_KEY" not in os.environ
    assert os.environ.get("SAFE_APP_VAR") == "visible_constant"


def test_sandbox_fails_closed_without_in_process_fallback(monkeypatch):
    """When subprocess invocation fails, sandbox returns error without executing in API process."""
    from adam.agent.sandbox import SecurePythonSandbox

    spawn_ctx = multiprocessing.get_context("spawn")

    class FailingProcess:
        def __init__(self, *args, **kwargs):
            pass
        def start(self):
            raise OSError("Subprocess creation disabled by security policy")
        def is_alive(self):
            return False

    monkeypatch.setattr(spawn_ctx, "Process", FailingProcess)
    monkeypatch.setattr(multiprocessing, "get_context", lambda mode="spawn": spawn_ctx)

    sandbox = SecurePythonSandbox()
    res = sandbox.execute("result = 42")
    assert res.success is False
    assert "Sandbox execution failed" in res.error or "disabled" in res.error
    assert res.value is None


# ── 6. S10: Hosted Voice Opt-In Enforcement ──────────────────────────────────

def test_hosted_voice_refuses_egress_when_not_opted_in(monkeypatch):
    """Groq STT engine refuses initialization when ADAM_ALLOW_HOSTED_VOICE is not true."""
    from adam.api.voice.stt import GroqWhisperEngine, SttError, get_stt_engine

    # 1. get_stt_engine does not select Groq if hosted voice is not enabled
    monkeypatch.delenv("ADAM_ALLOW_HOSTED_VOICE", raising=False)
    monkeypatch.setenv("ADAM_STT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_123")
    engine = get_stt_engine()
    assert engine.provider != "groq"

    # 2. Direct GroqWhisperEngine.transcribe refuses when ADAM_ALLOW_HOSTED_VOICE is not true
    groq = GroqWhisperEngine(api_key="gsk_test_123")
    with pytest.raises(SttError, match="Hosted speech-to-text is disabled"):
        groq.transcribe(b"dummy audio")

    # 3. When opted in explicitly via ADAM_ALLOW_HOSTED_VOICE=true
    monkeypatch.setenv("ADAM_ALLOW_HOSTED_VOICE", "true")
    engine_opt_in = get_stt_engine()
    assert engine_opt_in.provider == "groq"


# ── 7. E2/E3: Audit Reference Endpoint & Provenance Metadata ─────────────────

def test_audit_benchmark_reference_endpoint(p0_client):
    """Audit reference endpoint returns benchmark metadata marking it as a synthetic smoke test."""
    resp = p0_client.get("/api/audit/benchmark/reference", headers={"X-User-Role": "ADMIN"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["benchmark_type"] == "synthetic_smoke_test_10_docs"
    assert data["corpus_document_count"] == 10
    assert data["corpus_page_count"] == 12
    assert "synthetic gold corpus" in data["provenance"].lower()
    assert data["total_queries"] == 215
    assert data["citation_page_precision"] == 0.9733
    assert data["recall_at_10"] == 1.0
    assert "reranker_ablation" in data
