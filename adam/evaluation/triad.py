"""Sovereign RAG Triad Evaluator (Ragas / ARES Aligned).

Evaluates the three essential legs of administrative document intelligence:
1. Context Relevance: Precision and information density of retrieved evidence chunks relative to query intent.
2. Groundedness / Faithfulness: Zero-hallucination verification using ProvenanceGraph connecting claims to PDF blocks.
3. Answer Relevance: Direct, actionable answers devoid of introductory administrative filler or conversational fluff.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from adam.graphs.provenance import ProvenanceGraph, ProvenanceTraceResult
from adam.rag.generator import CitationValidator
from adam.rag.models import EvidencePacket, EvidencePassage

logger = logging.getLogger(__name__)


@dataclass
class TriadItemResult:
    """Evaluation result for an individual question turn."""
    query_id: str
    query_text: str
    language: str
    department_id: Optional[str]
    category: str
    context_relevance: float
    groundedness: float
    answer_relevance: float
    composite_score: float
    passed: bool
    unsupported_claims: List[str] = field(default_factory=list)
    provenance_trace: Optional[ProvenanceTraceResult] = None
    answer: str = ""
    notes: Optional[str] = None


@dataclass
class TriadBenchmarkSummary:
    """Consolidated report across a golden benchmark evaluation suite."""
    run_id: str
    model_id: str
    trigger_event: str
    total_questions: int
    passed_questions: int
    mean_context_relevance: float
    mean_groundedness: float
    mean_answer_relevance: float
    mean_composite_score: float
    zero_hallucination_rate: float
    pass_rate: float
    by_department: Dict[str, Dict[str, float]] = field(default_factory=dict)
    by_language: Dict[str, Dict[str, float]] = field(default_factory=dict)
    by_category: Dict[str, Dict[str, float]] = field(default_factory=dict)
    drift_detected: bool = False
    drift_notes: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    items: List[TriadItemResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "model_id": self.model_id,
            "trigger_event": self.trigger_event,
            "total_questions": self.total_questions,
            "passed_questions": self.passed_questions,
            "pass_rate": round(self.pass_rate, 2),
            "mean_context_relevance": round(self.mean_context_relevance, 4),
            "mean_groundedness": round(self.mean_groundedness, 4),
            "mean_answer_relevance": round(self.mean_answer_relevance, 4),
            "mean_composite_score": round(self.mean_composite_score, 4),
            "zero_hallucination_rate": round(self.zero_hallucination_rate, 4),
            "drift_detected": self.drift_detected,
            "drift_notes": self.drift_notes,
            "duration_seconds": round(self.duration_seconds, 2),
            "by_department": self.by_department,
            "by_language": self.by_language,
            "by_category": self.by_category,
        }


class ContextRelevanceEvaluator:
    """Calculates precision and signal-to-noise ratio of retrieved chunks against query intent."""

    # Stopwords to filter out before computing keyword match density
    COMMON_STOPWORDS = {
        "what", "is", "the", "under", "for", "and", "of", "in", "to", "a", "an", "on", "as",
        "per", "by", "with", "from", "at", "about", "which", "are", "be", "been", "was", "were",
        "क्या", "है", "के", "की", "में", "पर", "और", "से", "को", "का", "लिए", "द्वारा", "तथा",
    }

    @classmethod
    def evaluate(cls, query: str, packet: EvidencePacket) -> float:
        """Compute context relevance score in [0.0, 1.0]."""
        if not packet.passages:
            # If query is an unanswerable or zero-evidence case, 0 passages is 100% relevant precision
            return 1.0 if getattr(packet.query, "is_no_answer", False) or getattr(packet.query, "is_out_of_jurisdiction", False) else 0.0

        # Extract substantive terms from query (length >= 3, not in stopwords)
        q_tokens = [
            t.lower().strip()
            for t in re.findall(r"\b\w+\b", query, flags=re.UNICODE)
            if len(t) >= 3 and t.lower() not in cls.COMMON_STOPWORDS
        ]

        if not q_tokens:
            return 1.0

        passage_scores: List[float] = []

        for p in packet.passages:
            p_text = f"{p.title} {p.section_heading or ''} {p.content} {p.go_number or ''}".lower()
            matching_tokens = sum(1 for t in q_tokens if t in p_text)
            token_precision = matching_tokens / len(q_tokens)

            # Department alignment bonus
            dept_bonus = 0.1 if packet.query.department_id and p.department_id == packet.query.department_id else 0.0
            p_score = min(1.0, token_precision + dept_bonus)
            passage_scores.append(p_score)

        avg_score = sum(passage_scores) / len(passage_scores)
        return round(min(1.0, max(0.0, avg_score)), 4)


class GroundednessEvaluator:
    """Evaluates strict faithfulness using ProvenanceGraph down to verified PDF blocks."""

    ABSTENTION_PHRASES = [
        "could not establish this from the approved repository",
        "could not establish",
        "not established from the approved repository",
        "no verified records found",
    ]

    @classmethod
    def evaluate(
        cls,
        answer: str,
        packet: EvidencePacket,
    ) -> Tuple[float, ProvenanceTraceResult, List[str]]:
        """Compute groundedness score in [0.0, 1.0], provenance trace, and ungrounded claims."""
        if not answer:
            return 0.0, ProvenanceTraceResult(0, 0, 0.0), []

        # Check for legitimate abstention
        answer_lower = answer.lower()
        if any(phrase in answer_lower for phrase in cls.ABSTENTION_PHRASES):
            # Proper refusal: 100% faithful to the lack of evidence
            trace = ProvenanceGraph.build_trace(answer, packet)
            return 1.0, trace, []

        # Build provenance trace linking answer claims to PDF passages
        trace: ProvenanceTraceResult = ProvenanceGraph.build_trace(answer, packet)

        # Extract ungrounded claims
        unsupported: List[str] = []
        grounded_claim_ids = {e.source_id for e in trace.edges if e.relation == "GROUNDS"}
        for n in trace.nodes:
            if n.node_type.value == "CLAIM" and n.node_id not in grounded_claim_ids:
                unsupported.append(n.label)

        if trace.total_claims > 0:
            score = trace.coverage_ratio
        else:
            # Fallback for answers with no explicit dates/numbers: lexical token containment in passages
            evidence_corpus = " ".join(p.content for p in packet.passages).lower()
            ans_tokens = [t for t in re.findall(r"\b\w{4,}\b", answer_lower) if t not in ContextRelevanceEvaluator.COMMON_STOPWORDS]
            if ans_tokens:
                matched = sum(1 for t in ans_tokens if t in evidence_corpus)
                score = min(1.0, matched / len(ans_tokens))
            else:
                score = 1.0

        return round(score, 4), trace, unsupported


class AnswerRelevanceEvaluator:
    """Evaluates query directness and deducts penalties for administrative filler."""

    # Disallowed administrative filler / boilerplate phrases
    FILLER_PATTERNS = [
        re.compile(r"\b(?:as an ai|as an assistant|as an artificial intelligence)\b", re.I),
        re.compile(r"\b(?:i hope this information helps|i hope this helps|feel free to ask)\b", re.I),
        re.compile(r"\b(?:thank you for (?:your )?(?:question|query|inquiry))\b", re.I),
        re.compile(r"\b(?:i am pleased to (?:inform|advise) you)\b", re.I),
        re.compile(r"\b(?:please note that|kindly be informed that|it may be noted that)\b", re.I),
        re.compile(r"(?:कृपया ध्यान दें कि|आपको अवगत कराया जाता है कि|आशा है कि यह जानकारी सहायक होगी)", re.U),
    ]

    @classmethod
    def evaluate(cls, query: str, answer: str) -> float:
        """Compute answer relevance score in [0.0, 1.0]."""
        if not answer:
            return 0.0

        # Base relevance: check if answer provides substantive content
        if len(answer.strip()) < 15:
            return 0.2

        # 1. Check keyword coverage of query in answer
        q_tokens = [
            t.lower() for t in re.findall(r"\b\w{3,}\b", query)
            if t.lower() not in ContextRelevanceEvaluator.COMMON_STOPWORDS
        ]
        matched_tokens = sum(1 for t in q_tokens if t in answer.lower())
        token_coverage = (matched_tokens / len(q_tokens)) if q_tokens else 1.0

        base_score = 0.5 + (0.5 * token_coverage)

        # 2. Check and penalize administrative filler
        filler_penalty = 0.0
        for pattern in cls.FILLER_PATTERNS:
            if pattern.search(answer):
                filler_penalty += 0.15

        final_score = max(0.0, min(1.0, base_score - filler_penalty))
        return round(final_score, 4)


class SovereignTriadEvaluator:
    """Coordinates calculation of the continuous RAG Triad benchmark."""

    # Governance Pass/Fail Thresholds
    THRESHOLD_CONTEXT_RELEVANCE = 0.75
    THRESHOLD_GROUNDEDNESS = 0.95
    THRESHOLD_ANSWER_RELEVANCE = 0.80
    THRESHOLD_COMPOSITE = 0.85

    @classmethod
    def compute_composite_score(
        cls,
        context_relevance: float,
        groundedness: float,
        answer_relevance: float,
    ) -> float:
        """Calculate weighted harmonic mean across the three triad dimensions."""
        cr = max(0.01, context_relevance)
        g = max(0.01, groundedness)
        ar = max(0.01, answer_relevance)
        harmonic_mean = 3.0 / ((1.0 / cr) + (1.0 / g) + (1.0 / ar))
        return round(harmonic_mean, 4)

    @classmethod
    def evaluate_turn(
        cls,
        query_id: str,
        query: str,
        answer: str,
        packet: EvidencePacket,
        language: str = "en",
        department_id: Optional[str] = None,
        category: str = "known_answer",
    ) -> TriadItemResult:
        """Evaluate a single question turn against all three RAG Triad dimensions."""
        # 1. Context Relevance
        ctx_rel = ContextRelevanceEvaluator.evaluate(query, packet)

        # 2. Groundedness / Faithfulness (via ProvenanceGraph)
        groundedness, trace, unsupported = GroundednessEvaluator.evaluate(answer, packet)

        # 3. Answer Relevance
        ans_rel = AnswerRelevanceEvaluator.evaluate(query, answer)

        # 4. Composite Score
        composite = cls.compute_composite_score(ctx_rel, groundedness, ans_rel)

        passed = (
            ctx_rel >= cls.THRESHOLD_CONTEXT_RELEVANCE
            and groundedness >= cls.THRESHOLD_GROUNDEDNESS
            and ans_rel >= cls.THRESHOLD_ANSWER_RELEVANCE
            and composite >= cls.THRESHOLD_COMPOSITE
        )

        return TriadItemResult(
            query_id=query_id,
            query_text=query,
            language=language,
            department_id=department_id,
            category=category,
            context_relevance=ctx_rel,
            groundedness=groundedness,
            answer_relevance=ans_rel,
            composite_score=composite,
            passed=passed,
            unsupported_claims=unsupported,
            provenance_trace=trace,
            answer=answer,
        )
