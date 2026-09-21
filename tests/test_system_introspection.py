"""Comprehensive unit tests for ADAM System Introspection & Self-Model Layer."""

import pytest
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from adam.agent.introspection import (
    SystemIntrospectionService,
    SystemSnapshot,
)
from adam.agent.redaction import SecretRedactor
from adam.harness.templates import PromptTemplateRegistry
from adam.agent.state_machine import BoundedAgentStateMachine
from adam.db.models import Base, AgentExecutionAudit
from adam.rag.models import UserContext
from adam.rag.query import QueryUnderstanding
from adam.vocabularies import Classification, AgentState


# ── Database & Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def test_db_session():
    """In-memory SQLite session with StaticPool."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_api_client(test_db_session):
    """FastAPI TestClient with overridden get_db."""
    from adam.api.app import create_app
    from adam.api import deps

    app = create_app()

    def override_get_db():
        yield test_db_session

    app.dependency_overrides[deps.get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


# ── 1. System Introspection Service & Snapshots ──────────────────────────────

def test_system_introspection_service_snapshot(test_db_session):
    """Verify live system snapshot collects authoritative data from registries."""
    snapshot = SystemIntrospectionService.get_system_snapshot(
        session=test_db_session,
        session_id="test_session_001",
        user_id="officer_test",
        clearance_level="PUBLIC",
    )

    assert isinstance(snapshot, SystemSnapshot)
    assert snapshot.system_info.name == "ADAM"
    assert snapshot.system_info.air_gapped is False

    # Active model
    assert snapshot.model.id is not None
    assert snapshot.model.serving_runtime in ("deterministic", "ollama", "gemini", "llamacpp")

    # Active harness
    assert snapshot.harness.profile_name is not None
    assert 0.0 <= snapshot.harness.temperature_range[0] <= snapshot.harness.temperature_range[1] <= 0.2

    # Tools: verify read-only tools allowed and dangerous tools forbidden
    allowed_names = [t["name"] for t in snapshot.tools.allowed_tools]
    assert "search" in allowed_names or "public_records_search" in allowed_names
    assert any("browse" in t or "web" in t for t in snapshot.tools.forbidden_capabilities)
    assert any("bash" in t or "command" in t for t in snapshot.tools.forbidden_capabilities)
    assert any("db" in t or "write" in t for t in snapshot.tools.forbidden_capabilities)

    # Data sources
    assert isinstance(snapshot.data_sources.approved_connectors, list)

    # Worker concurrency
    assert snapshot.workers.max_concurrent_heavy_tasks >= 1


# ── 2. Secret Redaction & Sanitization ────────────────────────────────────────

def test_secret_redaction_and_sanitization(test_db_session):
    """Verify secrets (API keys, DB credentials, filesystem paths) are stripped."""
    # Test redactor directly
    raw_text = (
        "Using key AIzaSyD9876543210ABCDEF123456 and connection "
        "postgresql://postgres:mySecretPass123@localhost:5432/adam_db "
        "and path /Users/secretuser/private/secrets.env"
    )
    redacted = SecretRedactor.sanitize_text(raw_text)
    assert "AIzaSyD9876543210ABCDEF123456" not in redacted
    assert "mySecretPass123" not in redacted
    assert "[REDACTED_API_KEY]" in redacted
    assert "[REDACTED_PASSWORD]" in redacted

    # Test snapshot sanitization
    snapshot = SystemIntrospectionService.get_system_snapshot(
        session=test_db_session,
        session_id="test_sess",
    )
    sanitized = SystemIntrospectionService.sanitize_snapshot(snapshot)
    assert isinstance(sanitized, dict)

    # Verify no raw sensitive keys
    keys_str = str(sanitized)
    assert "mySecretPass" not in keys_str
    assert "AIzaSy" not in keys_str


# ── 3. Prompt Formatting ─────────────────────────────────────────────────────

def test_system_introspection_prompt_formatting(test_db_session):
    """Verify formatted snapshot for prompt contains authoritative markers and sections."""
    snapshot = SystemIntrospectionService.get_system_snapshot(
        session=test_db_session,
        session_id="test_sess",
    )

    # Model subtopic
    model_prompt = SystemIntrospectionService.format_snapshot_for_prompt(snapshot, "MODEL")
    assert "### Active Model & Runtime" in model_prompt
    assert "**Active Model**:" in model_prompt
    assert "**Serving Runtime**:" in model_prompt

    turn_prompt = PromptTemplateRegistry.format_introspection_turn("What model?", model_prompt)
    assert "=== AUTHORITATIVE SYSTEM STATE SNAPSHOT ===" in turn_prompt

    # Tools subtopic
    tools_prompt = SystemIntrospectionService.format_snapshot_for_prompt(snapshot, "TOOLS")
    assert "**Authorized Read-Only Tools**:" in tools_prompt
    assert "**Forbidden Capabilities" in tools_prompt

    # Sources subtopic
    sources_prompt = SystemIntrospectionService.format_snapshot_for_prompt(snapshot, "SOURCES")
    assert "**Approved Sources Count**:" in sources_prompt


# ── 4. Query Understanding Classification ─────────────────────────────────────

def test_query_classification_introspection_all_subtopics():
    """Verify QueryUnderstanding accurately classifies introspection queries across all subtopics."""
    test_cases = [
        # MODEL
        ("What model are you using?", True, "MODEL"),
        ("Which LLM is running right now?", True, "MODEL"),
        ("What is your active model and runtime?", True, "MODEL"),
        ("सक्रिय मॉडल क्या है?", True, "MODEL"),
        # TOOLS
        ("What tools do you have?", True, "TOOLS"),
        ("Which tools are available to you?", True, "TOOLS"),
        ("Can you browse the web?", True, "TOOLS"),
        ("Can you run bash commands or scripts?", True, "TOOLS"),
        ("List your available tools", True, "TOOLS"),
        ("क्या आप वेब खोज सकते हैं?", True, "TOOLS"),
        # SOURCES
        ("What data sources are available?", True, "SOURCES"),
        ("Which data sources are indexed?", True, "SOURCES"),
        ("What collections can you search?", True, "SOURCES"),
        ("स्वीकृत डेटा स्रोत क्या हैं?", True, "SOURCES"),
        # HARNESS
        ("What is your active harness profile?", True, "HARNESS"),
        ("What temperature do you use?", True, "HARNESS"),
        # LAST_EXECUTION
        ("Why was my last request refused?", True, "LAST_EXECUTION"),
        ("Why did you refuse my previous query?", True, "LAST_EXECUTION"),
        ("Explain your last refusal", True, "LAST_EXECUTION"),
        # CURRENT_STATUS
        ("What are you doing right now?", True, "CURRENT_STATUS"),
        ("What is the system status?", True, "CURRENT_STATUS"),
        # Non-introspection: public records queries
        ("What is the dearness allowance rate under UK/FIN/2023/101?", False, None),
        ("Show procurement guidelines for Uttarakhand", False, None),
        ("वित्तीय स्वीकृति की सीमा क्या है?", False, None),
        # Non-introspection: standard greetings
        ("hi", False, None),
        ("namaste", False, None),
        ("capabilities", False, None),
        ("what can you do", False, None),
    ]

    for q, expected_intro, expected_subtopic in test_cases:
        parsed = QueryUnderstanding.parse(q)
        assert parsed.is_system_introspection == expected_intro, (
            f"Query '{q}': expected is_system_introspection={expected_intro}, got {parsed.is_system_introspection}"
        )
        if expected_intro:
            assert parsed.introspection_subtopic == expected_subtopic, (
                f"Query '{q}': expected subtopic={expected_subtopic}, got {parsed.introspection_subtopic}"
            )


# ── 5. Agent State Machine: Introspection Execution ───────────────────────────

def test_agent_state_machine_introspection_model_query(test_db_session):
    """Verify AgentStateMachine handles model introspection query end-to-end."""
    agent = BoundedAgentStateMachine(test_db_session)
    user = UserContext(
        user_id="officer_introspection_test",
        roles=["OFFICER"],
        clearance_level=Classification.PUBLIC.value,
    )

    response = agent.run(
        query="What model and runtime are you currently using?",
        user_context=user,
    )

    assert response.state_history[-1].to_state == AgentState.COMPLETED.value
    assert response.is_no_answer is False
    assert len(response.answer) > 0
    # Answer should ground on the active model
    assert any(term in response.answer.lower() for term in ["model", "runtime", "deterministic", "qwen", "gemini"])
    assert response.validation_passed is True

    # Check audit record
    audit_rec = test_db_session.query(AgentExecutionAudit).filter(
        AgentExecutionAudit.session_id == response.session_id
    ).first()
    assert audit_rec is not None
    assert "SYSTEM_INTROSPECTION" in audit_rec.detected_intent


def test_agent_state_machine_introspection_tools_query(test_db_session):
    """Verify AgentStateMachine answers tool introspection accurately."""
    agent = BoundedAgentStateMachine(test_db_session)
    user = UserContext(
        user_id="officer_introspection_test",
        roles=["OFFICER"],
        clearance_level=Classification.PUBLIC.value,
    )

    response = agent.run(
        query="What tools do you have and can you browse the web?",
        user_context=user,
    )

    assert response.state_history[-1].to_state == AgentState.COMPLETED.value
    assert response.is_no_answer is False
    # Answer should mention read-only tools and forbidden capabilities
    ans_lower = response.answer.lower()
    assert "search" in ans_lower or "read-only" in ans_lower
    assert "forbidden" in ans_lower or "cannot" in ans_lower or "web" in ans_lower


# ── 6. Agent State Machine: Refusal Diagnosis ─────────────────────────────────

def test_agent_state_machine_refusal_diagnosis_flow(test_db_session):
    """Verify turn-by-turn refusal diagnosis without self-refusal."""
    agent = BoundedAgentStateMachine(test_db_session)
    user = UserContext(
        user_id="officer_diag_test",
        roles=["OFFICER"],
        clearance_level=Classification.PUBLIC.value,
    )
    chat_sess = agent.session_manager.create_session(
        user_id=user.user_id,
        classification_ceiling=user.clearance_level,
    )
    session_id = chat_sess.id

    # Turn 1: Query outside Uttarakhand jurisdiction
    res1 = agent.run(
        query="What are the electricity regulations in Himachal Pradesh?",
        user_context=user,
        session_id=session_id,
    )
    assert res1.is_no_answer is True

    # Turn 2: Ask why the previous query was refused
    res2 = agent.run(
        query="Why was my last request refused?",
        user_context=user,
        session_id=session_id,
    )
    # Turn 2 itself must NOT be refused
    assert res2.is_no_answer is False
    assert res2.state_history[-1].to_state == AgentState.COMPLETED.value
    # Turn 2 answer should explain the previous refusal
    ans_lower = res2.answer.lower()
    assert any(term in ans_lower for term in ["refuse", "jurisdiction", "himachal", "state", "outside", "uttarakhand"])


# ── 7. REST API Endpoints ─────────────────────────────────────────────────────

def test_api_system_introspection_endpoint(test_api_client):
    """Verify GET /api/system/introspection returns sanitized snapshot."""
    response = test_api_client.get("/api/system/introspection?clearance_level=PUBLIC")
    assert response.status_code == 200
    data = response.json()

    assert "system_info" in data
    assert "active_model" in data
    assert "active_harness" in data
    assert "tool_capabilities" in data
    assert "data_sources" in data
    assert "worker_concurrency" in data
    assert "last_execution" in data

    assert data["system_info"]["name"] == "ADAM"
    assert "allowed_tools" in data["tool_capabilities"]
    assert "forbidden_tools" in data["tool_capabilities"]


def test_api_system_introspection_last_execution_endpoint(test_api_client, test_db_session):
    """Verify GET /api/system/introspection/last-execution endpoint."""
    # Seed an execution audit
    audit = AgentExecutionAudit(
        id="audit_api_test_01",
        session_id="sess_api_diag_01",
        user_id="officer_api_test",
        query_text="What are electricity tariffs in Punjab?",
        detected_intent="JURISDICTION_REFUSAL",
        retrieval_pass_count=1,
        answer_pass_count=1,
        latency_ms=25.0,
        validation_passed=1,
        is_no_answer=1,
        state_transitions_json=[
            {
                "stage": "generation",
                "duration_ms": 15.0,
                "abstention_reason": "Out of jurisdiction: query targets Punjab",
            }
        ],
    )
    test_db_session.add(audit)
    test_db_session.commit()

    response = test_api_client.get(
        "/api/system/introspection/last-execution?session_id=sess_api_diag_01"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "sess_api_diag_01"
    assert data["was_refused"] is True
    assert "Punjab" in data["refusal_reason"]
