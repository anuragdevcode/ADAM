"""Tests for ADAM Agentic Problem-Solving and Reasoning Layer.

Covers:
1. SecurePythonSandbox: AST security enforcement, safe execution, timeout, forbidden calls.
2. AgenticPlanner: Query complexity classification, problem decomposition, sub-problem budgets.
3. CitationValidator: Grounding verification of derived mathematical numbers.
4. AgenticOrchestrator & AgentStateMachine: Dynamic execution, tool integration, audit trail.
"""

import pytest
from datetime import date
from sqlalchemy.orm import Session

from adam.agent.planner import (
    AgentExecutionPlan,
    AgenticPlanner,
    PlanStep,
    StepStatus,
    TaskComplexity,
)
from adam.agent.sandbox import (
    SandboxSecurityError,
    SandboxTimeoutError,
    SecurePythonSandbox,
)
from adam.agent.state_machine import BoundedAgentStateMachine
from adam.db.models import (
    AgentExecutionAudit,
    AuditEvent,
    Document,
    DocumentChunk,
    DocumentVersion,
)
from adam.rag.generator import CitationValidator
from adam.rag.models import (
    Citation,
    EvidencePacket,
    EvidencePassage,
    ParsedQuery,
    UserContext,
)
from adam.vocabularies import (
    AgentState,
    AgentToolName,
    Classification,
    DepartmentId,
    DocType,
    LifecycleStatus,
    ReviewStatus,
)


# ── 1. Secure Python Sandbox Tests ──────────────────────────────────────────

def test_sandbox_safe_arithmetic_and_math():
    """Verify safe arithmetic, percentages, and math functions execute accurately."""
    sandbox = SecurePythonSandbox(timeout_seconds=2.0)
    code = """
basic_pay = 45000.0
da_rate = 0.04
increase = basic_pay * da_rate
new_salary = basic_pay + increase
print(f"Increase: {increase}")
new_salary
"""
    res = sandbox.execute(code)
    assert res.success is True
    assert res.value == 46800.0
    assert "Increase: 1800.0" in res.output


def test_sandbox_datetime_and_decimal():
    """Verify safe decimal and datetime calculations."""
    sandbox = SecurePythonSandbox(timeout_seconds=2.0)
    code = """
rate = Decimal('0.04')
salary = Decimal('45000.00')
increase = salary * rate
increase
"""
    res = sandbox.execute(code)
    assert res.success is True
    assert float(res.value) == 1800.0


def test_sandbox_blocks_os_import():
    """Verify that importing os is intercepted and blocked by AST validator."""
    sandbox = SecurePythonSandbox(timeout_seconds=2.0)
    code = "import os\nos.listdir('.')"
    res = sandbox.execute(code)
    assert res.success is False
    assert "forbidden" in res.error.lower()


def test_sandbox_blocks_sys_and_subprocess():
    """Verify that subprocess and sys imports are blocked."""
    sandbox = SecurePythonSandbox(timeout_seconds=2.0)
    res1 = sandbox.execute("import sys")
    assert res1.success is False
    assert "forbidden" in res1.error.lower()

    res2 = sandbox.execute("import subprocess")
    assert res2.success is False
    assert "forbidden" in res2.error.lower()


def test_sandbox_blocks_dunder_attributes():
    """Verify that accessing dunder attributes like __globals__ or __builtins__ is blocked."""
    sandbox = SecurePythonSandbox(timeout_seconds=2.0)
    code = "().__class__.__bases__[0].__subclasses__()"
    res = sandbox.execute(code)
    assert res.success is False
    assert "forbidden" in res.error.lower()


def test_sandbox_blocks_banned_builtin_calls():
    """Verify that open, eval, exec calls are rejected."""
    sandbox = SecurePythonSandbox(timeout_seconds=2.0)
    code = "open('/etc/passwd', 'r')"
    res = sandbox.execute(code)
    assert res.success is False
    assert "prohibited" in res.error.lower()


def test_sandbox_timeout_on_infinite_loop():
    """Verify that infinite loops are halted cleanly by thread timeout."""
    sandbox = SecurePythonSandbox(timeout_seconds=0.5)
    code = """
x = 0
while True:
    x += 1
"""
    res = sandbox.execute(code)
    assert res.success is False
    assert "timed out" in res.error.lower()


# ── 2. Agentic Planner & Problem Decomposition Tests ────────────────────────

