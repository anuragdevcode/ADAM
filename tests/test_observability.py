"""Tests for Backend <-> Frontend Operational Transparency (Observability)."""

import json
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from adam.observability.events import (
    OperationalEventType,
    OperationalEvent,
    OperationalEventEmitter,
)
from adam.observability.serializer import PublicEventSerializer
from adam.rag.models import UserContext


# ── 1. Event Emitter & Monotonic Sequencing ─────────────────────────────────

def test_emitter_monotonic_sequence_and_durations():
    """EventEmitter must assign strictly monotonic sequence numbers and calculate durations."""
    events = []
    emitter = OperationalEventEmitter(on_event=events.append, trace_id="tr_custom123")

    assert emitter.trace_id == "tr_custom123"

    emitter.start_stage("security")
    e1 = emitter.emit(
        OperationalEventType.SECURITY_STARTED,
        stage="security",
        status="running",
        message="Verifying security clearance",
    )
    assert e1.sequence == 1
    assert e1.trace_id == "tr_custom123"
    assert e1.span_id.startswith("sp_")

    e2 = emitter.emit(
        OperationalEventType.SECURITY_COMPLETED,
        stage="security",
        status="completed",
        message="Clearance verified",
    )
    assert e2.sequence == 2
    assert e2.duration_ms is not None
    assert e2.duration_ms >= 0.0

    emitter.start_stage("retrieval")
    e3 = emitter.emit(
        OperationalEventType.RETRIEVAL_STARTED,
        stage="retrieval",
        status="running",
        message="Searching records",
    )
    assert e3.sequence == 3
    assert len(events) == 3


# ── 2. Strict Public Sanitization Boundary ──────────────────────────────────

def test_serializer_whitelists_safe_metrics():
    """Serializer must allow whitelisted governance metrics through."""
    event = OperationalEvent(
        sequence=1,
        type=OperationalEventType.RETRIEVAL_COMPLETED,
        stage="retrieval",
        status="completed",
        message="18 records evaluated",
        duration_ms=45.2,
        trace_id="tr_12345",
        data={
            "candidate_count": 18,
            "records_considered": 18,
            "query_language": "en",
            "is_high_risk": False,
        },
    )

    serialized = PublicEventSerializer.serialize(event)
    assert serialized is not None
    assert serialized["sequence"] == 1
    assert serialized["type"] == "retrieval.completed"
    assert serialized["stage"] == "retrieval"
    assert serialized["duration_ms"] == 45.2
    assert serialized["data"]["candidate_count"] == 18
    assert serialized["data"]["query_language"] == "en"


def test_serializer_purges_sensitive_internals_and_keys():
    """Serializer must strip SQL, API keys, system prompts, filesystem paths, and secrets."""
    event = OperationalEvent(
        sequence=2,
        type=OperationalEventType.MODEL_READY,
        stage="model",
        status="completed",
        message="Model ready at /Users/anurag/ADAM/models/gemini.bin with key AIzaSyTestKey12345678901234",
        trace_id="tr_12345",
        data={
            "api_key": "AIzaSySecretApiKeyHere9999",
            "sql_query": "SELECT * FROM public_records WHERE classification = 'SECRET'",
            "system_prompt": "You are a state clerk assistant...",
            "filepath": "/Users/anurag/sensitive_doc.pdf",
            "candidate_count": 5,  # Whitelisted field
        },
    )

    serialized = PublicEventSerializer.serialize(event)
    assert serialized is not None

    # Whitelisted primitive remains
    assert serialized["data"].get("candidate_count") == 5

    # Dangerous fields completely purged
    assert "api_key" not in serialized["data"]
    assert "sql_query" not in serialized["data"]
    assert "system_prompt" not in serialized["data"]
    assert "filepath" not in serialized["data"]

    # Message paths and keys redacted
    assert "/Users/anurag" not in serialized["message"]
    assert "AIzaSyTestKey12345678901234" not in serialized["message"]
    assert "[path]" in serialized["message"] or "[redacted]" in serialized["message"]


# ── 3. Agent Integration & Lifecycle Events ─────────────────────────────────

