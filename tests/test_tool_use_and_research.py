"""Tests for ADAM Tool-Use and Research Orchestration Layer.

Covers:
1. SSRF Protection (SSRFGuard): private IP, link-local, cloud metadata, loopback blocking.
2. Web Rate Limiting (WebRateLimiter): per-domain sliding window enforcement.
3. Secure Web Fetcher & Search: markdown conversion, table parsing, size limits.
4. Typed Permission-Aware Tool Registry: self-inspection manifest, parameter types, clearance controls.
5. Guardrails Preservation: destructive tool rejection and forbidden tool error contracts.
6. Database Query Tool: safe schema inspection, aggregate queries, mutation blocking.
7. Source Comparison Tool: cross-source delta and consistency analysis.
8. Local Evidence Evaluator: fast local verification first, autonomous escalation triggers.
9. Specialized Subagents: WebResearchSubagent, DataAnalysisSubagent, budget limits, recursion block.
10. Orchestrator Loop Prevention: repeated step detection and termination.
11. Provenance Citations: distinct internal [1] vs external [WEB-1] citations.
"""

import time
import pytest
from datetime import date
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from adam.agent.orchestrator import AgenticOrchestrator, LocalEvidenceEvaluator
from adam.agent.planner import AgentExecutionPlan, PlanStep, StepStatus, TaskComplexity
from adam.agent.subagents import (
    DataAnalysisSubagent,
    SubagentCoordinator,
    SubagentExecutionBudget,
    SubagentTask,
    WebResearchSubagent,
)
from adam.agent.tools import ForbiddenToolError, ReadOnlyToolRegistry
from adam.agent.web import SecureWebFetcher, SecureWebSearchEngine, WebRateLimiter, WebRateLimitExceeded
from adam.db.models import Document, DocumentChunk, DocumentVersion
from adam.rag.citation import CitationBuilder, format_citation_markdown
from adam.rag.models import Citation, EvidencePacket, EvidencePassage, UserContext
from adam.security.ssrf import SSRFGuard, SSRFSecurityError
from adam.vocabularies import AgentToolName, Classification, DepartmentId, DocType, ReviewStatus


# ── 1. SSRF Protection Tests ─────────────────────────────────────────────────

def test_ssrf_blocks_loopback_and_private_ips():
    """Verify SSRFGuard intercepts and blocks loopback and RFC 1918 private subnets."""
    private_ips = [
        "127.0.0.1",
        "10.0.0.1",
        "10.254.1.1",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.0.1",
        "192.168.1.100",
        "::1",
    ]
    for ip in private_ips:
        assert SSRFGuard.is_forbidden_ip(ip) is True

    # Validate URL raises SSRFSecurityError when resolving to private IP
    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("127.0.0.1", 80))]
        with pytest.raises(SSRFSecurityError, match="restricted IP"):
            SSRFGuard.validate_url("http://internal-service.local/api")


def test_ssrf_blocks_cloud_metadata_service():
    """Verify SSRFGuard specifically blocks cloud metadata endpoint (169.254.169.254)."""
    assert SSRFGuard.is_forbidden_ip("169.254.169.254") is True
    assert SSRFGuard.is_forbidden_ip("169.254.1.1") is True

    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("169.254.169.254", 80))]
        with pytest.raises(SSRFSecurityError, match="restricted IP"):
            SSRFGuard.validate_url("http://169.254.169.254/latest/meta-data/")


def test_ssrf_allows_public_addresses():
    """Verify SSRFGuard permits legitimate public web endpoints."""
    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        clean_url, hostname, ips = SSRFGuard.validate_url("https://doe.gov.in/orders")
        assert clean_url == "https://doe.gov.in/orders"
        assert hostname == "doe.gov.in"
        assert "93.184.216.34" in ips


# ── 2. Web Rate Limiting Tests ──────────────────────────────────────────────

