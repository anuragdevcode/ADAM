"""Tests for ADAM's Next-Generation Capability Fabric."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from adam.capabilities import (
    AirGappedSovereigntyViolationError,
    ApprovalBoundaryRequiredError,
    CapabilityDescriptor,
    CapabilityGovernanceEngine,
    CapabilityPermissions,
    CapabilityRegistry,
    CapabilityRouter,
    CapabilitySecurityViolationError,
    CapabilityType,
    CostModel,
    EvidenceStoppingEvaluator,
    InvocationStatus,
    RiskLevel,
    StoppingAssessment,
)
from adam.db.models import Base, Document, DocumentVersion, Source
from adam.rag.models import EvidencePassage, UserContext
from adam.vocabularies import Classification, SourceStatus


@pytest.fixture
def in_memory_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Seed an approved source and document
    source = Source(
        id="src_uk_fin",
        name="Uttarakhand Finance Portal",
        department_id="FINANCE_TREASURY",
        owner_name="Finance Department",
        owner_contact="finance@uk.gov.in",
        written_authority_ref="AUTH-UK-FIN-01",
        status=SourceStatus.APPROVED.value,
        access_classification=Classification.PUBLIC.value,
    )
    doc = Document(
        id="doc_da_order_2024",
        source_id="src_uk_fin",
        title="Finance Order on Dearness Allowance 2024",
        department_id="FINANCE_TREASURY",
        classification=Classification.PUBLIC.value,
        lifecycle_status="ACTIVE",
    )
    version = DocumentVersion(
        id="ver_da_2024",
        document_id="doc_da_order_2024",
        source_url="https://ekosh.uk.gov.in/go/da_2024.pdf",
        sha256="abc123da",
        mime_type="application/pdf",
        byte_size=1024,
        original_object_key="go/da_2024.pdf",
        retrieved_at=datetime.now(timezone.utc),
    )
    session.add_all([source, doc, version])
    session.commit()

    try:
        yield session
    finally:
        session.close()


def test_capability_registry_registration_and_descriptors():
    """Verify all authoritative capabilities are registered with typed schemas and metadata."""
    manifests = CapabilityRegistry.list_capabilities(filter_unavailable=False)
    assert len(manifests) >= 12

    cap_ids = {c["id"] for c in manifests}
    assert "search" in cap_ids
    assert "open_cited_source" in cap_ids
    assert "inspect_system" in cap_ids
    assert "execute_python_sandbox" in cap_ids
    assert "traverse_precedent_dag" in cap_ids
    assert "trace_claim_provenance" in cap_ids
    assert "database_query" in cap_ids
    assert "web_search" in cap_ids
    assert "a2a_dispatch" in cap_ids

    # Verify typed descriptor details for python sandbox
    sandbox_cap = CapabilityRegistry.get("execute_python_sandbox")
    assert sandbox_cap is not None
    assert sandbox_cap.type == CapabilityType.SANDBOX_COMPUTE
    assert sandbox_cap.risk == RiskLevel.MEDIUM
    assert sandbox_cap.is_read_only is True
    assert sandbox_cap.cost.compute_intensity == "MODERATE"
    assert "code" in sandbox_cap.input_model.model_fields


def test_capability_registry_clearance_filtering():
    """Verify clearance levels properly filter available capabilities."""
    public_user = UserContext(
        user_id="citizen_user",
        clearance_level=Classification.PUBLIC.value,
    )
    public_caps = CapabilityRegistry.list_capabilities(user_context=public_user, filter_unavailable=True)
    public_ids = {c["id"] for c in public_caps}
    assert "search" in public_ids
    assert "web_search" in public_ids

    # Classified user under Air-Gapped Data Sovereignty Policy
    restricted_user = UserContext(
        user_id="classified_officer",
        clearance_level=Classification.RESTRICTED.value,
    )
    restricted_caps = CapabilityRegistry.list_capabilities(user_context=restricted_user, filter_unavailable=True)
    restricted_ids = {c["id"] for c in restricted_caps}

    # Internal tools remain accessible
    assert "search" in restricted_ids
    assert "execute_python_sandbox" in restricted_ids
    assert "database_query" in restricted_ids
    assert "traverse_precedent_dag" in restricted_ids

    # Network-requiring tools are strictly barred under air-gap policy
    assert "web_search" not in restricted_ids
    assert "fetch_web_page" not in restricted_ids


def test_air_gapped_policy_enforcement():
    """Verify air-gapped policy blocks execution of network tools directly."""
    restricted_user = UserContext(
        user_id="classified_officer",
        clearance_level=Classification.RESTRICTED.value,
    )
    res = CapabilityRegistry.invoke(
        capability_id="web_search",
        arguments={"query": "national dearness allowance"},
        user_context=restricted_user,
    )
    assert res.status == InvocationStatus.BLOCKED
    assert "Air-Gapped Policy Violation" in res.error


def test_approval_boundary_interception():
    """Verify high-risk or governed capabilities enforce approval boundaries."""
    governed_descriptor = CapabilityDescriptor(
        id="test_governed_action",
        name="Test Governed Action",
        type=CapabilityType.TOOL,
        purpose="Testing approval boundary guard",
        description="Requires approval token to execute",
        when_to_use="Testing only",
        requires_approval=True,
        risk=RiskLevel.HIGH,
    )
    CapabilityRegistry.register(governed_descriptor)

    # 1. Unapproved invocation without token
    res_unapproved = CapabilityRegistry.invoke(
        capability_id="test_governed_action",
        arguments={},
        user_context=UserContext(),
    )
    assert res_unapproved.status == InvocationStatus.APPROVAL_REQUIRED
    assert res_unapproved.requires_approval is True
    assert "Approval Boundary Required" in res_unapproved.approval_prompt

    # 2. Approved invocation with valid approval token
    res_approved = CapabilityRegistry.invoke(
        capability_id="test_governed_action",
        arguments={},
        user_context=UserContext(),
        approval_token="APPROVED:admin_authorization_123",
    )
    # Execution proceeds past approval boundary
    assert res_approved.status != InvocationStatus.APPROVAL_REQUIRED


def test_capability_invocation_dispatch(in_memory_db):
    """Verify unified capability execution dispatch across diverse capability types."""
    user = UserContext(user_id="analyst", clearance_level=Classification.PUBLIC.value)

    # 1. Sandbox calculation capability
    calc_res = CapabilityRegistry.invoke(
        capability_id="execute_python_sandbox",
        arguments={"code": "salary = 50000\nda_rate = 0.50\nresult = salary * da_rate"},
        user_context=user,
        session=in_memory_db,
    )
    assert calc_res.status == InvocationStatus.SUCCESS
    assert calc_res.value["success"] is True
    assert float(calc_res.value["value"]) == 25000.0

    # 2. Database query capability
    db_res = CapabilityRegistry.invoke(
        capability_id="database_query",
        arguments={"table": "documents", "aggregate": "count"},
        user_context=user,
        session=in_memory_db,
    )
    assert db_res.status == InvocationStatus.SUCCESS
    assert db_res.value["result"] >= 1

    # 3. Source comparison capability
    comp_res = CapabilityRegistry.invoke(
        capability_id="compare_sources",
        arguments={
            "source_a": "Order 101 DA is 46% effective Jan 2024",
            "source_b": "Order 102 DA revised to 50% effective July 2024",
        },
        user_context=user,
    )
    assert comp_res.status == InvocationStatus.SUCCESS
    assert "46%" in comp_res.value["source_a_label"] or "summary" in comp_res.value


def test_dynamic_capability_router_selection():
    """Verify CapabilityRouter selects the optimal capability sequence based on query intent."""
    user = UserContext(clearance_level=Classification.PUBLIC.value)

    # Calculation query
    calc_caps = CapabilityRouter.select_capabilities_for_query(
        query="Calculate 50% DA increase on basic pay of 45000",
        user_context=user,
        registry=CapabilityRegistry,
    )
    assert "execute_python_sandbox" in calc_caps
    assert "search" in calc_caps

    # Precedent query
    prec_caps = CapabilityRouter.select_capabilities_for_query(
        query="Which order superseded the 2021 financial rule and trace amendments?",
        user_context=user,
        registry=CapabilityRegistry,
    )
    assert "traverse_precedent_dag" in prec_caps

    # System introspection query
    intro_caps = CapabilityRouter.select_capabilities_for_query(
        query="What active model and harness profile is ADAM running?",
        user_context=user,
        registry=CapabilityRegistry,
    )
    assert intro_caps == ["inspect_system"]


def test_evidence_stopping_evaluator():
    """Verify EvidenceStoppingEvaluator detects evidence convergence and halts early."""
    # 1. Zero passages -> cannot stop
    assess_empty = EvidenceStoppingEvaluator.evaluate(
        query="What is the revised DA rate?",
        accumulated_passages=[],
    )
    assert assess_empty.can_stop is False

    # 2. Strong local passages -> can stop early
    strong_passages = [
        EvidencePassage(
            chunk_id="c1",
            document_id="doc1",
            version_id="v1",
            title="Finance Order 2024",
            department_id="FINANCE_TREASURY",
            doc_type="GOVERNMENT_ORDER",
            page_start=1,
            page_end=1,
            section_heading="Sanction",
            content="The Governor is pleased to sanction Dearness Allowance at the rate of 50% of Basic Pay with effect from 01-01-2024.",
            score=0.75,
        ),
        EvidencePassage(
            chunk_id="c2",
            document_id="doc1",
            version_id="v1",
            title="Finance Order 2024",
            department_id="FINANCE_TREASURY",
            doc_type="GOVERNMENT_ORDER",
            page_start=2,
            page_end=2,
            section_heading="Applicability",
            content="Applicable to all regular state government employees across Uttarakhand departments.",
            score=0.60,
        ),
    ]

    assess_converged = EvidenceStoppingEvaluator.evaluate(
        query="What is the revised DA rate for Uttarakhand employees?",
        accumulated_passages=strong_passages,
    )
    assert assess_converged.can_stop is True
    assert assess_converged.confidence >= 0.85
    assert "converged" in assess_converged.reason.lower() or "sufficient" in assess_converged.reason.lower()


def test_api_capabilities_endpoints(in_memory_db):
    """Test REST API /system/capabilities endpoints."""
    from fastapi.testclient import TestClient
    from adam.api.app import app
    from adam.api.deps import get_db

    app.dependency_overrides[get_db] = lambda: in_memory_db
    client = TestClient(app)

    # 1. GET /api/system/capabilities for PUBLIC user
    resp_pub = client.get("/api/system/capabilities", headers={"X-Clearance-Level": "PUBLIC"})
    assert resp_pub.status_code == 200
    data_pub = resp_pub.json()
    assert data_pub["total_available"] >= 10
    names = {c["id"] for c in data_pub["capabilities"]}
    assert "web_search" in names

    # 2. GET /api/system/capabilities for RESTRICTED user (Air-Gapped)
    resp_restr = client.get("/api/system/capabilities", headers={"X-Clearance-Level": "RESTRICTED"})
    assert resp_restr.status_code == 200
    data_restr = resp_restr.json()
    restr_names = {c["id"] for c in data_restr["capabilities"]}
    assert "web_search" not in restr_names
    assert "search" in restr_names

    # 3. GET /api/system/capabilities/{id}
    resp_detail = client.get("/api/system/capabilities/execute_python_sandbox")
    assert resp_detail.status_code == 200
    detail = resp_detail.json()
    assert detail["id"] == "execute_python_sandbox"
    assert detail["risk_level"] == "MEDIUM"

    app.dependency_overrides.clear()
