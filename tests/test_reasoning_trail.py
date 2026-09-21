"""Unit and integration tests for State-Transition Reasoning Trail and Per-Stage Latency.

Verifies:
1. AgentStateTransition fields, per-stage timing, and to_dict() serialization.
2. BoundedAgentStateMachine per_stage_latency_ms across the 7 deterministic stages.
3. Explicit abstention_reason capture on out-of-jurisdiction and refusal queries.
4. AgentExecutionAudit persistence of transition duration and abstention reasons.
5. FastAPI SSE /api/chat streaming of 'event: trail' and enriched 'event: done'.
6. /api/audit/metrics aggregate average response time and per-stage latency calculation.
"""

import json
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from adam.agent.state_machine import (
    BoundedAgentStateMachine,
    AgentStateTransition,
    AgentResponse,
)
from adam.api.app import create_app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from adam.db.models import (
    Base,
    Document,
    DocumentVersion,
    DocumentChunk,
    AgentExecutionAudit,
)
from adam.rag.models import UserContext
from adam.vocabularies import (
    AgentState,
    Classification,
    DepartmentId,
    DocType,
    LifecycleStatus,
)


# ── Test Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def populated_trail_db():
    """Seed thread-safe in-memory SQLite database for agent and API tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()

    doc = Document(
        id="doc_trail_fin_2024",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        title="Sanction of Revised Allowances 2024",
        classification=Classification.PUBLIC.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    session.add(doc)

    ver = DocumentVersion(
        id="ver_trail_fin_2024",
        document_id="doc_trail_fin_2024",
        source_url="https://ekosh.uk.gov.in/orders/allowance2024.pdf",
        sha256="sha256_trail_test_hash_allowance_2024",
        mime_type="application/pdf",
        byte_size=8192,
        go_number="UK/FIN/2024/202",
        original_object_key="originals/allowance2024.pdf",
    )
    session.add(ver)

    chk = DocumentChunk(
        id="chk_trail_fin_2024_01",
        document_id="doc_trail_fin_2024",
        version_id="ver_trail_fin_2024",
        chunk_index=0,
        content="Under order UK/FIN/2024/202 dated 20/02/2024, Uttarakhand Finance sanctions special hill allowance.",
        page_start=1,
        page_end=1,
    )
    session.add(chk)
    session.commit()
    yield session
    session.close()


# ── 1. AgentStateTransition Dataclass & Serialization ───────────────────────────

def test_agent_state_transition_attributes_and_serialization():
    """AgentStateTransition must record duration_ms, stage, abstention_reason and serialize via to_dict()."""
    trans = AgentStateTransition(
        from_state=AgentState.AUTHENTICATE.value,
        to_state=AgentState.CLASSIFY_REQUEST.value,
        timestamp="2026-09-21T07:00:00Z",
        notes="Authentication verified",
        duration_ms=12.456,
        stage="AUTHENTICATE",
        abstention_reason=None,
    )

    assert trans.from_state == "AUTHENTICATE"
    assert trans.to_state == "CLASSIFY_REQUEST"
    assert trans.duration_ms == 12.456
    assert trans.stage == "AUTHENTICATE"
    assert trans.abstention_reason is None

    d = trans.to_dict()
    assert d["from"] == "AUTHENTICATE"
    assert d["to"] == "CLASSIFY_REQUEST"
    assert d["duration_ms"] == 12.46  # Rounded to 2 decimal places
    assert d["stage"] == "AUTHENTICATE"
    assert d["abstention_reason"] is None


# ── 2. Per-Stage Latency Tracking in State Machine ────────────────────────────

def test_state_machine_records_per_stage_latency(populated_trail_db):
    """BoundedAgentStateMachine must record non-negative duration_ms for each stage."""
    agent = BoundedAgentStateMachine(populated_trail_db)
    user = UserContext(clearance_level=Classification.PUBLIC.value)

    resp: AgentResponse = agent.run(
        query="What is the special hill allowance under UK/FIN/2024/202?",
        user_context=user,
    )

    assert resp.per_stage_latency_ms is not None
    assert len(resp.per_stage_latency_ms) > 0

    # Key stages must be present in per_stage_latency_ms
    expected_stages = [
        AgentState.AUTHENTICATE.value,
        AgentState.CLASSIFY_REQUEST.value,
        AgentState.RETRIEVE.value,
        AgentState.EVIDENCE_CURRENCY_CHECKS.value,
        AgentState.GENERATE_OR_ABSTAIN.value,
        AgentState.VALIDATE_CITATIONS.value,
        AgentState.AUDIT.value,
    ]
    for stage in expected_stages:
        assert stage in resp.per_stage_latency_ms, f"Stage {stage} missing from per_stage_latency_ms"
        assert resp.per_stage_latency_ms[stage] >= 0.0

    # Each transition in state_history must have duration_ms recorded
    assert len(resp.state_history) == 7
    for t in resp.state_history:
        assert hasattr(t, "duration_ms")
        assert t.duration_ms >= 0.0


# ── 3. Abstention Reason Capture ──────────────────────────────────────────────

def test_state_machine_captures_abstention_reason(populated_trail_db):
    """Out-of-jurisdiction query must capture explicit abstention_reason on response and transition."""
    agent = BoundedAgentStateMachine(populated_trail_db)
    user = UserContext(clearance_level=Classification.PUBLIC.value)

    resp: AgentResponse = agent.run(
        query="What are the rules promulgated by Punjab Government for DA?",
        user_context=user,
    )

    assert resp.is_no_answer is True
    assert resp.abstention_reason is not None
    assert "jurisdiction" in resp.abstention_reason.lower() or "punjab" in resp.abstention_reason.lower()

    # The terminal transition (AUDIT -> ABSTAINED) must carry the abstention_reason
    terminal_transition = resp.state_history[-1]
    assert terminal_transition.to_state == AgentState.ABSTAINED.value
    assert terminal_transition.abstention_reason is not None


# ── 4. Audit Persistence of Transitions and Latencies ─────────────────────────

def test_audit_table_persists_stage_durations_and_abstention(populated_trail_db):
    """AgentExecutionAudit must record duration_ms and abstention_reason in state_transitions_json."""
    agent = BoundedAgentStateMachine(populated_trail_db)
    user = UserContext(user_id="officer_trail_test", clearance_level=Classification.PUBLIC.value)

    agent.run(
        query="What are the rules of Bihar Government?",
        user_context=user,
    )

    audit_entry = (
        populated_trail_db.query(AgentExecutionAudit)
        .filter(AgentExecutionAudit.user_id == "officer_trail_test")
        .order_by(AgentExecutionAudit.created_at.desc())
        .first()
    )

    assert audit_entry is not None
    assert audit_entry.is_no_answer == 1
    assert audit_entry.state_transitions_json is not None
    assert len(audit_entry.state_transitions_json) > 0

    first_trans = audit_entry.state_transitions_json[0]
    assert "duration_ms" in first_trans
    assert isinstance(first_trans["duration_ms"], (int, float))

    last_trans = audit_entry.state_transitions_json[-1]
    assert last_trans["to"] == AgentState.ABSTAINED.value
    assert "abstention_reason" in last_trans
    assert last_trans["abstention_reason"] is not None


from dataclasses import dataclass, field
from adam.api.deps import get_db


@dataclass
class _LocalStub_Citation:
    document_title: str = "Finance Circular 2024"
    department: str = "FINANCE_TREASURY"
    go_number: str = "GO/2024/101"
    issue_date: str = "2024-01-15"
    page: int = 1
    source_url: str = "https://example.gov.in/go/2024/101"
    pdf_page_link: str = "https://example.gov.in/go/2024/101/page/1"
    version_hash: str = "abc123"
    disclaimer: str = "A citation is a source pointer, not a claim of legal validity."

    def to_dict(self):
        return {
            "document_title": self.document_title,
            "department": self.department,
            "go_number": self.go_number,
            "page": self.page,
            "source_url": self.source_url,
            "pdf_page_link": self.pdf_page_link,
            "version_hash": self.version_hash,
            "disclaimer": self.disclaimer,
        }


@dataclass
class _LocalStub_AgentResponse:
    session_id: str = "sess_test123"
    answer: str = "The allowance rate is 46%."
    citations: list = field(default_factory=lambda: [_LocalStub_Citation()])
    currency_banners: list = field(default_factory=list)
    search_suggestions: list = field(default_factory=list)
    is_no_answer: bool = False
    is_high_risk: bool = False
    is_research_brief: bool = False
    validation_passed: bool = True
    validation_errors: list = field(default_factory=list)
    state_history: list = field(default_factory=list)
    tool_calls: list = field(default_factory=list)
    retrieval_pass_count: int = 1
    answer_pass_count: int = 1
    latency_ms: float = 42.0
    per_stage_latency_ms: dict = field(default_factory=dict)
    abstention_reason: str = None
    prompt_tokens: int = 100
    completion_tokens: int = 50
    model_id: str = "qwen3-4b-instruct-q4"
    temperature_applied: float = 0.0
    applied_schema: str = "ADAM_AGENT_SCHEMA_V1"
    session_summary: dict = None


# ── 5. API SSE Chat Streaming of Trail & Done Events ──────────────────────────

def test_api_chat_emits_trail_event_and_done_metadata():
    """Streaming chat endpoint must emit event: trail and enriched event: done with state_history."""
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    stub = _LocalStub_AgentResponse()
    stub.per_stage_latency_ms = {"AUTHENTICATE": 1.2, "RETRIEVE": 15.4}
    stub.abstention_reason = None
    stub.state_history = [
        AgentStateTransition(
            from_state="AUTHENTICATE",
            to_state="CLASSIFY_REQUEST",
            timestamp="2026-09-21T07:00:00Z",
            notes="Clearance verified",
            duration_ms=1.2,
            stage="AUTHENTICATE",
            abstention_reason=None,
        )
    ]

    with patch("adam.api.routers.chat.AgentStateMachine") as MockClass:
        instance = MagicMock()
        instance.run.return_value = stub
        MockClass.return_value = instance

        resp = client.post(
            "/api/chat",
            json={"query": "Test trail query"},
            headers={"X-User-Id": "officer_1", "X-Clearance-Level": "PUBLIC"},
        )

    assert resp.status_code == 200
    body = resp.text

    # Verify event: trail is emitted
    assert "event: trail" in body
    assert "event: done" in body

    # Parse trail data
    lines = body.split("\n")
    trail_data = None
    done_data = None
    for i, line in enumerate(lines):
        if line == "event: trail":
            for j in range(i + 1, len(lines)):
                if lines[j].startswith("data:"):
                    trail_data = json.loads(lines[j][len("data:"):].strip())
                    break
        elif line == "event: done":
            for j in range(i + 1, len(lines)):
                if lines[j].startswith("data:"):
                    done_data = json.loads(lines[j][len("data:"):].strip())
                    break

    assert trail_data is not None, "event: trail data payload missing"
    assert "state_history" in trail_data
    assert len(trail_data["state_history"]) == 1
    assert trail_data["state_history"][0]["from"] == "AUTHENTICATE"
    assert trail_data["per_stage_latency"]["AUTHENTICATE"] == 1.2

    assert done_data is not None, "event: done data payload missing"
    assert "state_history" in done_data
    assert "per_stage_latency" in done_data


# ── 6. Audit Metrics Endpoint (/audit/metrics) ────────────────────────────────

def test_api_audit_metrics_aggregation(populated_trail_db):
    """GET /api/audit/metrics must calculate average response time and per-stage latency breakdown."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: populated_trail_db
    client = TestClient(app, raise_server_exceptions=False)

    # Seed two sample audits
    audit1 = AgentExecutionAudit(
        session_id="sess_met_1",
        user_id="user_1",
        user_role="OFFICER",
        clearance_level="PUBLIC",
        query_text="Query 1",
        model_id="qwen3-4b-instruct-q4",
        retrieval_pass_count=1,
        answer_pass_count=1,
        is_no_answer=0,
        validation_passed=1,
        latency_ms=100.0,
        state_transitions_json=[
            {"from": "AUTHENTICATE", "to": "CLASSIFY_REQUEST", "duration_ms": 10.0, "stage": "AUTHENTICATE"},
            {"from": "CLASSIFY_REQUEST", "to": "RETRIEVE", "duration_ms": 20.0, "stage": "CLASSIFY_REQUEST"},
        ],
    )
    audit2 = AgentExecutionAudit(
        session_id="sess_met_2",
        user_id="user_2",
        user_role="OFFICER",
        clearance_level="PUBLIC",
        query_text="Query 2",
        model_id="qwen3-4b-instruct-q4",
        retrieval_pass_count=1,
        answer_pass_count=1,
        is_no_answer=1,
        validation_passed=1,
        latency_ms=200.0,
        state_transitions_json=[
            {"from": "AUTHENTICATE", "to": "CLASSIFY_REQUEST", "duration_ms": 14.0, "stage": "AUTHENTICATE"},
            {"from": "CLASSIFY_REQUEST", "to": "RETRIEVE", "duration_ms": 26.0, "stage": "CLASSIFY_REQUEST"},
            {"from": "AUDIT", "to": "ABSTAINED", "duration_ms": 5.0, "stage": "AUDIT", "abstention_reason": "External jurisdiction"},
        ],
    )
    populated_trail_db.add(audit1)
    populated_trail_db.add(audit2)
    populated_trail_db.commit()

    resp = client.get("/api/audit/metrics?limit=10")
    assert resp.status_code == 200
    metrics = resp.json()

    assert metrics["total_executions"] >= 2
    assert metrics["avg_latency_ms"] > 0
    assert "AUTHENTICATE" in metrics["avg_stage_latencies_ms"]
    assert metrics["avg_stage_latencies_ms"]["AUTHENTICATE"] == 12.0  # (10 + 14) / 2
    assert metrics["avg_stage_latencies_ms"]["CLASSIFY_REQUEST"] == 23.0  # (20 + 26) / 2
    assert metrics["abstention_count"] >= 1
    assert "External jurisdiction" in metrics["abstention_reasons"]
