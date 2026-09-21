"""Tests for Air-Gapped Data Sovereignty and Cloud Model Boundary Policy.

Verifies:
1. Explicit policy checks forbidding cloud models (Gemini) under RESTRICTED and CONFIDENTIAL clearances.
2. Local models (Ollama / deterministic) remain fully authorized across all clearance levels.
3. State machine enforces air-gapped boundaries in Stage 1 (Authenticate) with SECURITY_DENIED event.
4. GET /api/system/models marks cloud models as air_gapped_restricted under classified clearance.
5. POST /api/chat intercepts cloud model requests under classified clearance and returns structured error.
6. Verification that no route contains duplicate hard-fail gates bypassing deterministic fallbacks.
"""

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from adam.api.app import app
from adam.db.models import Base
from adam.vocabularies import Classification, AgentState
from adam.model.policy import (
    AirGappedSovereigntyViolationError,
    is_cloud_model,
    validate_air_gapped_model_policy,
    enforce_air_gapped_model_policy,
)
from adam.model.runtime import SingleModelLifecycleManager
from adam.agent.state_machine import AgentStateMachine
from adam.rag.models import UserContext
from adam.observability.events import OperationalEventType


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_is_cloud_model_detection():
    """Verify accurate detection of cloud model artifacts and backends."""
    assert is_cloud_model(model_id="gemini-3.6-flash") is True
    assert is_cloud_model(model_id="gemini-1.5-pro") is True
    assert is_cloud_model(backend="gemini") is True
    assert is_cloud_model(serving_runtime="gemini") is True

    assert is_cloud_model(model_id="qwen2.5-3b-instruct-q4") is False
    assert is_cloud_model(model_id="qwen3-4b-instruct-q4") is False
    assert is_cloud_model(backend="ollama") is False
    assert is_cloud_model(backend="deterministic") is False


def test_validate_air_gapped_model_policy():
    """Cloud models must be prohibited for RESTRICTED and CONFIDENTIAL, permitted for PUBLIC and INTERNAL."""
    # RESTRICTED clearance
    allowed, reason = validate_air_gapped_model_policy("gemini-3.6-flash", Classification.RESTRICTED.value)
    assert allowed is False
    assert "Air-Gapped Data Sovereignty Policy" in reason

    # CONFIDENTIAL clearance
    allowed, reason = validate_air_gapped_model_policy("gemini-3.6-flash", Classification.CONFIDENTIAL.value)
    assert allowed is False
    assert "Air-Gapped Data Sovereignty Policy" in reason

    # PUBLIC clearance allows cloud model
    allowed, reason = validate_air_gapped_model_policy("gemini-3.6-flash", Classification.PUBLIC.value)
    assert allowed is True
    assert reason is None

    # INTERNAL clearance allows cloud model
    allowed, reason = validate_air_gapped_model_policy("gemini-3.6-flash", Classification.INTERNAL.value)
    assert allowed is True
    assert reason is None

    # Local models authorized across all clearance levels
    for cl in (Classification.PUBLIC.value, Classification.INTERNAL.value, Classification.RESTRICTED.value, Classification.CONFIDENTIAL.value):
        allowed, reason = validate_air_gapped_model_policy("qwen2.5-3b-instruct-q4", cl)
        assert allowed is True
        assert reason is None


def test_enforce_air_gapped_model_policy_raises():
    """enforce_air_gapped_model_policy must raise AirGappedSovereigntyViolationError."""
    with pytest.raises(AirGappedSovereigntyViolationError):
        enforce_air_gapped_model_policy("gemini-3.6-flash", Classification.RESTRICTED.value)

    with pytest.raises(AirGappedSovereigntyViolationError):
        enforce_air_gapped_model_policy("gemini-3.6-flash", Classification.CONFIDENTIAL.value)

    # Local model must not raise
    enforce_air_gapped_model_policy("qwen2.5-3b-instruct-q4", Classification.RESTRICTED.value)


def test_lifecycle_manager_blocks_cloud_model_under_restricted(db_session):
    """SingleModelLifecycleManager.load_model must block cloud model when clearance is RESTRICTED."""
    lifecycle = SingleModelLifecycleManager()
    with pytest.raises(AirGappedSovereigntyViolationError) as exc_info:
        lifecycle.load_model("gemini-3.6-flash", clearance_level=Classification.RESTRICTED.value)
    assert "Air-Gapped Data Sovereignty Policy" in str(exc_info.value)


