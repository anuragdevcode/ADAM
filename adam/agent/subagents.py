"""Specialized, bounded subagents for focused problem decomposition.

Provides:
- WebResearchSubagent: Conducts focused external web investigation and extracts clean evidence passages.
- DataAnalysisSubagent: Formulates deterministic calculation scripts and performs sandboxed verification.
- SubagentCoordinator: Enforces strict depth ceilings (max recursion = 1), invocation quotas (max 2 subagents),
  and per-subagent time/tool budgets.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from adam.agent.tools import ReadOnlyToolRegistry
from adam.rag.models import EvidencePassage, UserContext
from adam.vocabularies import AgentToolName

logger = logging.getLogger(__name__)


@dataclass
class SubagentExecutionBudget:
    """Hard resource budget allocated to a subagent execution."""
    max_tool_calls: int = 2
    max_runtime_seconds: float = 8.0
    recursion_depth: int = 1
    max_tokens: int = 512


@dataclass
class SubagentTask:
    """Bounded task definition handed to a subagent."""
    task_id: str
    subagent_type: str  # web_research, data_analysis
    goal: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    depth: int = 1


@dataclass
class SubagentResult:
    """Verified findings returned by a subagent to the parent orchestrator."""
    task_id: str
    subagent_type: str
    success: bool
    summary: str
    findings: List[Dict[str, Any]] = field(default_factory=list)
    evidence_passages: List[EvidencePassage] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "subagent_type": self.subagent_type,
            "success": self.success,
            "summary": self.summary,
            "findings": self.findings,
            "evidence_count": len(self.evidence_passages),
            "tool_calls": self.tool_calls,
            "latency_ms": round(self.latency_ms, 2),
            "error": self.error,
        }


class BaseSubagent(ABC):
    """Abstract base class for isolated, single-depth subagents."""

    def __init__(
        self,
        session: Optional[Session] = None,
        user_context: Optional[UserContext] = None,
        budget: Optional[SubagentExecutionBudget] = None,
    ):
        self.session = session
        self.user_context = user_context or UserContext()
        self.budget = budget or SubagentExecutionBudget()

    @abstractmethod
    def run(self, task: SubagentTask) -> SubagentResult:
        """Execute bounded task and return verified findings."""
        pass


class WebResearchSubagent(BaseSubagent):
    """Conducts focused external web search and URL extraction for external facts."""

    def run(self, task: SubagentTask) -> SubagentResult:
        start_t = time.perf_counter()
        tool_records: List[Dict[str, Any]] = []
        passages: List[EvidencePassage] = []
        findings: List[Dict[str, Any]] = []

        # Recursion depth guard
        if task.depth > 1:
            return SubagentResult(
                task_id=task.task_id,
                subagent_type="web_research",
                success=False,
                summary="Recursion blocked: subagents cannot spawn descendant subagents.",
                error="Max recursion depth exceeded (depth > 1).",
            )

        query = task.inputs.get("query") or task.goal
        domain_filter = task.inputs.get("domain_filter")

        try:
            # 1. External Web Search
            search_res = ReadOnlyToolRegistry.execute(
                tool_name=AgentToolName.WEB_SEARCH.value,
                arguments={"query": query, "domain_filter": domain_filter, "max_results": 3},
                user_context=self.user_context,
                session=self.session,
            )
            tool_records.append({
                "tool": "web_search",
                "args": {"query": query, "domain_filter": domain_filter},
                "found_count": search_res.get("total_found", 0),
            })

            results = search_res.get("results") or []
            if not results:
                return SubagentResult(
                    task_id=task.task_id,
                    subagent_type="web_research",
                    success=True,
                    summary="Web research yielded zero search results for query.",
                    tool_calls=tool_records,
                    latency_ms=(time.perf_counter() - start_t) * 1000.0,
                )

            # 2. Fetch top authoritative result if available and within tool budget
            top_hit = results[0]
            top_url = top_hit.get("url")
            page_text = top_hit.get("snippet", "")

            if top_url and len(tool_records) < self.budget.max_tool_calls:
                elapsed = time.perf_counter() - start_t
                if elapsed < self.budget.max_runtime_seconds:
                    try:
                        fetch_res = ReadOnlyToolRegistry.execute(
                            tool_name=AgentToolName.FETCH_WEB_PAGE.value,
                            arguments={"url": top_url, "extract_tables": True},
                            user_context=self.user_context,
                            session=self.session,
                        )
                        tool_records.append({
                            "tool": "fetch_web_page",
                            "url": top_url,
                            "status": fetch_res.get("status_code", 200),
                        })
                        if fetch_res.get("content"):
                            page_text = fetch_res["content"][:2000]
                    except Exception as fe:
                        logger.warning(f"WebResearchSubagent page fetch warning: {fe}")

            # Construct external EvidencePassage with provenance
            passage = EvidencePassage(
                chunk_id=f"web_{uuid4().hex[:8]}",
                document_id=top_hit.get("domain", "web"),
                version_id="ext_v1",
                title=top_hit.get("title", "External Web Source"),
                department_id="EXTERNAL_PUBLIC",
                doc_type="WEB_SOURCE",
                page_start=1,
                page_end=1,
                section_heading="External Web Finding",
                content=page_text,
                source_url=top_url,
                is_external=True,
                provenance_type="EXTERNAL_WEB",
                external_url=top_url,
                external_domain=top_hit.get("domain"),
            )
            passages.append(passage)
            findings.append({
                "title": top_hit.get("title"),
                "url": top_url,
                "domain": top_hit.get("domain"),
                "snippet": top_hit.get("snippet"),
            })

            summary = f"Gathered {len(passages)} external web source(s) from {top_hit.get('domain')}."
            return SubagentResult(
                task_id=task.task_id,
                subagent_type="web_research",
                success=True,
                summary=summary,
                findings=findings,
                evidence_passages=passages,
                tool_calls=tool_records,
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )
        except Exception as e:
            return SubagentResult(
                task_id=task.task_id,
                subagent_type="web_research",
                success=False,
                summary=f"Web research subagent error: {str(e)}",
                error=str(e),
                tool_calls=tool_records,
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )


class DataAnalysisSubagent(BaseSubagent):
    """Performs isolated quantitative calculation, cross-tabulation, and sandbox proof verification."""

    def run(self, task: SubagentTask) -> SubagentResult:
        start_t = time.perf_counter()
        tool_records: List[Dict[str, Any]] = []

        if task.depth > 1:
            return SubagentResult(
                task_id=task.task_id,
                subagent_type="data_analysis",
                success=False,
                summary="Recursion blocked: subagents cannot spawn descendant subagents.",
                error="Max recursion depth exceeded (depth > 1).",
            )

        code = task.inputs.get("code")
        if not code:
            return SubagentResult(
                task_id=task.task_id,
                subagent_type="data_analysis",
                success=False,
                summary="No computation formula provided.",
                error="Missing 'code' input parameter.",
            )

        try:
            calc_res = ReadOnlyToolRegistry.execute(
                tool_name=AgentToolName.EXECUTE_PYTHON_SANDBOX.value,
                arguments={"code": code},
                user_context=self.user_context,
                session=self.session,
            )
            tool_records.append({
                "tool": "execute_python_sandbox",
                "success": calc_res.get("success", False),
                "val": calc_res.get("value"),
            })

            success = bool(calc_res.get("success"))
            summary = f"Calculated value: {calc_res.get('value')}" if success else f"Calculation failed: {calc_res.get('error')}"

            return SubagentResult(
                task_id=task.task_id,
                subagent_type="data_analysis",
                success=success,
                summary=summary,
                findings=[calc_res],
                tool_calls=tool_records,
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
                error=calc_res.get("error") if not success else None,
            )
        except Exception as e:
            return SubagentResult(
                task_id=task.task_id,
                subagent_type="data_analysis",
                success=False,
                summary=f"Data analysis error: {str(e)}",
                error=str(e),
                tool_calls=tool_records,
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )


class SubagentCoordinator:
    """Manages subagent dispatching, depth enforcement, and collective budget tracking."""

    MAX_SUBAGENTS: int = 2

    def __init__(
        self,
        session: Optional[Session] = None,
        user_context: Optional[UserContext] = None,
        max_subagents: Optional[int] = None,
    ):
        self.session = session
        self.user_context = user_context or UserContext()
        self.max_subagents = max_subagents if max_subagents is not None else self.MAX_SUBAGENTS
        self._spawned_count = 0

    def dispatch(
        self,
        subagent_type: str | SubagentTask,
        goal: Optional[str] = None,
        inputs: Optional[Dict[str, Any]] = None,
        depth: int = 1,
    ) -> SubagentResult:
        """Spawn and execute a specialized subagent within hard quotas."""
        if isinstance(subagent_type, SubagentTask):
            task = subagent_type
            effective_type = task.subagent_type
        else:
            effective_type = subagent_type
            task = SubagentTask(
                task_id=f"task_{uuid4().hex[:6]}",
                subagent_type=effective_type,
                goal=goal or "",
                inputs=inputs or {},
                depth=depth,
            )

        # Depth ceiling check (depth must be <= 1)
        if task.depth > 1:
            return SubagentResult(
                task_id=task.task_id,
                subagent_type=effective_type,
                success=False,
                summary="Recursion blocked: subagents cannot spawn descendant subagents.",
                error="Max recursion depth exceeded (depth > 1).",
            )

        if self._spawned_count >= self.max_subagents:
            return SubagentResult(
                task_id=task.task_id,
                subagent_type=effective_type,
                success=False,
                summary=f"Subagent quota exceeded (max {self.max_subagents} per request).",
                error="Subagent budget exceeded.",
            )

        self._spawned_count += 1

        norm_type = effective_type.lower()
        if "web" in norm_type:
            sub = WebResearchSubagent(self.session, self.user_context)
            return sub.run(task)
        elif "data" in norm_type or "calc" in norm_type:
            sub = DataAnalysisSubagent(self.session, self.user_context)
            return sub.run(task)
        else:
            return SubagentResult(
                task_id=task.task_id,
                subagent_type=effective_type,
                success=False,
                summary=f"Unknown subagent type '{effective_type}'.",
                error="Unregistered subagent type.",
            )
