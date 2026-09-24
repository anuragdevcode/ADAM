"""Continuous Sovereign RAG Triad Evaluation Worker.

Monitors answer quality, groundedness, and retrieval precision against a golden
benchmark of Uttarakhand administrative questions whenever new government orders
are ingested or on a scheduled cadence.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from adam.agent.state_machine import BoundedAgentStateMachine
from adam.db.models import RagTriadBenchmarkRecord
from adam.evaluation.triad import (
    SovereignTriadEvaluator,
    TriadBenchmarkSummary,
    TriadItemResult,
)
from adam.observability.events import (
    OperationalEvent,
    OperationalEventEmitter,
    OperationalEventType,
)
from adam.rag.evaluation import populate_eval_corpus
from adam.rag.gold_set import generate_gold_questions
from adam.rag.models import EvidencePacket, EvidencePassage, ParsedQuery, UserContext
from adam.rag.pipeline import RagPipeline

logger = logging.getLogger(__name__)


class ContinuousTriadWorker:
    """Automated benchmark worker evaluating continuous RAG Triad health."""

    def __init__(
        self,
        session: Session,
        model_id: str = "qwen3-4b-instruct-q4",
        emitter: Optional[OperationalEventEmitter] = None,
    ):
        self.session = session
        self.model_id = model_id
        self.emitter = emitter

    def run_benchmark(
        self,
        sample_size: Optional[int] = 20,
        trigger_event: str = "MANUAL",
        categories: Optional[List[str]] = None,
    ) -> TriadBenchmarkSummary:
        """Run continuous RAG Triad evaluation against the golden benchmark suite."""
        start_time = time.perf_counter()
        run_id = f"triad_{uuid.uuid4().hex[:10]}"

        # 1. Ensure evaluation corpus is populated
        try:
            populate_eval_corpus(self.session)
        except Exception as e:
            logger.warning("Eval corpus check note: %s", e)

        # 2. Fetch golden questions
        all_questions = generate_gold_questions()
        if categories:
            all_questions = [q for q in all_questions if q.get("category") in categories]

        # Subsample if requested
        if sample_size and len(all_questions) > sample_size:
            # Deterministic, balanced sampling
            step = max(1, len(all_questions) // sample_size)
            selected_questions = all_questions[::step][:sample_size]
        else:
            selected_questions = all_questions

        pipeline = RagPipeline(self.session)
        items: List[TriadItemResult] = []

        dept_aggregates: Dict[str, List[float]] = {}
        lang_aggregates: Dict[str, List[float]] = {}
        cat_aggregates: Dict[str, List[float]] = {}

        # 3. Evaluate each golden question
        for idx, q_spec in enumerate(selected_questions, start=1):
            q_id = q_spec.get("id", f"q_{idx}")
            q_text = q_spec.get("question") or q_spec.get("query", "")
            q_lang = q_spec.get("language", "en")
            q_dept = q_spec.get("department") or q_spec.get("department_id")
            q_cat = q_spec.get("category", "general")

            raw_ctx = q_spec.get("user_context")
            if raw_ctx and isinstance(raw_ctx, dict):
                user = UserContext(
                    user_id=raw_ctx.get("user_id", f"eval_officer_{idx}"),
                    roles=raw_ctx.get("roles", ["OFFICER"]),
                    department_id=raw_ctx.get("department_id", q_dept),
                    clearance_level=raw_ctx.get("clearance_level", "PUBLIC"),
                )
            else:
                user = UserContext(
                    user_id=f"eval_officer_{idx}",
                    roles=["OFFICER"],
                    department_id=q_dept,
                    clearance_level="PUBLIC",
                )

            # Execute RAG turn
            try:
                rag_resp = pipeline.query(question=q_text, user_context=user)
                answer = rag_resp.answer
                packet = rag_resp.evidence_packet
            except Exception as e:
                logger.error("Error evaluating query '%s': %s", q_text, e)
                answer = "I could not establish this from the approved repository."
                packet = EvidencePacket(query=ParsedQuery(raw_query=q_text, clean_query=q_text), passages=[])

            # Evaluate RAG Triad
            item_res = SovereignTriadEvaluator.evaluate_turn(
                query_id=q_id,
                query=q_text,
                answer=answer,
                packet=packet,
                language=q_lang,
                department_id=q_dept,
                category=q_cat,
            )
            items.append(item_res)

            # Record aggregates
            dept_key = q_dept or "GENERAL"
            dept_aggregates.setdefault(dept_key, []).append(item_res.composite_score)
            lang_aggregates.setdefault(q_lang, []).append(item_res.composite_score)
            cat_aggregates.setdefault(q_cat, []).append(item_res.composite_score)

        # 4. Compute overall metrics
        total = len(items)
        passed_count = sum(1 for it in items if it.passed)
        pass_rate = (passed_count / total) if total > 0 else 0.0

        mean_cr = sum(it.context_relevance for it in items) / total if total > 0 else 0.0
        mean_g = sum(it.groundedness for it in items) / total if total > 0 else 0.0
        mean_ar = sum(it.answer_relevance for it in items) / total if total > 0 else 0.0
        mean_comp = sum(it.composite_score for it in items) / total if total > 0 else 0.0
        zero_hallucination = sum(1 for it in items if it.groundedness >= 0.99) / total if total > 0 else 0.0

        by_dept = {k: {"mean_score": round(sum(v) / len(v), 4), "count": len(v)} for k, v in dept_aggregates.items()}
        by_lang = {k: {"mean_score": round(sum(v) / len(v), 4), "count": len(v)} for k, v in lang_aggregates.items()}
        by_cat = {k: {"mean_score": round(sum(v) / len(v), 4), "count": len(v)} for k, v in cat_aggregates.items()}

        duration = time.perf_counter() - start_time

        # 5. Continuous Drift Detection
        drift_detected = False
        drift_notes: List[str] = []

        last_record = (
            self.session.query(RagTriadBenchmarkRecord)
            .filter(RagTriadBenchmarkRecord.model_id == self.model_id)
            .order_by(RagTriadBenchmarkRecord.created_at.desc())
            .first()
        )

        if last_record:
            if (last_record.groundedness - mean_g) >= 0.05:
                drift_detected = True
                drift_notes.append(
                    f"Groundedness regression detected: dropped from {last_record.groundedness:.3f} to {mean_g:.3f}"
                )
            if (last_record.context_relevance - mean_cr) >= 0.08:
                drift_detected = True
                drift_notes.append(
                    f"Context relevance degradation detected: dropped from {last_record.context_relevance:.3f} to {mean_cr:.3f}"
                )
            if (last_record.composite_score - mean_comp) >= 0.05:
                drift_detected = True
                drift_notes.append(
                    f"Overall composite score drift: dropped from {last_record.composite_score:.3f} to {mean_comp:.3f}"
                )

        summary = TriadBenchmarkSummary(
            run_id=run_id,
            model_id=self.model_id,
            trigger_event=trigger_event,
            total_questions=total,
            passed_questions=passed_count,
            mean_context_relevance=round(mean_cr, 4),
            mean_groundedness=round(mean_g, 4),
            mean_answer_relevance=round(mean_ar, 4),
            mean_composite_score=round(mean_comp, 4),
            zero_hallucination_rate=round(zero_hallucination, 4),
            pass_rate=round(pass_rate, 4),
            by_department=by_dept,
            by_language=by_lang,
            by_category=by_cat,
            drift_detected=drift_detected,
            drift_notes=drift_notes,
            duration_seconds=round(duration, 2),
            items=items,
        )

        # 6. Persist benchmark result to database
        db_record = RagTriadBenchmarkRecord(
            id=run_id,
            model_id=self.model_id,
            trigger_event=trigger_event,
            total_queries=total,
            passed_queries=passed_count,
            context_relevance=round(mean_cr, 4),
            groundedness=round(mean_g, 4),
            answer_relevance=round(mean_ar, 4),
            composite_score=round(mean_comp, 4),
            zero_hallucination_rate=round(zero_hallucination, 4),
            drift_detected=drift_detected,
            drift_notes_json=drift_notes,
            department_scores_json=by_dept,
            language_scores_json=by_lang,
            duration_seconds=round(duration, 2),
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(db_record)
        self.session.commit()

        # 7. Emit operational telemetry event
        if self.emitter:
            self.emitter.emit(
                OperationalEventType.BENCHMARK_EVALUATED,
                stage="evaluation",
                status="completed" if not drift_detected else "warning",
                message=f"RAG Triad Benchmark completed (Composite: {mean_comp:.3f}, Groundedness: {mean_g:.3f})",
                data=summary.to_dict(),
            )

        return summary


def trigger_triad_evaluation_on_ingestion(
    session: Session,
    document_id: str,
    model_id: str = "qwen3-4b-instruct-q4",
    sample_size: int = 15,
) -> TriadBenchmarkSummary:
    """Automated post-ingestion trigger validating that new document ingestion did not degrade benchmark metrics."""
    logger.info("Triggering post-ingestion RAG Triad evaluation for document %s", document_id)
    worker = ContinuousTriadWorker(session=session, model_id=model_id)
    return worker.run_benchmark(
        sample_size=sample_size,
        trigger_event=f"POST_INGESTION:{document_id}",
    )