def test_agent_emits_lifecycle_events_on_greeting(db_session):
    """Greeting query should emit security, query parsing, retrieval, evidence, and answer grounded events."""
    from adam.agent.state_machine import AgentStateMachine

    agent = AgentStateMachine(db_session)
    events = []

    user = UserContext(user_id="officer_1", clearance_level="PUBLIC", roles=["OFFICER"])
    response = agent.run(
        query="Hello ADAM",
        user_context=user,
        on_event=events.append,
        trace_id="tr_test_greet",
    )

    assert response is not None
    assert len(events) >= 5

    # Verify event types present in order
    event_types = [e.type for e in events]
    assert OperationalEventType.SECURITY_STARTED in event_types
    assert OperationalEventType.SECURITY_COMPLETED in event_types
    assert OperationalEventType.QUERY_PARSED in event_types
    assert OperationalEventType.GENERATION_STARTED in event_types
    assert OperationalEventType.GENERATION_COMPLETED in event_types
    assert OperationalEventType.ANSWER_GROUNDED in event_types
    assert OperationalEventType.EXECUTION_COMPLETED in event_types

    # Verify monotonic sequencing
    sequences = [e.sequence for e in events]
    assert sequences == sorted(sequences)
    assert sequences[0] == 1


def test_agent_emits_security_denied_on_invalid_clearance(db_session):
    """Invalid clearance level should emit security.started and security.denied before raising."""
    from adam.agent.state_machine import AgentStateMachine

    agent = AgentStateMachine(db_session)
    events = []

    user = UserContext(user_id="guest_1", clearance_level="INVALID_LEVEL", roles=["GUEST"])
    with pytest.raises(PermissionError):
        agent.run(
            query="Tell me about budget",
            user_context=user,
            on_event=events.append,
        )

    event_types = [e.type for e in events]
    assert OperationalEventType.SECURITY_STARTED in event_types
    assert OperationalEventType.SECURITY_DENIED in event_types
    assert OperationalEventType.EXECUTION_FAILED in event_types


# ── 4. FastAPI Streaming Chat Status Events ─────────────────────────────────

def test_api_chat_streams_operational_status_events():
    """Chat endpoint should stream event: status SSE frames alongside start, token, and done."""
    from adam.api.app import create_app
    from dataclasses import dataclass, field
    from typing import List, Optional

    @dataclass
    class _MockResponse:
        session_id: str = "sess_obs_123"
        answer: str = "Finance GO 101 establishes rules."
        citations: List = field(default_factory=list)
        currency_banners: List[str] = field(default_factory=list)
        search_suggestions: List[str] = field(default_factory=list)
        is_no_answer: bool = False
        is_high_risk: bool = False
        validation_passed: bool = True
        latency_ms: float = 120.0

    def mock_run(query, user_context=None, session_id=None, on_event=None, trace_id=None):
        if on_event:
            emitter = OperationalEventEmitter(on_event=on_event, trace_id=trace_id)
            emitter.emit(
                OperationalEventType.SECURITY_COMPLETED,
                stage="security",
                status="completed",
                message="Security clearance OK",
            )
            emitter.emit(
                OperationalEventType.RETRIEVAL_COMPLETED,
                stage="retrieval",
                status="completed",
                message="Found 5 records",
                data={"candidate_count": 5},
            )
        return _MockResponse()

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    with patch("adam.api.routers.chat.AgentStateMachine") as MockAgent:
        instance = MagicMock()
        instance.run.side_effect = mock_run
        MockAgent.return_value = instance

        resp = client.post(
            "/api/chat",
            json={"query": "Finance rules"},
            headers={"X-User-Id": "officer_1"},
        )

        assert resp.status_code == 200
        assert "event: status" in resp.text

        # Parse status events from SSE body
        lines = resp.text.split("\n")
        status_events = []
        for i, line in enumerate(lines):
            if line == "event: status":
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith("data:"):
                        payload = json.loads(lines[j][len("data:"):].strip())
                        status_events.append(payload)
                        break

        assert len(status_events) >= 2
        assert status_events[0]["stage"] == "security"
        assert status_events[1]["stage"] == "retrieval"
        assert status_events[1]["data"]["candidate_count"] == 5
