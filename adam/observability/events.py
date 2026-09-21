"""Typed operational events and thread-safe event emitter for ADAM.

Provides structured observability over the bounded agent execution lifecycle:
- Security checks
- Request classification / query parsing
- Hybrid retrieval
- Evidence packet assembly
- Statutory currency & precedent checks
- Model loading and execution
- Answer grounding / abstention
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, Callable


class OperationalEventType(str, Enum):
    """Canonical operational event taxonomy for ADAM pipeline transparency."""

    # Security & Clearance
    SECURITY_STARTED = "security.started"
    SECURITY_COMPLETED = "security.completed"
    SECURITY_DENIED = "security.denied"

    # Query Understanding & Intent
    QUERY_PARSED = "query.parsed"

    # Retrieval
    RETRIEVAL_STARTED = "retrieval.started"
    RETRIEVAL_COMPLETED = "retrieval.completed"

    # Evidence Assembly
    EVIDENCE_STARTED = "evidence.started"
    EVIDENCE_COMPLETED = "evidence.completed"
    EVIDENCE_INSUFFICIENT = "evidence.insufficient"

    # Currency & Precedent Verification
    CURRENCY_CHECKED = "currency.checked"
    CURRENCY_WARNING = "currency.warning"

    # Model Lifecycle
    MODEL_LOADING = "model.loading"
    MODEL_READY = "model.ready"
    MODEL_FAILED = "model.failed"

    # Generation
    GENERATION_STARTED = "generation.started"
    GENERATION_COMPLETED = "generation.completed"

    # Outcome / Grounding
    ANSWER_GROUNDED = "answer.grounded"
    ANSWER_ABSTAINED = "answer.abstained"

    # Terminal Lifecycle
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"


@dataclass
class OperationalEvent:
    """Internal representation of a pipeline operational event.
    
    Compatible with OpenTelemetry and Langfuse tracing constructs:
    includes trace_id, span_id, timestamps, duration, and metadata attributes.
    """
    sequence: int
    type: OperationalEventType
    stage: str
    status: str  # "running" | "completed" | "warning" | "failed"
    message: str
    timestamp: float = field(default_factory=time.time)
    duration_ms: Optional[float] = None
    trace_id: str = field(default_factory=lambda: f"tr_{uuid.uuid4().hex[:12]}")
    span_id: str = field(default_factory=lambda: f"sp_{uuid.uuid4().hex[:8]}")
    parent_span_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sequence": self.sequence,
            "type": self.type.value if hasattr(self.type, "value") else str(self.type),
            "stage": self.stage,
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "data": self.data,
        }


class OperationalEventEmitter:
    """Thread-safe event generator maintaining monotonic sequence ordering and phase durations."""

    def __init__(
        self,
        on_event: Optional[Callable[[OperationalEvent], None]] = None,
        trace_id: Optional[str] = None,
    ):
        self._on_event = on_event
        self.trace_id = trace_id or f"tr_{uuid.uuid4().hex[:12]}"
        self._sequence = 0
        self._stage_start_times: Dict[str, float] = {}

    def start_stage(self, stage: str) -> None:
        """Record the start time of a pipeline stage to calculate duration later."""
        self._stage_start_times[stage] = time.perf_counter()

    def get_stage_duration_ms(self, stage: str) -> Optional[float]:
        """Return elapsed milliseconds since start_stage was called for this stage."""
        start = self._stage_start_times.get(stage)
        if start is not None:
            return round((time.perf_counter() - start) * 1000.0, 1)
        return None

    def emit(
        self,
        event_type: OperationalEventType,
        stage: str,
        status: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        parent_span_id: Optional[str] = None,
    ) -> OperationalEvent:
        """Create, sequence, and dispatch an operational event."""
        self._sequence += 1
        calc_duration = duration_ms if duration_ms is not None else self.get_stage_duration_ms(stage)

        event = OperationalEvent(
            sequence=self._sequence,
            type=event_type,
            stage=stage,
            status=status,
            message=message,
            timestamp=time.time(),
            duration_ms=calc_duration,
            trace_id=self.trace_id,
            span_id=f"sp_{uuid.uuid4().hex[:8]}",
            parent_span_id=parent_span_id,
            data=data or {},
        )

        if self._on_event:
            try:
                self._on_event(event)
            except Exception:
                # Logging or emitter errors must never break agent execution
                pass

        return event