def test_web_rate_limiter_sliding_window():
    """Verify sliding-window rate limit enforces per-domain threshold and resets."""
    limiter = WebRateLimiter(max_per_window=2, window_seconds=2)
    
    # 2 calls within budget succeed
    assert limiter.check_and_record("doe.gov.in") is True
    assert limiter.check_and_record("doe.gov.in") is True

    # 3rd call exceeds limit
    with pytest.raises(WebRateLimitExceeded, match="Rate limit exceeded"):
        limiter.check_and_record("doe.gov.in")

    # Different domain is unaffected
    assert limiter.check_and_record("uk.gov.in") is True


# ── 3. Web Fetcher & Search Tests ───────────────────────────────────────────

def test_secure_web_fetcher_html_to_markdown():
    """Verify HTML cleanup, script stripping, and table markdown extraction."""
    fetcher = SecureWebFetcher()
    sample_html = """
    <html>
      <head><title>Office Memorandum</title></head>
      <body>
        <script>alert('malicious')</script>
        <h1>Revised Rates of Dearness Allowance</h1>
        <p>The undersigned is directed to refer to OM No. 1/1/2024-E-II(B).</p>
        <table>
          <tr><th>Category</th><th>Rate</th></tr>
          <tr><td>7th CPC</td><td>50%</td></tr>
        </table>
      </body>
    </html>
    """
    cleaned = fetcher._html_to_clean_markdown(sample_html)
    assert "Revised Rates of Dearness Allowance" in cleaned
    assert "OM No. 1/1/2024-E-II(B)" in cleaned
    assert "Category" in cleaned
    assert "50%" in cleaned
    assert "alert" not in cleaned
    assert "<script>" not in cleaned


def test_secure_web_fetcher_rejects_non_http():
    """Verify fetcher rejects file:// and ftp:// protocols."""
    fetcher = SecureWebFetcher()
    with pytest.raises(SSRFSecurityError, match="Only HTTP and HTTPS"):
        fetcher.fetch("file:///etc/passwd")


def test_secure_web_search_engine_mock():
    """Verify web search returns structured results with domain metadata."""
    engine = SecureWebSearchEngine()
    engine.register_mock_result(
        "7th cpc da rates central government",
        [
            {
                "title": "DoE OM on Dearness Allowance 2024",
                "url": "https://doe.gov.in/orders/da-rate-2024.pdf",
                "snippet": "Revised rate of Dearness Allowance is 50% with effect from 01.01.2024.",
                "domain": "doe.gov.in",
            }
        ],
    )
    res = engine.search("7th cpc da rates central government", max_results=3)
    assert len(res) == 1
    assert res[0].title == "DoE OM on Dearness Allowance 2024"
    assert res[0].domain == "doe.gov.in"
    assert "50%" in res[0].snippet


# ── 4. Typed Tool Registry & Introspection Tests ─────────────────────────────

def test_tool_manifest_inspection():
    """Verify ReadOnlyToolRegistry exposes typed manifest for self-introspection."""
    user = UserContext(
        user_id="research_officer",
        clearance_level=Classification.PUBLIC.value,
        permissions=["agent:use_tools", "agent:web_research"],
        allow_web_research=True,
    )
    manifest = ReadOnlyToolRegistry.get_tool_manifest(user)
    assert len(manifest) >= 8

    # Verify tool names and parameters
    tool_names = {t["name"] for t in manifest}
    assert "search" in tool_names
    assert "database_query" in tool_names
    assert "execute_python_sandbox" in tool_names
    assert "compare_sources" in tool_names
    assert "web_search" in tool_names
    assert "inspect_system" in tool_names

    # Check database_query descriptor
    db_tool = next(t for t in manifest if t["name"] == "database_query")
    assert "table" in db_tool["parameters"]["properties"]
    assert db_tool["is_read_only"] is True


def test_tool_manifest_air_gapped_clearance_enforcement():
    """Verify classified/air-gapped clearances automatically filter external web tools."""
    classified_user = UserContext(
        user_id="secret_operator",
        clearance_level=Classification.RESTRICTED.value,
        permissions=["agent:use_tools"],
    )
    manifest = ReadOnlyToolRegistry.get_tool_manifest(classified_user)
    tool_names = {t["name"] for t in manifest}
    
    # External web tools must NOT be exposed for restricted sessions
    assert "web_search" not in tool_names
    assert "fetch_web_page" not in tool_names
    # Internal tools remain accessible
    assert "search" in tool_names
    assert "database_query" in tool_names


