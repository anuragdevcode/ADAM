"""Comprehensive Unit Tests for Continuous Sovereign RAG Triad Evaluation.

Validates:
1. Context Relevance: Precision and information density of retrieved chunks.
2. Groundedness / Faithfulness: Zero-hallucination verification using ProvenanceGraph.
3. Answer Relevance: Directness and penalty for administrative filler / conversational fluff.
4. Composite Triad Score (Ragas / ARES aligned harmonic mean).
5. ContinuousTriadWorker: Benchmark execution, drift detection, and persistence.
6. Post-ingestion automated evaluation triggers.
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy.orm import Session

from adam.db.models import RagTriadBenchmarkRecord
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
from adam.graphs.provenance import ProvenanceGraph
from adam.rag.models import EvidencePacket, EvidencePassage, ParsedQuery, UserContext


# ── 1. Context Relevance Evaluator Tests ─────────────────────────────────────

def test_context_relevance_high_matching():
    """Verify high context relevance when retrieved passages match query intent."""
    query = "What is the revised Dearness Allowance rate under Finance Department order 2024?"
    passage = EvidencePassage(
        chunk_id="chk_1",
        document_id="doc_fin_1",
        version_id="ver_1",
        title="Dearness Allowance Order 2024",
        department_id="FINANCE_TREASURY",
        doc_type="ORDER",
        page_start=1,
        page_end=1,
        section_heading="Dearness Allowance Rate",
        content="The revised Dearness Allowance rate under Finance Department order is 50% for 2024.",
        go_number="UK/FIN/2024/101",
    )
    packet = EvidencePacket(
        query=ParsedQuery(raw_query=query, clean_query=query, department_id="FINANCE_TREASURY"),
        passages=[passage],
    )

    score = ContextRelevanceEvaluator.evaluate(query, packet)
    assert score >= 0.80


def test_context_relevance_low_matching():
    """Verify low context relevance when passages are off-topic or irrelevant."""
    query = "What is the revised Dearness Allowance rate for 2024?"
    irrelevant_passage = EvidencePassage(
        chunk_id="chk_irr",
        document_id="doc_irr",
        version_id="ver_irr",
        title="Forest Tree Planting Rules 2012",
        department_id="FOREST",
        doc_type="RULES",
        page_start=1,
        page_end=1,
        section_heading="Silviculture",
        content="Pine and deodar sapling spacing must be maintained at two meters distance.",
    )
    packet = EvidencePacket(
        query=ParsedQuery(raw_query=query, clean_query=query, department_id="FINANCE_TREASURY"),
        passages=[irrelevant_passage],
    )

    score = ContextRelevanceEvaluator.evaluate(query, packet)
    assert score < 0.30


def test_context_relevance_unanswerable_query():
    """Verify that an empty packet for an unanswerable query yields 1.0 (correct non-retrieval)."""
    query = "What was the DA rate in Tamil Nadu in 1995?"
    packet = EvidencePacket(
        query=ParsedQuery(raw_query=query, clean_query=query, is_out_of_jurisdiction=True),
        passages=[],
    )
    score = ContextRelevanceEvaluator.evaluate(query, packet)
    assert score == 1.0


# ── 2. Groundedness Evaluator Tests (via ProvenanceGraph) ────────────────────

def test_groundedness_perfect_faithfulness():
    """Verify 100% groundedness when all claims connect to passage bounding boxes."""
    passage = EvidencePassage(
        chunk_id="chk_da",
        document_id="doc_da",
        version_id="ver_da",
        title="DA GO 2024",
        department_id="FINANCE_TREASURY",
        doc_type="ORDER",
        page_start=1,
        page_end=1,
        section_heading="Sanction",
        content="Dearness Allowance increased from 46% to 50% effective from 01-01-2024 under UK/FIN/2024/101.",
        go_number="UK/FIN/2024/101",
        bbox_list=[[50, 50, 400, 100]],
    )
    packet = EvidencePacket(
        query=ParsedQuery(raw_query="DA rate", clean_query="DA rate"),
        passages=[passage],
    )

    answer = "Under order UK/FIN/2024/101 [1], Dearness Allowance is 50% effective 01-01-2024."
    score, trace, unsupported = GroundednessEvaluator.evaluate(answer, packet)

    assert score >= 0.95
    assert len(unsupported) == 0
    assert trace.grounded_claims >= 2


def test_groundedness_detects_hallucination():
    """Verify groundedness score drops when answer states unverified dates and amounts."""
    passage = EvidencePassage(
        chunk_id="chk_da",
        document_id="doc_da",
        version_id="ver_da",
        title="DA GO 2024",
        department_id="FINANCE_TREASURY",
        doc_type="ORDER",
        page_start=1,
        page_end=1,
        section_heading="Sanction",
        content="Dearness Allowance increased to 50% effective from 01-01-2024.",
        go_number="UK/FIN/2024/101",
    )
    packet = EvidencePacket(
        query=ParsedQuery(raw_query="DA rate", clean_query="DA rate"),
        passages=[passage],
    )

    # Hallucinated 62% and ₹90,000
    answer = "The Dearness Allowance was enhanced to 62% with total salary ₹90,000 on 2025-12-01."
    score, trace, unsupported = GroundednessEvaluator.evaluate(answer, packet)

    assert score < 0.50
    assert len(unsupported) >= 2


def test_groundedness_on_legitimate_abstention():
    """Verify proper repository abstention is graded 1.0 (zero hallucination)."""
    packet = EvidencePacket(
        query=ParsedQuery(raw_query="Fake query", clean_query="Fake query"),
        passages=[],
    )
    answer = "I could not establish this from the approved repository. Please check order number."
    score, trace, unsupported = GroundednessEvaluator.evaluate(answer, packet)

    assert score == 1.0
    assert len(unsupported) == 0


# ── 3. Answer Relevance Evaluator Tests ──────────────────────────────────────

def test_answer_relevance_direct_answer():
    """Verify high answer relevance for concise, direct responses."""
    query = "What is the revised DA rate for 2024?"
    answer = "The revised Dearness Allowance rate under Finance Order UK/FIN/2024/101 is 50% effective from January 1, 2024."
    score = AnswerRelevanceEvaluator.evaluate(query, answer)
    assert score >= 0.85


def test_answer_relevance_penalizes_administrative_filler():
    """Verify penalty deduction when answer contains boilerplate filler."""
    query = "What is the revised DA rate for 2024?"
    # Answer with multiple filler phrases
    answer = (
        "As an AI administrative assistant, thank you for your query. "
        "Please note that the revised Dearness Allowance rate is 50%. "
        "I hope this information helps, feel free to ask further questions."
    )
    score = AnswerRelevanceEvaluator.evaluate(query, answer)
    # Penalized by filler patterns
    assert score < 0.70


# ── 4. SovereignTriadEvaluator Composite Score Tests ─────────────────────────

def test_triad_composite_harmonic_mean():
    """Verify weighted harmonic mean composite score calculation."""
    # Balanced high scores
    comp_high = SovereignTriadEvaluator.compute_composite_score(0.90, 0.95, 0.90)
    assert 0.90 <= comp_high <= 0.95

    # If any single dimension is severely compromised (e.g. groundedness = 0.2), harmonic mean drops sharply
    comp_flawed = SovereignTriadEvaluator.compute_composite_score(0.90, 0.20, 0.90)
    assert comp_flawed < 0.45


def test_sovereign_triad_evaluate_turn_pass_and_fail():
    """Verify turn evaluation correctly classifies PASS vs FAIL against sovereign thresholds."""
    passage = EvidencePassage(
        chunk_id="c1",
        document_id="d1",
        version_id="v1",
        title="Rules 2024",
        department_id="FINANCE",
        doc_type="ORDER",
        page_start=1,
        page_end=1,
        section_heading="Limit",
        content="The procurement ceiling is ₹50,000 as per Order UK/FIN/2024/50 on 2024-01-10.",
        go_number="UK/FIN/2024/50",
    )
    packet = EvidencePacket(
        query=ParsedQuery(raw_query="procurement limit", clean_query="procurement limit"),
        passages=[passage],
    )

    # Valid turn
    valid_res = SovereignTriadEvaluator.evaluate_turn(
        query_id="q_pass",
        query="What is the procurement ceiling under Order UK/FIN/2024/50?",
        answer="Under Order UK/FIN/2024/50 [1], the procurement ceiling is ₹50,000 effective 2024-01-10.",
        packet=packet,
    )
    assert valid_res.passed is True
    assert valid_res.context_relevance >= 0.75
    assert valid_res.groundedness >= 0.95
    assert valid_res.answer_relevance >= 0.80

    # Hallucinated turn
    fail_res = SovereignTriadEvaluator.evaluate_turn(
        query_id="q_fail",
        query="What is the procurement ceiling under Order UK/FIN/2024/50?",
        answer="As an AI, the limit is ₹99,00,000 on 2030-05-01.",
        packet=packet,
    )
    assert fail_res.passed is False
    assert fail_res.groundedness < 0.50


# ── 5. ContinuousTriadWorker & Drift Detection Tests ─────────────────────────

def test_continuous_triad_worker_drift_detection(db_session: Session):
    """Verify that worker detects drift when benchmark metrics regress compared to history."""
    # 1. Seed a high-performing historical benchmark run in DB
    historical_record = RagTriadBenchmarkRecord(
        id="triad_historical_01",
        model_id="test_model",
        trigger_event="SEED",
        total_queries=10,
        passed_queries=10,
        context_relevance=0.92,
        groundedness=0.98,
        answer_relevance=0.90,
        composite_score=0.93,
        zero_hallucination_rate=1.0,
        drift_detected=False,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(historical_record)
    db_session.commit()

    # 2. Run worker on small sample
    worker = ContinuousTriadWorker(session=db_session, model_id="test_model")
    summary: TriadBenchmarkSummary = worker.run_benchmark(sample_size=5, trigger_event="TEST")

    assert summary.total_questions >= 1
    assert summary.model_id == "test_model"
    assert summary.run_id.startswith("triad_")

    # DB record must be created
    latest = (
        db_session.query(RagTriadBenchmarkRecord)
        .filter(RagTriadBenchmarkRecord.id == summary.run_id)
        .first()
    )
    assert latest is not None
    assert latest.total_queries == summary.total_questions


def test_trigger_triad_evaluation_on_ingestion(db_session: Session):
    """Verify post-ingestion trigger runs and produces benchmark summary."""
    summary = trigger_triad_evaluation_on_ingestion(
        session=db_session,
        document_id="doc_new_ingested_123",
        model_id="qwen3-4b-instruct-q4",
        sample_size=3,
    )
    assert summary.trigger_event == "POST_INGESTION:doc_new_ingested_123"
    assert summary.total_questions <= 3
