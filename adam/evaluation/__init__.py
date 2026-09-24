"""ADAM Evaluation, Benchmark Metrics, and Continuous Sovereign RAG Triad package."""

from adam.evaluation.metrics import (
    character_error_rate,
    compute_abstention_metrics,
    compute_citation_coverage,
    compute_latency_percentiles,
    compute_ndcg,
    compute_unsupported_claim_rate,
    compute_user_correction_rate,
    word_error_rate,
)
from adam.evaluation.triad import (
    AnswerRelevanceEvaluator,
    ContextRelevanceEvaluator,
    GroundednessEvaluator,
    SovereignTriadEvaluator,
    TriadBenchmarkSummary,
    TriadItemResult,
)
from adam.evaluation.worker import (
    ContinuousTriadWorker,
    trigger_triad_evaluation_on_ingestion,
)

__all__ = [
    "compute_ndcg",
    "compute_citation_coverage",
    "compute_unsupported_claim_rate",
    "compute_abstention_metrics",
    "compute_latency_percentiles",
    "word_error_rate",
    "character_error_rate",
    "compute_user_correction_rate",
    "ContextRelevanceEvaluator",
    "GroundednessEvaluator",
    "AnswerRelevanceEvaluator",
    "SovereignTriadEvaluator",
    "TriadItemResult",
    "TriadBenchmarkSummary",
    "ContinuousTriadWorker",
    "trigger_triad_evaluation_on_ingestion",
]
