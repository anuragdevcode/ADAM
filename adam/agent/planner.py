"""Agentic Planner and Problem Decomposition Engine.

Analyzes administrative queries, classifies task complexity, generates structured
execution plans, and breaks down complex questions into verifiable sub-problems.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Dict, List, Optional

from adam.rag.models import UserContext
from adam.vocabularies import AgentToolName


class TaskComplexity(StrEnum):
    """Categorization of problem solving complexity."""
    DIRECT_LOOKUP = "DIRECT_LOOKUP"
    MULTI_STEP_ANALYSIS = "MULTI_STEP_ANALYSIS"
    QUANTITATIVE_COMPUTATION = "QUANTITATIVE_COMPUTATION"
    PRECEDENT_TRACKING = "PRECEDENT_TRACKING"
    SYSTEM_INTROSPECTION = "SYSTEM_INTROSPECTION"
    DATABASE_INSPECTION = "DATABASE_INSPECTION"
    EXTERNAL_WEB_RESEARCH = "EXTERNAL_WEB_RESEARCH"
    COMPARATIVE_RESEARCH = "COMPARATIVE_RESEARCH"


class StepStatus(StrEnum):
    """Execution lifecycle status of an individual plan step."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    VERIFIED = "VERIFIED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABSTAINED = "ABSTAINED"


@dataclass
class PlanStep:
    """An individual sub-task within an agent execution plan."""
    step_id: int
    title: str
    description: str
    action_type: str  # search, compute, precedent, introspection, synthesize
    tool_name: Optional[str] = None
    tool_args: Dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    result_summary: Optional[str] = None
    computation_result: Optional[Any] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "title": self.title,
            "description": self.description,
            "action_type": self.action_type,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "status": str(self.status.value if hasattr(self.status, "value") else self.status),
            "result_summary": self.result_summary,
            "computation_result": str(self.computation_result) if self.computation_result is not None else None,
            "error": self.error,
        }


@dataclass
class AgentExecutionPlan:
    """High-level, structured execution plan for resolving user requests."""
    query: str
    complexity: TaskComplexity
    plan_summary: str
    steps: List[PlanStep] = field(default_factory=list)
    is_direct_lookup: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "complexity": str(self.complexity.value if hasattr(self.complexity, "value") else self.complexity),
            "plan_summary": self.plan_summary,
            "is_direct_lookup": self.is_direct_lookup,
            "total_steps": len(self.steps),
            "steps": [s.to_dict() for s in self.steps],
        }


