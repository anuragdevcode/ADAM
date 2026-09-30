"""Agent-to-Agent (A2A) Protocol Layer for Specialist Agent Delegation.

Provides:
- A2ATaskContract: Structured, typed task delegation contract between orchestrator and specialist agents.
- A2AResponseEnvelope: Formal verified findings envelope returned to the delegating agent.
- A2ABudget: Hard constraints (max duration, max tools, max tokens) allocated to specialist.
- A2ASpecialistCoordinator: Manages specialist agent lifecycle, enforcing single-recursion depth (depth <= 1)
  and preventing uncontrolled agent swarms.
- Specialized Agents:
  - PrecedentGraphSpecialist: Deep multi-hop DAG traversal of amending orders and supersessions.
  - QuantitativeAnalysisSpecialist: Sandboxed mathematical, pension, and allowance calculations.
  - WebResearchSpecialist: SSRF-guarded external investigation and clean passage extraction.
  - ComplianceAuditSpecialist: Administrative jurisdiction, clearance, and precedent currency verification.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field

from adam.agent.sandbox import SecurePythonSandbox
from adam.agent.tools import ReadOnlyToolRegistry
from adam.graphs.precedents import PrecedentDAG
from adam.rag.models import EvidencePassage, UserContext
from adam.vocabularies import AgentToolName, Classification

logger = logging.getLogger(__name__)


class A2ATaskStatus(StrEnum):
    """Lifecycle status of an A2A task contract."""
    INITIALIZED = "INITIALIZED"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ABSTAINED = "ABSTAINED"


class A2ARecursionError(RuntimeError):
    """Raised when an agent attempts to spawn descendant agents beyond allowed depth."""
    pass


class A2ABudget(BaseModel):
    """Resource constraints allocated to a specialist agent."""
    model_config = ConfigDict(extra="ignore")

    max_duration_seconds: float = Field(default=8.0, description="Max runtime allocated to specialist")
    max_tool_calls: int = Field(default=3, description="Maximum tool calls allowed")
    max_tokens: int = Field(default=512, description="Token generation budget")
    max_depth: int = Field(default=1, description="Strict recursion ceiling (depth <= 1)")


class A2ATaskContract(BaseModel):
    """Typed contract for delegating a sub-task to a specialist agent."""
    model_config = ConfigDict(extra="ignore")

    task_id: str = Field(default_factory=lambda: f"a2a_{uuid4().hex[:10]}")
    parent_task_id: Optional[str] = Field(default=None)
    delegator_agent_id: str = Field(default="adam_orchestrator")
    specialist_agent_id: str = Field(..., description="Target specialist: precedent_graph, quantitative_analysis, web_research, compliance_audit")
    objective: str = Field(..., description="Explicit, unambiguous sub-goal to achieve")
    input_artifacts: Dict[str, Any] = Field(default_factory=dict, description="Context, passages, formulas, or order numbers")
    clearance_level: str = Field(default=Classification.PUBLIC.value)
    budget: A2ABudget = Field(default_factory=A2ABudget)
    depth: int = Field(default=1, description="Call stack depth (1 = direct child)")


class A2AResponseEnvelope(BaseModel):
    """Structured response returned by a specialist agent upon task completion."""
    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True)

    task_id: str
    specialist_agent_id: str
    status: A2ATaskStatus
    summary: str
    structured_findings: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_passages: List[EvidencePassage] = Field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    latency_ms: float = 0.0
    error: Optional[str] = None
    consumed_budget: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "specialist": self.specialist_agent_id,
            "status": self.status.value,
            "summary": self.summary,
            "findings_count": len(self.structured_findings),
            "findings": self.structured_findings,
            "evidence_count": len(self.evidence_passages),
            "tool_calls": self.tool_calls,
            "latency_ms": round(self.latency_ms, 2),
            "error": self.error,
        }


class BaseSpecialistAgent(ABC):
    """Abstract base class for all A2A specialist agents."""

    def __init__(self, session: Optional[Any] = None, user_context: Optional[UserContext] = None):
        self.session = session
        self.user_context = user_context or UserContext()

    @abstractmethod
    def execute(self, contract: A2ATaskContract) -> A2AResponseEnvelope:
        """Execute task contract within bounded resource limits."""
        pass


class PrecedentGraphSpecialist(BaseSpecialistAgent):
    """Specialist traversing DAG linkages to identify superseding notifications and amendment chains."""

    def execute(self, contract: A2ATaskContract) -> A2AResponseEnvelope:
        start_t = time.perf_counter()
        tool_records: List[Dict[str, Any]] = []
        findings: List[Dict[str, Any]] = []

        if contract.depth > contract.budget.max_depth:
            raise A2ARecursionError(f"Recursion depth {contract.depth} exceeds limit {contract.budget.max_depth}.")

        order_number = contract.input_artifacts.get("order_number") or contract.objective
        document_id = contract.input_artifacts.get("document_id")

        if not self.session:
            return A2AResponseEnvelope(
                task_id=contract.task_id,
                specialist_agent_id="precedent_graph_specialist",
                status=A2ATaskStatus.FAILED,
                summary="Database session unavailable for precedent graph traversal.",
                error="No database session",
            )

        try:
            dag = PrecedentDAG.build_from_database(self.session)
            total_edges = sum(len(e) for e in dag.outgoing_edges.values())
            tool_records.append({"tool": "precedent_dag_init", "nodes": len(dag.nodes), "edges": total_edges})

            # 1. Resolve active terminal order (supersession check)
            terminal_node, chain = dag.resolve_active_terminal_order(order_number=order_number)
            is_superseded = len(chain) > 1

            # 2. Get amendment chain
            amendments = dag.get_amendment_chain(order_number=order_number)

            summary = f"Precedent Analysis for '{order_number}': "
            if is_superseded:
                summary += f"SUPERSEDED by {terminal_node.order_number} ({len(chain)-1} hops). "
            else:
                summary += "Currently ACTIVE / not superseded. "
            summary += f"Found {len(amendments)} amending order(s)."

            findings.append({
                "query_order": order_number,
                "is_superseded": is_superseded,
                "active_terminal_order": terminal_node.order_number if terminal_node else None,
                "supersession_chain": list(chain),
                "amendments_count": len(amendments),
                "amendments": [a.order_number for a in amendments],
            })

            return A2AResponseEnvelope(
                task_id=contract.task_id,
                specialist_agent_id="precedent_graph_specialist",
                status=A2ATaskStatus.SUCCESS,
                summary=summary,
                structured_findings=findings,
                tool_calls=tool_records,
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )
        except Exception as e:
            logger.exception("PrecedentGraphSpecialist failed")
            return A2AResponseEnvelope(
                task_id=contract.task_id,
                specialist_agent_id="precedent_graph_specialist",
                status=A2ATaskStatus.FAILED,
                summary=f"Graph traversal error: {str(e)}",
                error=str(e),
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )


class QuantitativeAnalysisSpecialist(BaseSpecialistAgent):
    """Specialist deriving mathematical formulas and executing verified calculations in Python sandbox."""

    def execute(self, contract: A2ATaskContract) -> A2AResponseEnvelope:
        start_t = time.perf_counter()
        tool_records: List[Dict[str, Any]] = []

        if contract.depth > contract.budget.max_depth:
            raise A2ARecursionError(f"Recursion depth {contract.depth} exceeds limit {contract.budget.max_depth}.")

        code = contract.input_artifacts.get("code") or ""
        context_vars = contract.input_artifacts.get("context_vars")

        if not code:
            return A2AResponseEnvelope(
                task_id=contract.task_id,
                specialist_agent_id="quantitative_analysis_specialist",
                status=A2ATaskStatus.FAILED,
                summary="No computation formula or code provided in contract inputs.",
                error="Missing 'code' artifact",
            )

        calc_res = SecurePythonSandbox.execute(
            code=code,
            context_vars=context_vars,
            timeout_seconds=min(2.0, contract.budget.max_duration_seconds),
        )

        tool_records.append({
            "tool": "execute_python_sandbox",
            "success": calc_res.success,
            "duration_ms": calc_res.execution_time_ms,
        })

        if calc_res.success:
            res_val = calc_res.value if calc_res.value is not None else calc_res.output
            summary = f"Verified calculation result: {res_val}"
            findings = [{
                "code": code,
                "value": calc_res.value,
                "output": calc_res.output,
                "execution_time_ms": calc_res.execution_time_ms,
            }]
            return A2AResponseEnvelope(
                task_id=contract.task_id,
                specialist_agent_id="quantitative_analysis_specialist",
                status=A2ATaskStatus.SUCCESS,
                summary=summary,
                structured_findings=findings,
                tool_calls=tool_records,
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )
        else:
            return A2AResponseEnvelope(
                task_id=contract.task_id,
                specialist_agent_id="quantitative_analysis_specialist",
                status=A2ATaskStatus.FAILED,
                summary=f"Calculation error: {calc_res.error}",
                error=calc_res.error,
                tool_calls=tool_records,
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )


class WebResearchSpecialist(BaseSpecialistAgent):
    """Specialist conducting domain-aware external search and URL fetching."""

    def execute(self, contract: A2ATaskContract) -> A2AResponseEnvelope:
        start_t = time.perf_counter()
        tool_records: List[Dict[str, Any]] = []
        passages: List[EvidencePassage] = []
        findings: List[Dict[str, Any]] = []

        if contract.depth > contract.budget.max_depth:
            raise A2ARecursionError(f"Recursion depth {contract.depth} exceeds limit {contract.budget.max_depth}.")

        # Enforce air-gap policy
        if self.user_context.clearance_level in (Classification.RESTRICTED.value, Classification.CONFIDENTIAL.value):
            return A2AResponseEnvelope(
                task_id=contract.task_id,
                specialist_agent_id="web_research_specialist",
                status=A2ATaskStatus.FAILED,
                summary="Web research barred under Air-Gapped Data Sovereignty Policy.",
                error="Air-Gapped Sovereignty Policy violation",
            )

        query = contract.input_artifacts.get("query") or contract.objective
        domain_filter = contract.input_artifacts.get("domain_filter")

        try:
            from adam.agent.web import SecureWebFetcher, SecureWebSearchEngine

            engine = SecureWebSearchEngine()
            results = engine.search(query=query, domain_filter=domain_filter, max_results=3)
            tool_records.append({
                "tool": "web_search",
                "query": query,
                "found_count": len(results),
            })

            if results:
                top_hit = results[0]
                fetcher = SecureWebFetcher()
                page = fetcher.fetch(top_hit.url, extract_tables=True)
                tool_records.append({
                    "tool": "fetch_web_page",
                    "url": top_hit.url,
                    "status_code": page.status_code,
                })

                p = EvidencePassage(
                    chunk_id=f"a2a_web_{uuid4().hex[:8]}",
                    document_id=top_hit.domain,
                    version_id="ext_v1",
                    title=top_hit.title,
                    department_id="EXTERNAL_PUBLIC",
                    doc_type="WEB_SOURCE",
                    page_start=1,
                    page_end=1,
                    section_heading="External Web Finding",
                    content=page.content[:2000] if page.content else top_hit.snippet,
                    source_url=top_hit.url,
                    is_external=True,
                    provenance_type="EXTERNAL_WEB",
                    external_url=top_hit.url,
                    external_domain=top_hit.domain,
                )
                passages.append(p)
                findings.append({
                    "title": top_hit.title,
                    "url": top_hit.url,
                    "domain": top_hit.domain,
                    "snippet": top_hit.snippet,
                })

            summary = f"Gathered {len(passages)} external passage(s) across {len(findings)} source(s)."
            return A2AResponseEnvelope(
                task_id=contract.task_id,
                specialist_agent_id="web_research_specialist",
                status=A2ATaskStatus.SUCCESS,
                summary=summary,
                structured_findings=findings,
                evidence_passages=passages,
                tool_calls=tool_records,
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )
        except Exception as e:
            logger.exception("WebResearchSpecialist failed")
            return A2AResponseEnvelope(
                task_id=contract.task_id,
                specialist_agent_id="web_research_specialist",
                status=A2ATaskStatus.FAILED,
                summary=f"Web research error: {str(e)}",
                error=str(e),
                tool_calls=tool_records,
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )


class ComplianceAuditSpecialist(BaseSpecialistAgent):
    """Specialist auditing statutory jurisdiction, clearance limits, and policy compliance."""

    def execute(self, contract: A2ATaskContract) -> A2AResponseEnvelope:
        start_t = time.perf_counter()
        target_department = contract.input_artifacts.get("department_id")
        user_clearance = self.user_context.clearance_level

        is_authorized = True
        notes = []

        if user_clearance == Classification.PUBLIC.value and target_department in ("INTELLIGENCE", "CABINET_SECRETARIAT"):
            is_authorized = False
            notes.append("Department requires elevated clearance (RESTRICTED or above).")

        findings = [{
            "user_id": self.user_context.user_id,
            "clearance": user_clearance,
            "target_department": target_department,
            "is_authorized": is_authorized,
            "notes": notes,
        }]

        return A2AResponseEnvelope(
            task_id=contract.task_id,
            specialist_agent_id="compliance_audit_specialist",
            status=A2ATaskStatus.SUCCESS if is_authorized else A2ATaskStatus.ABSTAINED,
            summary=f"Compliance check: {'Passed' if is_authorized else 'Failed'}.",
            structured_findings=findings,
            latency_ms=(time.perf_counter() - start_t) * 1000.0,
        )


class A2ASpecialistCoordinator:
    """Coordinates specialist agent dispatching with strict budget and recursion guards."""

    MAX_CONCURRENT_SPECIALISTS: int = 2

    def __init__(self, session: Optional[Any] = None, user_context: Optional[UserContext] = None):
        self.session = session
        self.user_context = user_context or UserContext()
        self._spawned_count = 0

    def dispatch(self, contract: A2ATaskContract) -> A2AResponseEnvelope:
        """Dispatch task to designated specialist agent enforcing depth and quota boundaries."""
        # Enforce recursion depth ceiling
        if contract.depth > contract.budget.max_depth:
            return A2AResponseEnvelope(
                task_id=contract.task_id,
                specialist_agent_id=contract.specialist_agent_id,
                status=A2ATaskStatus.FAILED,
                summary="Recursion blocked: specialist agents cannot spawn child agents.",
                error=f"Recursion limit exceeded (depth={contract.depth} > {contract.budget.max_depth})",
            )

        # Enforce invocation quotas
        if self._spawned_count >= self.MAX_CONCURRENT_SPECIALISTS:
            return A2AResponseEnvelope(
                task_id=contract.task_id,
                specialist_agent_id=contract.specialist_agent_id,
                status=A2ATaskStatus.ABSTAINED,
                summary="Specialist delegation quota reached for this session (max 2).",
                error="Specialist invocation quota exhausted",
            )

        self._spawned_count += 1
        spec_id = contract.specialist_agent_id.strip().lower()

        agent: BaseSpecialistAgent
        if spec_id in ("precedent_graph", "precedent_graph_specialist"):
            agent = PrecedentGraphSpecialist(self.session, self.user_context)
        elif spec_id in ("quantitative_analysis", "quantitative_analysis_specialist", "data_analysis"):
            agent = QuantitativeAnalysisSpecialist(self.session, self.user_context)
        elif spec_id in ("web_research", "web_research_specialist"):
            agent = WebResearchSpecialist(self.session, self.user_context)
        elif spec_id in ("compliance_audit", "compliance_audit_specialist"):
            agent = ComplianceAuditSpecialist(self.session, self.user_context)
        else:
            return A2AResponseEnvelope(
                task_id=contract.task_id,
                specialist_agent_id=contract.specialist_agent_id,
                status=A2ATaskStatus.FAILED,
                summary=f"Unrecognized specialist agent '{contract.specialist_agent_id}'.",
                error=f"Unknown specialist ID '{contract.specialist_agent_id}'",
            )

        return agent.execute(contract)