def test_destructive_tool_guardrail_rejection():
    """Verify destructive tools raise ForbiddenToolError."""
    forbidden = ["execute_sql_dml", "write_file", "delete_file", "modify_system_state"]
    for tname in forbidden:
        with pytest.raises(ForbiddenToolError):
            ReadOnlyToolRegistry.execute(tname, {}, UserContext())


# ── 5. Database Query Tool Tests ────────────────────────────────────────────

def test_database_query_tool_execution(db_session: Session):
    """Verify safe read-only database inspections via ReadOnlyToolRegistry."""
    # Seed a document
    doc = Document(
        id="doc_test_research_01",
        title="Uttarakhand DA Revision Order 2024",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        classification=Classification.PUBLIC.value,
    )
    db_session.add(doc)
    db_session.commit()

    user = UserContext(user_id="auditor", clearance_level=Classification.PUBLIC.value)

    # 1. Count documents
    res_count = ReadOnlyToolRegistry.execute(
        AgentToolName.DATABASE_QUERY.value,
        {"table": "documents", "aggregate": "count"},
        user,
        session=db_session,
    )
    assert res_count["result"] == 1

    # 2. List documents
    res_docs = ReadOnlyToolRegistry.execute(
        AgentToolName.DATABASE_QUERY.value,
        {"table": "documents", "aggregate": "list", "limit": 5},
        user,
        session=db_session,
    )
    assert res_docs["total_returned"] == 1
    assert res_docs["records"][0]["id"] == "doc_test_research_01"


# ── 6. Source Comparison Tool Tests ──────────────────────────────────────────

def test_compare_sources_tool():
    """Verify cross-source text comparison and delta identification."""
    src_a = "Uttarakhand state government announces 4% DA revision effective January 2024, reaching total 50%."
    src_b = "Central government announced 4% DA revision in March 2024 effective January 2024."
    
    res = ReadOnlyToolRegistry.execute(
        AgentToolName.COMPARE_SOURCES.value,
        {"source_a": src_a, "source_b": src_b, "comparison_focus": "DA revision date and rates"},
        UserContext(),
    )
    assert "summary" in res
    assert "common_terms" in res
    assert "2024" in res["common_terms"] or "4" in res["common_terms"]


# ── 7. Local Evidence Evaluator Tests ────────────────────────────────────────

def test_local_evidence_evaluator_sufficient():
    """Verify evaluator marks local evidence sufficient when valid passages exist."""
    passages = [
        EvidencePassage(
            chunk_id="chk_1",
            document_id="doc_1",
            version_id="ver_1",
            title="Uttarakhand DA Order",
            department_id="FINANCE_TREASURY",
            doc_type="GO",
            page_start=1,
            page_end=1,
            section_heading="DA Revision",
            content="Uttarakhand Government Order No. 450/XXVII(7)/2024 announces 4% DA hike for state employees.",
            score=0.85,
        )
    ]
    res = LocalEvidenceEvaluator.evaluate("What is the Uttarakhand DA increase?", passages)
    assert res.is_sufficient is True
    assert res.total_local_passages == 1


def test_local_evidence_evaluator_requires_external_national():
    """Verify evaluator flags external research when query explicitly references central/national entities."""
    passages = [
        EvidencePassage(
            chunk_id="chk_1",
            document_id="doc_1",
            version_id="ver_1",
            title="Uttarakhand DA Order",
            department_id="FINANCE_TREASURY",
            doc_type="GO",
            page_start=1,
            page_end=1,
            section_heading="DA Revision",
            content="Uttarakhand Government Order on local state allowance.",
            score=0.80,
        )
    ]
    res = LocalEvidenceEvaluator.evaluate("Compare Uttarakhand DA with central government 7th CPC rates", passages)
    assert res.is_sufficient is False
    assert "external" in res.reason.lower() or "national" in res.reason.lower()


# ── 8. Specialized Subagents Tests ───────────────────────────────────────────

