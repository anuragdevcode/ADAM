"""Agent execution audit and state machine governance endpoints."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from adam.api.deps import get_db, get_user_context
from adam.db.models import AgentExecutionAudit
from adam.rag.models import UserContext

router = APIRouter()


@router.get("/audit/executions")
def list_execution_audits(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> List[Dict[str, Any]]:
    """Return immutable records of bounded 7-stage state machine executions."""
    records = (
        db.query(AgentExecutionAudit)
        .order_by(AgentExecutionAudit.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "user_id": r.user_id,
            "user_role": r.user_role,
            "clearance_level": r.clearance_level,
            "query_text": r.query_text,
            "model_id": r.model_id,
            "retrieval_pass_count": r.retrieval_pass_count,
            "answer_pass_count": r.answer_pass_count,
            "is_no_answer": bool(r.is_no_answer),
            "is_high_risk": bool(r.is_high_risk),
            "validation_passed": bool(r.validation_passed),
            "latency_ms": round(r.latency_ms, 2),
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "state_transitions": r.state_transitions_json or [],
            "tool_calls": r.tool_calls_json or [],
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]


@router.get("/audit/metrics")
def get_audit_metrics(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> Dict[str, Any]:
    """Compute aggregate execution statistics including average response time and per-stage latency breakdown."""
    records = (
        db.query(AgentExecutionAudit)
        .order_by(AgentExecutionAudit.created_at.desc())
        .limit(limit)
        .all()
    )
    if not records:
        return {
            "total_executions": 0,
            "avg_latency_ms": 0.0,
            "avg_stage_latencies_ms": {},
            "abstention_count": 0,
            "abstention_rate_pct": 0.0,
            "abstention_reasons": {},
        }

    total_executions = len(records)
    total_latency = sum(r.latency_ms for r in records if r.latency_ms is not None)
    avg_latency = round(total_latency / total_executions, 2)

    # Accumulate per-stage durations from state transitions
    stage_durations: Dict[str, List[float]] = {}
    abstention_reasons: Dict[str, int] = {}
    abstention_count = 0

    for r in records:
        if r.is_no_answer:
            abstention_count += 1

        for t in (r.state_transitions_json or []):
            if isinstance(t, dict):
                st = t.get("stage") or t.get("from")
                dur = t.get("duration_ms")
                if st and dur is not None and isinstance(dur, (int, float)):
                    stage_durations.setdefault(st, []).append(float(dur))

                reason = t.get("abstention_reason")
                if reason:
                    abstention_reasons[reason] = abstention_reasons.get(reason, 0) + 1

    avg_stage_latencies = {
        st: round(sum(durs) / len(durs), 2)
        for st, durs in stage_durations.items()
        if durs
    }

    abstention_rate = round((abstention_count / total_executions) * 100.0, 1)

    return {
        "total_executions": total_executions,
        "avg_latency_ms": avg_latency,
        "avg_stage_latencies_ms": avg_stage_latencies,
        "abstention_count": abstention_count,
        "abstention_rate_pct": abstention_rate,
        "abstention_reasons": abstention_reasons,
    }