def test_planner_direct_lookup_classification():
    """Verify direct lookup queries bypass multi-step planning."""
    q = "What is the procurement limit for IT equipment under UK/FIN/2023/101?"
    plan = AgenticPlanner.create_plan(q)
    assert plan.complexity == TaskComplexity.DIRECT_LOOKUP
    assert plan.is_direct_lookup is True
    assert len(plan.steps) == 2
    assert plan.steps[0].action_type == "search"


def test_planner_quantitative_computation_decomposition():
    """Verify calculation queries decompose into retrieve, compute, and synthesize."""
    q = "If basic pay is 45000, calculate the revised salary after 4% DA increase under UK/FIN/2024/101."
    plan = AgenticPlanner.create_plan(q)
    assert plan.complexity == TaskComplexity.QUANTITATIVE_COMPUTATION
    assert plan.is_direct_lookup is False
    assert len(plan.steps) >= 3
    action_types = [s.action_type for s in plan.steps]
    assert "search" in action_types
    assert "compute" in action_types
    assert "synthesize" in action_types


def test_planner_precedent_tracking_decomposition():
    """Verify precedent tracing queries decompose into search, precedent lookup, and synthesis."""
    q = "Trace precedent chain and superseding orders for UK/FIN/2020/12."
    plan = AgenticPlanner.create_plan(q)
    assert plan.complexity == TaskComplexity.PRECEDENT_TRACKING
    assert plan.is_direct_lookup is False
    action_types = [s.action_type for s in plan.steps]
    assert "search" in action_types
    assert "precedent" in action_types
    assert "synthesize" in action_types


def test_planner_comparative_analysis_decomposition():
    """Verify comparative queries formulate comparative sub-problems."""
    q = "Compare the differences between the 2021 and 2024 financial sanction limits."
    plan = AgenticPlanner.create_plan(q)
    assert plan.complexity in (TaskComplexity.MULTI_STEP_ANALYSIS, TaskComplexity.COMPARATIVE_RESEARCH)
    assert plan.is_direct_lookup is False
    assert len(plan.steps) >= 2


def test_planner_enforces_maximum_budget_limits():
    """Verify planner enforces strict step bounds (max 6 steps)."""
    q = "Compare order 1, compare order 2, calculate salary for 50000, trace precedent chain, and verify rules."
    plan = AgenticPlanner.create_plan(q)
    assert len(plan.steps) <= AgenticPlanner.MAX_STEPS


# ── 3. Citation Validation for Derived Mathematical Calculations ────────────

def test_citation_validator_accepts_verified_sandbox_calculations():
    """Derived calculations from sandbox should be recognized as grounded, not hallucinations."""
    query = ParsedQuery(raw_query="Calculate new salary for 45000", clean_query="Calculate new salary for 45000")
    passage = EvidencePassage(
        chunk_id="chk_01",
        document_id="doc_da",
        version_id="ver_01",
        title="Sanction Order 2024",
        department_id="FINANCE",
        doc_type="GO",
        page_start=1,
        page_end=1,
        section_heading="Sanction Clause",
        content="The Governor approved 4% increase in Dearness Allowance.",
    )
    packet = EvidencePacket(query=query, passages=[passage])

    # Answer contains derived number 46,800 which is not in passage, but verified in calculation
    answer = "Based on [1], with a 4% DA increase, the monthly increase is ₹1,800 and the revised salary is ₹46,800."
    verified_calculations = [
        {
            "code": "basic = 45000; inc = 1800; total = 46800",
            "value": 46800.0,
            "output": "Increase: 1800, Total: 46800",
            "formatted": "₹46,800.00",
        }
    ]

    passed, errors = CitationValidator.validate(
        answer=answer,
        packet=packet,
        verified_calculations=verified_calculations,
    )
    assert passed is True
    assert len(errors) == 0


# ── 4. End-to-End State Machine Integration with Agentic Problem Solving ────

