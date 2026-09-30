"""Dynamic Capability Router and Real-Time Evidence Stopping Engine for ADAM.

Enables ADAM to:
1. Intelligently determine the minimal, highest-precision sequence of capabilities
   (repository search, graph traversal, database query, controlled sandbox calculation,
   approved external sources, or specialist agent delegation).
2. Continuously evaluate evidence convergence and claim sufficiency, stopping
   exploratory tool calls immediately once sufficient evidence is established.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from adam.capabilities.models import CapabilityDescriptor
from adam.rag.models import EvidencePassage, UserContext
from adam.vocabularies import Classification

logger = logging.getLogger(__name__)


@dataclass
class StoppingAssessment:
    """Real-time assessment of whether gathered evidence suffices to stop execution."""
    can_stop: bool
    confidence: float
    reason: str
    total_local_passages: int
    total_external_passages: int
    has_supersession_conflict: bool = False
    has_verified_calculation: bool = False


class EvidenceStoppingEvaluator:
    """Continuously evaluates evidence convergence to halt execution without over-fetching."""

    MIN_PASSAGE_SCORE_THRESHOLD: float = 0.25
    MIN_CONTENT_LENGTH: int = 120

    @classmethod
    def evaluate(
        cls,
        query: str,
        accumulated_passages: List[EvidencePassage],
        verified_calculations: Optional[List[Dict[str, Any]]] = None,
        precedents_identified: Optional[List[Dict[str, Any]]] = None,
    ) -> StoppingAssessment:
        clean_q = query.strip().lower()
        local_passages = [p for p in accumulated_passages if not getattr(p, "is_external", False)]
        ext_passages = [p for p in accumulated_passages if getattr(p, "is_external", False)]

        # Check for supersession conflicts
        has_supersession_conflict = any(
            getattr(p, "currency_status", "") == "SUPERSEDED" or getattr(p, "has_conflict", False)
            for p in local_passages
        )

        has_verified_calc = bool(verified_calculations and len(verified_calculations) > 0)

        # 1. Zero evidence gathered yet
        if not accumulated_passages:
            return StoppingAssessment(
                can_stop=False,
                confidence=0.0,
                reason="No evidence passages retrieved yet.",
                total_local_passages=0,
                total_external_passages=0,
            )

        # 2. Check if calculation was required and whether it has completed
        math_needed = any(w in clean_q for w in ("calculate", "compute", "how much increase", "formula", "गणना"))
        if math_needed and not has_verified_calc:
            return StoppingAssessment(
                can_stop=False,
                confidence=0.4,
                reason="Query requires numerical calculation proof which has not yet been verified.",
                total_local_passages=len(local_passages),
                total_external_passages=len(ext_passages),
            )

        # 3. Check if query asks for out-of-repository / national entities
        external_need = any(w in clean_q for w in (
            "central government", "central da", "national", "union government",
            "other states", "doe.gov.in", "delhi", "outside uttarakhand", "central 7th cpc",
        ))
        if external_need and len(ext_passages) == 0:
            return StoppingAssessment(
                can_stop=False,
                confidence=0.5,
                reason="Query explicitly references external/national entities; external source needed.",
                total_local_passages=len(local_passages),
                total_external_passages=0,
            )

        # 4. Check quality and substance of local passages
        total_content = sum(len(p.content or "") for p in local_passages)
        top_score = max((getattr(p, "score", 0.0) for p in local_passages), default=0.0)

        if len(local_passages) >= 2 and total_content >= cls.MIN_CONTENT_LENGTH and top_score >= cls.MIN_PASSAGE_SCORE_THRESHOLD:
            return StoppingAssessment(
                can_stop=True,
                confidence=0.95,
                reason=f"Authoritative local records converged ({len(local_passages)} passages, score={top_score:.2f}).",
                total_local_passages=len(local_passages),
                total_external_passages=len(ext_passages),
                has_supersession_conflict=has_supersession_conflict,
                has_verified_calculation=has_verified_calc,
            )

        if len(local_passages) >= 1 and total_content >= 200:
            return StoppingAssessment(
                can_stop=True,
                confidence=0.85,
                reason="Sufficient local repository context acquired to synthesize grounded response.",
                total_local_passages=len(local_passages),
                total_external_passages=len(ext_passages),
                has_supersession_conflict=has_supersession_conflict,
                has_verified_calculation=has_verified_calc,
            )

        return StoppingAssessment(
            can_stop=False,
            confidence=0.5,
            reason="Passage coverage is marginal; additional context exploration permitted.",
            total_local_passages=len(local_passages),
            total_external_passages=len(ext_passages),
        )


class CapabilityRouter:
    """Intelligently plans and orders capability invocations for a given user query."""

    @classmethod
    def select_capabilities_for_query(
        cls,
        query: str,
        user_context: Optional[UserContext],
        registry: Any,
    ) -> List[str]:
        """Determine optimal ordered capability IDs based on query semantics, clearance, and safety."""
        clean_q = query.strip().lower()
        selected: List[str] = []

        is_air_gapped = False
        if user_context and user_context.clearance_level in (
            Classification.RESTRICTED.value,
            Classification.CONFIDENTIAL.value,
        ):
            is_air_gapped = True

        # 1. System Introspection
        if any(w in clean_q for w in ("what model", "which model", "active model", "harness", "system state", "self-model", "allowed tools", "capabilities")):
            return ["inspect_system"]

        # 2. Database Counts / Inventory Queries
        if any(w in clean_q for w in ("how many documents", "total orders", "database stats", "records count", "count of documents")):
            selected.append("database_query")

        # 3. Always prioritize primary local repository retrieval for administrative knowledge
        selected.append("search")

        # 4. Precedent DAG Traversal / Amendment Checks
        if any(w in clean_q for w in ("supersede", "amend", "precedent", "order chain", "history of", "in continuation")):
            selected.append("traverse_precedent_dag")

        # 5. Deterministic Arithmetic / Sandbox Calculations
        if any(w in clean_q for w in ("calculate", "compute", "allowance", "increase on", "basic pay", "da calculation", "formula")):
            selected.append("execute_python_sandbox")

        # 6. Multi-source Delta Comparison
        if any(w in clean_q for w in ("compare", "comparison", "difference between", "versus", "vs")):
            selected.append("compare_sources")

        # 7. External Web Research (Strictly gated: only if not air-gapped)
        if not is_air_gapped:
            external_need = any(w in clean_q for w in (
                "central government", "central da", "national policy", "delhi", "union government", "doe.gov.in",
            ))
            if external_need:
                selected.append("web_search")
                selected.append("fetch_web_page")

        # 8. Always conclude with token/semantic claim verification
        selected.append("verify_claim")

        # Filter by actual registry availability and user clearance
        available = {c["id"] for c in registry.list_capabilities(user_context=user_context, filter_unavailable=True)}
        final_sequence = [cid for cid in selected if cid in available]
        return final_sequence
