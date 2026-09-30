"""Tests for Agent-to-Agent (A2A) Protocol Layer and Specialist Agents."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adam.capabilities.a2a import (
    A2ABudget,
    A2ARecursionError,
    A2AResponseEnvelope,
    A2ASpecialistCoordinator,
    A2ATaskContract,
    A2ATaskStatus,
    ComplianceAuditSpecialist,
    PrecedentGraphSpecialist,
    QuantitativeAnalysisSpecialist,
    WebResearchSpecialist,
)
from adam.db.models import Base, Document, DocumentVersion, PrecedentReference
from adam.rag.models import UserContext
from adam.vocabularies import Classification


@pytest.fixture
def a2a_test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    d202 = Document(id="doc_202", title="Order 202", department_id="FINANCE_TREASURY")
    d303 = Document(id="doc_303", title="Order 303", department_id="FINANCE_TREASURY")
    v202 = DocumentVersion(
        id="ver_202",
        document_id="doc_202",
        source_url="https://ekosh.uk.gov.in/go_202.pdf",
        sha256="sha202",
        mime_type="application/pdf",
        byte_size=1024,
        original_object_key="go/go_202.pdf",
        retrieved_at=datetime.now(timezone.utc),
    )
    v303 = DocumentVersion(
        id="ver_303",
        document_id="doc_303",
        source_url="https://ekosh.uk.gov.in/go_303.pdf",
        sha256="sha303",
        mime_type="application/pdf",
        byte_size=1024,
        original_object_key="go/go_303.pdf",
        retrieved_at=datetime.now(timezone.utc),
    )
    # Seed precedent references: Order 101 SUPERSEDED by Order 202
    p1 = PrecedentReference(
        id="ref_101_to_202",
        source_version_id="ver_202",
        raw_citation_text="In supersession of GO-101/FIN/2020",
        relation_type="SUPERSEDES",
        cited_order_number="GO-101/FIN/2020",
        cited_date=datetime(2020, 1, 15, tzinfo=timezone.utc).date(),
    )
    # Order 202 AMENDED by Order 303
    p2 = PrecedentReference(
        id="ref_202_to_303",
        source_version_id="ver_303",
        raw_citation_text="Amending GO-202/FIN/2022",
        relation_type="AMENDS",
        cited_order_number="GO-202/FIN/2022",
        cited_date=datetime(2022, 6, 1, tzinfo=timezone.utc).date(),
    )
    session.add_all([d202, d303, v202, v303, p1, p2])
    session.commit()

    try:
        yield session
    finally:
        session.close()


def test_a2a_task_contract_validation():
    """Verify typed contract creation and boundary validation."""
    contract = A2ATaskContract(
        specialist_agent_id="quantitative_analysis",
        objective="Verify revised basic pay formula",
        input_artifacts={"code": "res = 40000 * 1.5"},
        clearance_level=Classification.PUBLIC.value,
        budget=A2ABudget(max_duration_seconds=5.0, max_depth=1),
    )
    assert contract.task_id.startswith("a2a_")
    assert contract.depth == 1
    assert contract.budget.max_depth == 1


def test_a2a_recursion_depth_limit():
    """Verify that specialist agents strictly reject depth > 1 (no runaway recursion)."""
    contract_invalid_depth = A2ATaskContract(
        specialist_agent_id="quantitative_analysis",
        objective="Spawn grandchild agent",
        input_artifacts={"code": "res = 1 + 1"},
        depth=2,  # Exceeds max_depth = 1
        budget=A2ABudget(max_depth=1),
    )

    specialist = QuantitativeAnalysisSpecialist(session=None, user_context=UserContext())
    with pytest.raises(A2ARecursionError) as exc_info:
        specialist.execute(contract_invalid_depth)
    assert "depth 2 exceeds limit 1" in str(exc_info.value)


def test_a2a_specialist_coordinator_limits(a2a_test_db):
    """Verify coordinator limits concurrent specialist dispatches per session."""
    coord = A2ASpecialistCoordinator(session=a2a_test_db, user_context=UserContext())
    assert coord.MAX_CONCURRENT_SPECIALISTS == 2

    # 1. Dispatch 1st specialist
    c1 = A2ATaskContract(
        specialist_agent_id="quantitative_analysis",
        objective="Calc 1",
        input_artifacts={"code": "result = 10 * 10"},
    )
    res1 = coord.dispatch(c1)
    assert res1.status == A2ATaskStatus.SUCCESS

    # 2. Dispatch 2nd specialist
    c2 = A2ATaskContract(
        specialist_agent_id="quantitative_analysis",
        objective="Calc 2",
        input_artifacts={"code": "result = 20 * 20"},
    )
    res2 = coord.dispatch(c2)
    assert res2.status == A2ATaskStatus.SUCCESS

    # 3. Dispatch 3rd specialist -> must be blocked by quota
    c3 = A2ATaskContract(
        specialist_agent_id="quantitative_analysis",
        objective="Calc 3",
        input_artifacts={"code": "result = 30 * 30"},
    )
    res3 = coord.dispatch(c3)
    assert res3.status == A2ATaskStatus.ABSTAINED
    assert "quota reached" in res3.summary


def test_precedent_graph_specialist(a2a_test_db):
    """Verify PrecedentGraphSpecialist traverses DAG and identifies supersessions."""
    specialist = PrecedentGraphSpecialist(session=a2a_test_db, user_context=UserContext())

    contract = A2ATaskContract(
        specialist_agent_id="precedent_graph",
        objective="Trace order status",
        input_artifacts={"order_number": "GO-101/FIN/2020"},
    )
    res = specialist.execute(contract)
    assert res.status == A2ATaskStatus.SUCCESS
    assert "Precedent Analysis" in res.summary
    assert len(res.structured_findings) >= 1
    finding = res.structured_findings[0]
    assert finding["query_order"] == "GO-101/FIN/2020"


def test_quantitative_analysis_specialist():
    """Verify QuantitativeAnalysisSpecialist executes arithmetic in Python sandbox."""
    specialist = QuantitativeAnalysisSpecialist(session=None, user_context=UserContext())

    contract = A2ATaskContract(
        specialist_agent_id="quantitative_analysis",
        objective="Calculate HRA allowance",
        input_artifacts={"code": "basic = 60000\nhra_rate = 0.27\nresult = basic * hra_rate"},
    )
    res = specialist.execute(contract)
    assert res.status == A2ATaskStatus.SUCCESS
    assert "16200.0" in res.summary
    assert len(res.structured_findings) >= 1
    assert round(res.structured_findings[0]["value"], 2) == 16200.0


def test_web_research_specialist_air_gap_denial():
    """Verify WebResearchSpecialist refuses external research under classified clearance."""
    restricted_user = UserContext(
        user_id="secret_operator",
        clearance_level=Classification.RESTRICTED.value,
    )
    specialist = WebResearchSpecialist(session=None, user_context=restricted_user)

    contract = A2ATaskContract(
        specialist_agent_id="web_research",
        objective="Search central government policy",
        input_artifacts={"query": "central 7th CPC"},
        clearance_level=Classification.RESTRICTED.value,
    )
    res = specialist.execute(contract)
    assert res.status == A2ATaskStatus.FAILED
    assert "Air-Gapped Data Sovereignty Policy" in res.summary