@pytest.fixture
def agentic_test_db(db_session):
    """Seed test database with an official GO containing DA rates."""
    doc = Document(
        id="doc_fin_da_2024_agentic",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        title="Sanction of 4% Dearness Allowance for Uttarakhand State Employees 2024",
        classification=Classification.PUBLIC.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    db_session.add(doc)

    ver = DocumentVersion(
        id="ver_fin_da_2024_agentic",
        document_id="doc_fin_da_2024_agentic",
        source_url="https://ekosh.uk.gov.in/orders/da2024_agentic.pdf",
        sha256="hash_da_2024_agentic_sha256",
        mime_type="application/pdf",
        byte_size=12000,
        go_number="UK/FIN/2024/202",
        original_object_key="originals/test_da_2024_agentic.pdf",
    )
    db_session.add(ver)

    chk = DocumentChunk(
        id="chk_fin_da_2024_agentic_01",
        document_id="doc_fin_da_2024_agentic",
        version_id="ver_fin_da_2024_agentic",
        chunk_index=0,
        content="Under order UK/FIN/2024/202 dated 15/01/2024, the Governor of Uttarakhand sanctions a 4% increase in Dearness Allowance.",
        page_start=1,
        page_end=1,
        section_heading="Sanction Clause",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        classification=Classification.PUBLIC.value,
        go_number="UK/FIN/2024/202",
        order_date=date(2024, 1, 15),
        source_url="https://ekosh.uk.gov.in/orders/da2024_agentic.pdf",
        sha256="hash_da_2024_agentic_sha256",
        review_status=ReviewStatus.AUTO_APPROVED.value,
    )
    db_session.add(chk)
    db_session.commit()
    return db_session


def test_agent_state_machine_executes_agentic_calculation(agentic_test_db):
    """Verify that a calculation query triggers Agentic reasoning, executes sandbox math,
    and returns verified calculation results and plan in AgentResponse.
    """
    agent = BoundedAgentStateMachine(agentic_test_db)
    user = UserContext(
        user_id="officer_agentic_test",
        roles=["OFFICER"],
        department_id=DepartmentId.FINANCE_TREASURY.value,
        clearance_level=Classification.PUBLIC.value,
    )

    query = "If basic pay is 45000, calculate the monthly increase under order UK/FIN/2024/202."
    response = agent.run(query=query, user_context=user)

    # Response validations
    assert response.plan is not None
    assert response.plan.get("is_direct_lookup") is False
    assert response.plan.get("complexity") == TaskComplexity.QUANTITATIVE_COMPUTATION.value
    assert len(response.computation_results) >= 1
    # Check that calculation proof is present
    calc = response.computation_results[0]
    assert calc.get("value") is not None

    # State transitions must include agentic stages
    state_names = [t.to_state for t in response.state_history]
    assert AgentState.PLAN.value in state_names
    assert AgentState.EXECUTE_STEP.value in state_names
    assert AgentState.VERIFY_INTERMEDIATE.value in state_names
    assert AgentState.SYNTHESIZE.value in state_names
    assert response.state_history[-1].to_state == AgentState.COMPLETED.value

    # Check audit log
    audit_rec = agentic_test_db.query(AgentExecutionAudit).filter(
        AgentExecutionAudit.session_id == response.session_id
    ).first()
    assert audit_rec is not None
    assert "AGENTIC" in audit_rec.detected_intent
    assert len(audit_rec.tool_calls_json) >= 1


def test_agent_state_machine_fast_path_backward_compatibility(agentic_test_db):
    """Verify direct lookup continues to run through the standard 7-stage pipeline."""
    agent = BoundedAgentStateMachine(agentic_test_db)
    user = UserContext(
        user_id="officer_fast_path_test",
        roles=["OFFICER"],
        department_id=DepartmentId.FINANCE_TREASURY.value,
        clearance_level=Classification.PUBLIC.value,
    )

    query = "What is the Dearness Allowance rate under order UK/FIN/2024/202?"
    response = agent.run(query=query, user_context=user)

    assert response.plan is not None
    assert response.plan.get("is_direct_lookup") is True
    # Fast path has exactly 7 transitions
    assert len(response.state_history) == 7
    expected_transitions = [
        (AgentState.AUTHENTICATE.value, AgentState.CLASSIFY_REQUEST.value),
        (AgentState.CLASSIFY_REQUEST.value, AgentState.RETRIEVE.value),
        (AgentState.RETRIEVE.value, AgentState.EVIDENCE_CURRENCY_CHECKS.value),
        (AgentState.EVIDENCE_CURRENCY_CHECKS.value, AgentState.GENERATE_OR_ABSTAIN.value),
        (AgentState.GENERATE_OR_ABSTAIN.value, AgentState.VALIDATE_CITATIONS.value),
        (AgentState.VALIDATE_CITATIONS.value, AgentState.AUDIT.value),
        (AgentState.AUDIT.value, AgentState.COMPLETED.value),
    ]
    assert [(t.from_state, t.to_state) for t in response.state_history] == expected_transitions