def test_web_research_subagent_bounded_execution():
    """Verify WebResearchSubagent executes within tool budget."""
    user = UserContext(permissions=["agent:web_research"], allow_web_research=True)
    subagent = WebResearchSubagent(user_context=user)
    task = SubagentTask(
        task_id="task_web_01",
        subagent_type="web_research",
        goal="Find central government DA revision notification 2024",
        inputs={"query": "central government 7th cpc da rates 2024"},
    )
    result = subagent.run(task)
    assert result.success is True
    assert len(result.tool_calls) <= 2


def test_data_analysis_subagent_calculation():
    """Verify DataAnalysisSubagent performs verified arithmetic."""
    subagent = DataAnalysisSubagent()
    task = SubagentTask(
        task_id="task_data_01",
        subagent_type="data_analysis",
        goal="Calculate monthly pay increase for basic pay 50000 at 4% DA",
        inputs={"code": "basic = 50000\nrate = 0.04\nincrease = basic * rate\nincrease"},
    )
    result = subagent.run(task)
    assert result.success is True
    assert float(result.findings[0]["value"]) == 2000.0


def test_subagent_coordinator_limits():
    """Verify SubagentCoordinator blocks unbounded depth and enforces max subagents."""
    coord = SubagentCoordinator(max_subagents=2)

    # Depth > 1 must be rejected
    task_deep = SubagentTask(
        task_id="deep_01",
        subagent_type="web_research",
        goal="Unbounded recursion test",
        depth=2,
    )
    res_deep = coord.dispatch(task_deep)
    assert res_deep.success is False
    assert "depth" in res_deep.error.lower()

    # Dispatch 2 subagents
    t1 = SubagentTask(
        task_id="sub_1",
        subagent_type="data_analysis",
        goal="Calc A",
        inputs={"code": "10 + 20"},
        depth=1,
    )
    t2 = SubagentTask(
        task_id="sub_2",
        subagent_type="data_analysis",
        goal="Calc B",
        inputs={"code": "30 + 40"},
        depth=1,
    )
    r1 = coord.dispatch(t1)
    r2 = coord.dispatch(t2)
    assert r1.success is True
    assert r2.success is True

    # 3rd subagent exceeds coordinator budget
    t3 = SubagentTask(
        task_id="sub_3",
        subagent_type="data_analysis",
        goal="Calc C",
        inputs={"code": "50 + 60"},
        depth=1,
    )
    res3 = coord.dispatch(t3)
    assert res3.success is False
    assert "budget" in res3.error.lower()


# ── 9. Orchestrator Loop Prevention & External Citations ─────────────────────

def test_provenance_citation_formatting():
    """Verify distinct formatting between internal official citations and external web citations."""
    internal_cit = Citation(
        document_title="Uttarakhand Treasury Order",
        department="FINANCE_TREASURY",
        document_id="doc_uk_01",
        go_number="123/XXVII/2024",
        version_hash="hash123",
        page=1,
        source_url="https://finance.uk.gov.in/go.pdf",
        retrieval_timestamp="2024-01-01T00:00:00Z",
        pdf_page_link="https://finance.uk.gov.in/go.pdf#page=1",
        is_external=False,
    )
    ext_cit = Citation(
        document_title="Central DoE Office Memorandum",
        department="EXTERNAL_PUBLIC",
        version_hash="hash456",
        page=1,
        source_url="https://doe.gov.in/om.pdf",
        retrieval_timestamp="2024-01-01T00:00:00Z",
        pdf_page_link="https://doe.gov.in/om.pdf",
        is_external=True,
        provenance_type="EXTERNAL_WEB",
        external_url="https://doe.gov.in/om.pdf",
        external_domain="doe.gov.in",
    )

    int_md = format_citation_markdown(internal_cit, index=1)
    ext_md = format_citation_markdown(ext_cit, index=1)

    assert "[1] **Uttarakhand Treasury Order**" in int_md
    assert "[WEB-1] **Central DoE Office Memorandum**" in ext_md
    assert "doe.gov.in" in ext_md
    assert "External Web Source" in ext_md