class AgenticPlanner:
    """Intelligently analyzes query requirements and produces structured execution plans."""

    MAX_STEPS: int = 6
    MAX_SUBPROBLEMS: int = 4

    # Keywords signaling mathematical or financial calculation
    QUANTITATIVE_PATTERNS = [
        re.compile(r"\b(?:calculate|compute|calculation|eval(?:uate)?|arithmetic|formula|how much will be the increase|how much increase on|revised pay for|salary after increase|total payable|calculate (?:da|pension|gratuity|allowance)|if (?:the )?(?:basic|salary|pay) is \d+)\b", re.I),
        re.compile(r"(?:गणना करें|हिसाब लगाएं|कुल वेतन निकालें|वृद्धि की गणना|यदि मूल वेतन)", re.U),
    ]

    # Keywords signaling comparative or multi-document analysis
    COMPARISON_PATTERNS = [
        re.compile(r"\b(?:compare|comparison|difference between|differences between|changes between|from \d{4} to \d{4}|versus|vs\.?|how has .+ changed|evolution of|before and after)\b", re.I),
        re.compile(r"(?:तुलना करें|अंतर स्पष्ट करें|बदलाव क्या आया|पूर्व और पश्चात की तुलना)", re.U),
    ]

    # Keywords signaling precedent tracking or amendment tracing
    PRECEDENT_PATTERNS = [
        re.compile(r"\b(?:trace precedent|precedent chain|chain of orders|trace superseding|amendment history|which order superseded|history of amendments)\b", re.I),
        re.compile(r"(?:पूर्व आदेशों की श्रृंखला|संशोधन इतिहास|निरस्त करने वाले आदेश)", re.U),
    ]

    # Keywords signaling system capability introspection
    INTROSPECTION_PATTERNS = [
        re.compile(r"\b(?:what model|which model|active model|harness profile|system capabilities|allowed tools|memory footprint|data sources|system status|self-model)\b", re.I),
        re.compile(r"(?:मॉडल|सिस्टम क्षमता|सक्रिय मॉडल|टूल)", re.U),
    ]

    # Keywords signaling database queries and counts
    DATABASE_PATTERNS = [
        re.compile(r"\b(?:how many documents|total orders|count of documents|database stats|documents count|number of orders|how many records in database|total records|count documents)\b", re.I),
        re.compile(r"(?:दस्तावेजों की संख्या|कुल आदेश|डेटाबेस रिकॉर्ड)", re.U),
    ]

    # Keywords signaling external web research
    WEB_RESEARCH_PATTERNS = [
        re.compile(r"\b(?:central government|central da|central dearness|in other states|outside uttarakhand|delhi|national policy|union government|doe\.gov\.in|central 7th cpc|web search|online|latest update nationally)\b", re.I),
        re.compile(r"(?:केंद्र सरकार|केंद्रीय महंगाई भत्ता|अन्य राज्य|राष्ट्रीय नीति)", re.U),
    ]

    @classmethod
    def classify_complexity(cls, query: str) -> TaskComplexity:
        """Determine whether a task requires direct retrieval, computation, comparison, or introspection."""
        clean_q = query.strip().lower()

        # 1. System Introspection
        for pat in cls.INTROSPECTION_PATTERNS:
            if pat.search(clean_q):
                return TaskComplexity.SYSTEM_INTROSPECTION

        # 2. Database Inspection
        for pat in cls.DATABASE_PATTERNS:
            if pat.search(clean_q):
                return TaskComplexity.DATABASE_INSPECTION

        # 3. Quantitative Computation
        for pat in cls.QUANTITATIVE_PATTERNS:
            if pat.search(clean_q):
                return TaskComplexity.QUANTITATIVE_COMPUTATION

        # 4. External Web Research
        for pat in cls.WEB_RESEARCH_PATTERNS:
            if pat.search(clean_q):
                return TaskComplexity.EXTERNAL_WEB_RESEARCH

        # 5. Precedent Tracking
        for pat in cls.PRECEDENT_PATTERNS:
            if pat.search(clean_q):
                return TaskComplexity.PRECEDENT_TRACKING

        # 6. Comparative / Multi-Step Analysis
        for pat in cls.COMPARISON_PATTERNS:
            if pat.search(clean_q):
                return TaskComplexity.COMPARATIVE_RESEARCH

        # 7. Check if query contains multiple distinct sub-questions
        if len(clean_q) > 40 and ("?" in clean_q[:-1] or " and also compare " in clean_q):
            return TaskComplexity.MULTI_STEP_ANALYSIS

        return TaskComplexity.DIRECT_LOOKUP

    @classmethod
    def create_plan(
        cls,
        query: str,
        user_context: Optional[UserContext] = None,
        department_id: Optional[str] = None,
    ) -> AgentExecutionPlan:
        """Construct a high-level, bounded execution plan based on problem classification."""
        complexity = cls.classify_complexity(query)

        # Case 1: Direct Lookup (Fast Path)
        if complexity == TaskComplexity.DIRECT_LOOKUP:
            return AgentExecutionPlan(
                query=query,
                complexity=complexity,
                plan_summary="Direct repository retrieval and citation-grounded synthesis.",
                is_direct_lookup=True,
                steps=[
                    PlanStep(
                        step_id=1,
                        title="Repository Search & Citation Verification",
                        description="Retrieve authoritative Uttarakhand Government Orders and verify public evidence.",
                        action_type="search",
                        tool_name=AgentToolName.SEARCH.value,
                        tool_args={"query": query, "department_id": department_id},
                    ),
                    PlanStep(
                        step_id=2,
                        title="Governed Synthesis",
                        description="Synthesize grounded response strictly adhering to retrieved evidence.",
                        action_type="synthesize",
                    ),
                ],
            )

        # Case 2: System Introspection
        if complexity == TaskComplexity.SYSTEM_INTROSPECTION:
            return AgentExecutionPlan(
                query=query,
                complexity=complexity,
                plan_summary="Inspect authoritative system runtime state, model parameters, and capabilities.",
                is_direct_lookup=False,
                steps=[
                    PlanStep(
                        step_id=1,
                        title="System Introspection Inspection",
                        description="Retrieve authoritative snapshot of active model, harness profile, memory budget, and tool registry.",
                        action_type="introspection",
                        tool_name=AgentToolName.INSPECT_SYSTEM.value,
                        tool_args={"query": query},
                    ),
                    PlanStep(
                        step_id=2,
                        title="Authoritative System State Reporting",
                        description="Present objective ground truth of system capabilities and active telemetry.",
                        action_type="synthesize",
                    ),
                ],
            )

        # Case 2b: Database Inspection
        if complexity == TaskComplexity.DATABASE_INSPECTION:
            return AgentExecutionPlan(
                query=query,
                complexity=complexity,
                plan_summary="Query connected relational database tables for document counts and statistics.",
                is_direct_lookup=False,
                steps=[
                    PlanStep(
                        step_id=1,
                        title="Query Connected Database Records",
                        description="Inspect database records for document counts, statuses, or department aggregations.",
                        action_type="database",
                        tool_name=AgentToolName.DATABASE_QUERY.value,
                        tool_args={"table": "documents", "aggregate": "count"},
                    ),
                    PlanStep(
                        step_id=2,
                        title="Synthesize Grounded Database Report",
                        description="Report verified database figures and metadata summaries.",
                        action_type="synthesize",
                    ),
                ],
            )

        # Case 3: Quantitative Computation
        if complexity == TaskComplexity.QUANTITATIVE_COMPUTATION:
            # Extract basic numbers or parameters if present
            numbers = re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?\b", query)
            target_amount = numbers[0] if numbers else None

            steps = [
                PlanStep(
                    step_id=1,
                    title="Retrieve Relevant Government Orders & Statutory Rates",
                    description="Search repository for official orders detailing baseline and revised rates or formulas.",
                    action_type="search",
                    tool_name=AgentToolName.SEARCH.value,
                    tool_args={"query": query, "department_id": department_id, "top_k": 6},
                ),
                PlanStep(
                    step_id=2,
                    title="Execute Deterministic Calculation in Secure Sandbox",
                    description="Compute exact financial or statistical outcomes using isolated Python sandbox (math/datetime).",
                    action_type="compute",
                    tool_name=AgentToolName.EXECUTE_PYTHON_SANDBOX.value,
                    tool_args={"base_query": query, "target_amount": target_amount},
                ),
                PlanStep(
                    step_id=3,
                    title="Synthesize Grounded Response with Verified Proof",
                    description="Combine official order citations with verified mathematical proof.",
                    action_type="synthesize",
                ),
            ]
            return AgentExecutionPlan(
                query=query,
                complexity=complexity,
                plan_summary="Decompose query into statutory rate retrieval, secure sandbox computation, and grounded synthesis.",
                is_direct_lookup=False,
                steps=steps,
            )

        # Case 4: Precedent Tracking
        if complexity == TaskComplexity.PRECEDENT_TRACKING:
            steps = [
                PlanStep(
                    step_id=1,
                    title="Identify Primary Government Order",
                    description="Retrieve primary subject order and identify citation references.",
                    action_type="search",
                    tool_name=AgentToolName.SEARCH.value,
                    tool_args={"query": query, "department_id": department_id},
                ),
                PlanStep(
                    step_id=2,
                    title="Trace Precedent Chain (Superseded & Amending Orders)",
                    description="Query precedent relation graph for linked superseding and amending Government Orders.",
                    action_type="precedent",
                    tool_name=AgentToolName.LOOKUP_PRECEDENTS.value,
                    tool_args={"query": query},
                ),
                PlanStep(
                    step_id=3,
                    title="Synthesize Verified Chronological Administrative Authority",
                    description="Present legal hierarchy and currency status with explicit citations.",
                    action_type="synthesize",
                ),
            ]
            return AgentExecutionPlan(
                query=query,
                complexity=complexity,
                plan_summary="Trace administrative precedent hierarchy and amendments across repository records.",
                is_direct_lookup=False,
                steps=steps,
            )

        # Case 4b: External Web Research
        if complexity == TaskComplexity.EXTERNAL_WEB_RESEARCH:
            return AgentExecutionPlan(
                query=query,
                complexity=complexity,
                plan_summary="Perform fast local verification first, escalating to external web research if needed.",
                is_direct_lookup=False,
                steps=[
                    PlanStep(
                        step_id=1,
                        title="Local Repository Fast Verification",
                        description="Verify whether required factual authority exists in local public records.",
                        action_type="search",
                        tool_name=AgentToolName.SEARCH.value,
                        tool_args={"query": query, "department_id": department_id, "top_k": 5},
                    ),
                    PlanStep(
                        step_id=2,
                        title="External Web Research & Verification",
                        description="Conduct domain-aware external search and extract verified government portal provisions.",
                        action_type="web_research",
                        tool_name=AgentToolName.WEB_SEARCH.value,
                        tool_args={"query": query, "max_results": 3},
                    ),
                    PlanStep(
                        step_id=3,
                        title="Synthesize Grounded Multi-Source Brief",
                        description="Synthesize grounded answer clearly distinguishing internal orders from external web findings.",
                        action_type="synthesize",
                    ),
                ],
            )

        # Case 4c: Comparative Analysis
        if complexity == TaskComplexity.COMPARATIVE_RESEARCH:
            return AgentExecutionPlan(
                query=query,
                complexity=complexity,
                plan_summary="Retrieve relevant comparative records and execute structured delta analysis.",
                is_direct_lookup=False,
                steps=[
                    PlanStep(
                        step_id=1,
                        title="Retrieve Primary and Comparative Records",
                        description="Search repository for relevant orders, baseline rules, or amendments to compare.",
                        action_type="search",
                        tool_name=AgentToolName.SEARCH.value,
                        tool_args={"query": query, "department_id": department_id, "top_k": 6},
                    ),
                    PlanStep(
                        step_id=2,
                        title="Perform Structured Comparison Analysis",
                        description="Execute structured comparison between identified policy records and baseline provisions.",
                        action_type="compare",
                        tool_name=AgentToolName.COMPARE_SOURCES.value,
                        tool_args={"query": query},
                    ),
                    PlanStep(
                        step_id=3,
                        title="Synthesize Comparative Analytical Brief",
                        description="Present comparative differences, matching provisions, and official citations.",
                        action_type="synthesize",
                    ),
                ],
            )

        # Case 5: Multi-Step Analysis
        steps = [
            PlanStep(
                step_id=1,
                title="Retrieve Baseline Policy Records",
                description="Search repository for baseline regulations or earlier policy provisions.",
                action_type="search",
                tool_name=AgentToolName.SEARCH.value,
                tool_args={"query": query, "department_id": department_id, "top_k": 5},
            ),
            PlanStep(
                step_id=2,
                title="Verify Comparative Differences & Precedent Scope",
                description="Verify specific changes, exceptions, or departmental variations against repository passages.",
                action_type="verify",
                tool_name=AgentToolName.VERIFY_CLAIM.value,
                tool_args={"query": query},
            ),
            PlanStep(
                step_id=3,
                title="Synthesize Comparative Analytical Brief",
                description="Produce structured comparative summary with explicit passage citations.",
                action_type="synthesize",
            ),
        ]
        return AgentExecutionPlan(
            query=query,
            complexity=complexity,
            plan_summary="Perform multi-part comparative analysis across relevant public records.",
            is_direct_lookup=False,
            steps=steps,
        )