def test_state_machine_security_denial_on_air_gap_violation(db_session):
    """AgentStateMachine must fail with SECURITY_DENIED when cloud model is requested with RESTRICTED clearance."""
    agent = AgentStateMachine(db_session, model_id="gemini-3.6-flash")

    events = []
    def on_event(ev):
        events.append(ev)

    user_ctx = UserContext(
        user_id="officer_classified",
        roles=["OFFICER"],
        clearance_level=Classification.RESTRICTED.value,
    )

    session = agent.session_manager.create_session(user_id=user_ctx.user_id)

    with pytest.raises(AirGappedSovereigntyViolationError) as exc_info:
        agent.run(
            query="What are the finance treasury guidelines?",
            user_context=user_ctx,
            session_id=session.id,
            on_event=on_event,
        )

    assert "Air-Gapped Data Sovereignty Policy" in str(exc_info.value)

    # Verify SECURITY_DENIED event was emitted
    event_types = [e.type for e in events]
    assert OperationalEventType.SECURITY_DENIED in event_types
    assert OperationalEventType.EXECUTION_FAILED in event_types


def test_api_system_models_marks_cloud_models_restricted():
    """GET /api/system/models must flag Gemini as air_gapped_restricted when X-Clearance-Level is RESTRICTED."""
    client = TestClient(app)

    # 1. With PUBLIC clearance
    res_public = client.get("/api/system/models", headers={"X-Clearance-Level": "PUBLIC"})
    assert res_public.status_code == 200
    models_public = res_public.json()
    gemini_public = next((m for m in models_public if m["id"] == "gemini-3.6-flash"), None)
    assert gemini_public is not None
    assert gemini_public.get("air_gapped_restricted") is False

    # 2. With RESTRICTED clearance
    res_restricted = client.get("/api/system/models", headers={"X-Clearance-Level": "RESTRICTED"})
    assert res_restricted.status_code == 200
    models_restricted = res_restricted.json()
    gemini_restricted = next((m for m in models_restricted if m["id"] == "gemini-3.6-flash"), None)
    assert gemini_restricted is not None
    assert gemini_restricted.get("air_gapped_restricted") is True
    assert gemini_restricted.get("is_installed") is False
    assert gemini_restricted.get("is_supported") is False
    assert "Air-Gapped Sovereignty Policy" in gemini_restricted.get("unavailable_reason", "")

    # Local Qwen models must remain accessible
    qwen = next((m for m in models_restricted if "qwen" in m["id"].lower()), None)
    assert qwen is not None
    assert qwen.get("air_gapped_restricted") is False


def test_api_chat_rejects_gemini_under_restricted_clearance():
    """POST /api/chat must reject Gemini with air_gapped_policy_violation error event under RESTRICTED clearance."""
    client = TestClient(app)

    payload = {
        "query": "Summarize confidential budget documents",
        "model_id": "gemini-3.6-flash",
    }
    headers = {
        "X-User-Id": "officer_classified",
        "X-Clearance-Level": "RESTRICTED",
    }

    with client.stream("POST", "/api/chat", json=payload, headers=headers) as response:
        assert response.status_code == 200
        lines = [line for line in response.iter_lines() if line]

    # Find the error event
    error_data = None
    for i, line in enumerate(lines):
        if "event: error" in line and i + 1 < len(lines):
            data_line = lines[i + 1]
            if data_line.startswith("data: "):
                error_data = json.loads(data_line[6:])
                break

    assert error_data is not None
    assert error_data.get("category") == "air_gapped_policy_violation"
    assert "Air-Gapped" in error_data.get("title", "")
    assert error_data.get("suggested_action") == "switch_to_local_model"


def test_spot_check_no_duplicate_hard_fail_gates():
    """Verify that no API router contains duplicate live-presence checks bypassing fallbacks."""
    import inspect
    from adam.api.routers import chat, v1_chat, v1_search, v1_documents, documents

    # Inspect router route definitions
    for module in (chat, v1_chat, v1_search, v1_documents, documents):
        src = inspect.getsource(module)
        # Ensure no redundant live OllamaModelRuntime.is_model_present checks gating route entry
        assert "if not OllamaModelRuntime" not in src
        assert "if not ollama_rt.is_model_present" not in src
