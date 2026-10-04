"""Tests for ADAM API session management endpoints (Phase 06).

Uses SQLAlchemy StaticPool so the in-memory SQLite connection is shared
across threads (FastAPI runs sync endpoints in a thread pool).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from adam.db.models import Base
from adam.memory.session import SessionManager


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_engine():
    """Single shared in-memory SQLite connection via StaticPool, thread-safe."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def api_engine():
    """Single shared in-memory SQLite engine per test, with StaticPool."""
    engine = _make_engine()
    yield engine


@pytest.fixture()
def api_db(api_engine):
    """One database session per test."""
    factory = sessionmaker(bind=api_engine, autoflush=False, expire_on_commit=False)
    db = factory()
    yield db
    db.close()


@pytest.fixture()
def test_client(api_db, monkeypatch):
    """FastAPI test client with get_db overridden to use the test session."""
    monkeypatch.setenv("ADAM_TRUST_UNVERIFIED_HEADERS", "true")
    from adam.api.app import create_app
    from adam.api import deps

    app = create_app()

    def override_get_db():
        yield api_db

    app.dependency_overrides[deps.get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture()
def active_session(api_db):
    """Create a live ChatSession in the test database."""
    mgr = SessionManager(api_db)
    sess = mgr.create_session(user_id="officer_sess_test", classification_ceiling="PUBLIC")
    return sess


@pytest.fixture()
def session_with_turns(api_db, active_session):
    """Create a session with two encrypted turns."""
    mgr = SessionManager(api_db)
    mgr.add_turn(
        session_id=active_session.id,
        user_id="officer_sess_test",
        role="user",
        content="What is the DA rate?",
    )
    mgr.add_turn(
        session_id=active_session.id,
        user_id="officer_sess_test",
        role="assistant",
        content="The DA rate is 46%.",
    )
    return active_session


# ── List Sessions ─────────────────────────────────────────────────────────────

def test_list_sessions_empty_for_unknown_user(test_client):
    """GET /api/sessions for a user with no sessions returns empty list."""
    resp = test_client.get(
        "/api/sessions",
        params={"user_id": "nobody_at_all"},
        headers={"X-User-Id": "nobody_at_all"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data == []


def test_list_sessions_returns_active_sessions(test_client, active_session):
    """GET /api/sessions returns sessions for a known user."""
    resp = test_client.get(
        "/api/sessions",
        params={"user_id": "officer_sess_test"},
        headers={"X-User-Id": "officer_sess_test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    ids = [s["session_id"] for s in data]
    assert active_session.id in ids


def test_list_sessions_response_has_required_fields(test_client, active_session):
    """Each session record must expose session_id, user_id, is_active, turn_count."""
    resp = test_client.get(
        "/api/sessions",
        params={"user_id": "officer_sess_test"},
        headers={"X-User-Id": "officer_sess_test"},
    )
    assert resp.status_code == 200
    record = next(s for s in resp.json() if s["session_id"] == active_session.id)
    assert "session_id" in record
    assert "user_id" in record
    assert "is_active" in record
    assert "turn_count" in record
    assert "created_at" in record
    assert "expires_at" in record


def test_list_sessions_unauthenticated_idor_forbidden(test_client, active_session):
    """An unauthenticated (anonymous) or different user cannot list another user's sessions."""
    resp = test_client.get(
        "/api/sessions",
        params={"user_id": "officer_sess_test"},
        headers={"X-User-Id": "anonymous"},
    )
    assert resp.status_code == 403

    resp2 = test_client.get(
        "/api/sessions",
        params={"user_id": "officer_sess_test"},
        headers={"X-User-Id": "another_officer"},
    )
    assert resp2.status_code == 403


# ── Session History ────────────────────────────────────────────────────────────

def test_session_history_returns_decrypted_turns(test_client, session_with_turns):
    """GET /api/sessions/{id}/history returns decrypted turns for owner."""
    resp = test_client.get(
        f"/api/sessions/{session_with_turns.id}/history",
        headers={"X-User-Id": "officer_sess_test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert "turns" in data
    turns = data["turns"]
    assert len(turns) == 2
    roles = [t["role"] for t in turns]
    assert "user" in roles
    assert "assistant" in roles
    contents = [t["content"] for t in turns]
    assert any("DA rate" in c for c in contents)


def test_session_history_cross_user_returns_403(test_client, session_with_turns):
    """GET /api/sessions/{id}/history with wrong user returns 403."""
    resp = test_client.get(
        f"/api/sessions/{session_with_turns.id}/history",
        headers={"X-User-Id": "wrong_user_xyz"},
    )
    assert resp.status_code == 403


def test_session_history_nonexistent_returns_404(test_client):
    """GET /api/sessions/{id}/history for unknown session returns 404."""
    resp = test_client.get(
        "/api/sessions/sess_doesnotexist9999/history",
        headers={"X-User-Id": "officer_sess_test"},
    )
    assert resp.status_code == 404


# ── Delete Session ─────────────────────────────────────────────────────────────

def test_delete_session_removes_session(test_client, active_session):
    """DELETE /api/sessions/{id} removes the session for the owning user."""
    resp = test_client.get(
        "/api/sessions",
        params={"user_id": "officer_sess_test"},
        headers={"X-User-Id": "officer_sess_test"},
    )
    assert resp.status_code == 200
    assert any(s["session_id"] == active_session.id for s in resp.json())

    del_resp = test_client.delete(
        f"/api/sessions/{active_session.id}",
        headers={"X-User-Id": "officer_sess_test"},
    )
    assert del_resp.status_code == 200
    assert del_resp.json().get("deleted") is True


def test_delete_session_wrong_user_returns_403(test_client, active_session):
    """DELETE /api/sessions/{id} by non-owning user returns 403."""
    resp = test_client.delete(
        f"/api/sessions/{active_session.id}",
        headers={"X-User-Id": "intruder_user"},
    )
    assert resp.status_code == 403


def test_delete_nonexistent_session_returns_404(test_client):
    """DELETE /api/sessions/{id} for unknown session returns 404."""
    resp = test_client.delete(
        "/api/sessions/sess_ghost99999",
        headers={"X-User-Id": "officer_sess_test"},
    )
    assert resp.status_code == 404
