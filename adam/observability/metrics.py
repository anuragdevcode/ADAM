"""Prometheus / OpenMetrics telemetry collector and formatter for ADAM.

Exposes standard operational metrics, request counters, latency distributions,
cache efficiency, and worker saturation in Prometheus text exposition format.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Dict, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from adam.agent.cache import GLOBAL_RESPONSE_CACHE
from adam.agent.coordinator import HeavyWorkerCoordinator
from adam.config import COLLECTOR_VERSION


class MetricsCollector:
    """Thread-safe Prometheus / OpenMetrics metric registry."""

    _instance: Optional[MetricsCollector] = None
    _lock = threading.Lock()

    def __new__(cls) -> MetricsCollector:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MetricsCollector, cls).__new__(cls)
                cls._instance._init_metrics()
            return cls._instance

    def _init_metrics(self) -> None:
        self._mutex = threading.Lock()
        self.requests_total: Dict[str, int] = {
            "completed": 0,
            "abstained": 0,
            "failed": 0,
        }
        self.stage_durations: Dict[str, float] = {}
        self.stage_counts: Dict[str, int] = {}

    def record_request(self, status: str) -> None:
        """Record a completed request with its outcome status."""
        with self._mutex:
            self.requests_total[status] = self.requests_total.get(status, 0) + 1

    def record_stage_latency(self, stage: str, duration_seconds: float) -> None:
        """Record stage execution duration."""
        with self._mutex:
            self.stage_durations[stage] = self.stage_durations.get(stage, 0.0) + duration_seconds
            self.stage_counts[stage] = self.stage_counts.get(stage, 0) + 1

    def generate_metrics_text(self, session: Optional[Session] = None) -> str:
        """Generate OpenMetrics / Prometheus standard text format output."""
        lines = []

        # 1. System Info
        lines.append("# HELP adam_info ADAM system build and environment metadata")
        lines.append("# TYPE adam_info gauge")
        profile = os.getenv("ADAM_PROFILE", "DEV_SERVER")
        lines.append(f'adam_info{{version="{COLLECTOR_VERSION}",profile="{profile}"}} 1')

        # 2. Total Requests by Status
        lines.append("# HELP adam_chat_requests_total Total number of chat inference requests by status")
        lines.append("# TYPE adam_chat_requests_total counter")
        with self._mutex:
            for status, count in sorted(self.requests_total.items()):
                lines.append(f'adam_chat_requests_total{{status="{status}"}} {count}')

        # 3. Stage Latency Averages
        lines.append("# HELP adam_stage_latency_seconds_total Total duration spent in pipeline stages")
        lines.append("# TYPE adam_stage_latency_seconds_total counter")
        lines.append("# HELP adam_stage_latency_count Total executions per pipeline stage")
        lines.append("# TYPE adam_stage_latency_count counter")
        with self._mutex:
            for stage in sorted(self.stage_durations.keys()):
                dur = self.stage_durations[stage]
                cnt = self.stage_counts[stage]
                lines.append(f'adam_stage_latency_seconds_total{{stage="{stage}"}} {dur:.4f}')
                lines.append(f'adam_stage_latency_count{{stage="{stage}"}} {cnt}')

        # 4. Response Cache Metrics
        lines.append("# HELP adam_cache_entries_current Number of entries currently cached in governed response cache")
        lines.append("# TYPE adam_cache_entries_current gauge")
        try:
            cache_size = len(GLOBAL_RESPONSE_CACHE._cache)
        except Exception:
            cache_size = 0
        lines.append(f"adam_cache_entries_current {cache_size}")

        # 5. Heavy Worker Saturation
        lines.append("# HELP adam_heavy_workers_active Active heavy workers executing GPU/CPU-bound tasks")
        lines.append("# TYPE adam_heavy_workers_active gauge")
        try:
            active_workers = len(HeavyWorkerCoordinator()._active_tasks)
        except Exception:
            active_workers = 0
        lines.append(f"adam_heavy_workers_active {active_workers}")

        # 6. Database Counts (if session provided)
        if session:
            try:
                from adam.db.models import Document, DocumentChunk, Source
                doc_count = session.query(func.count(Document.id)).scalar() or 0
                chunk_count = session.query(func.count(DocumentChunk.id)).scalar() or 0
                source_count = session.query(func.count(Source.id)).scalar() or 0

                lines.append("# HELP adam_documents_total Total approved documents in repository")
                lines.append("# TYPE adam_documents_total gauge")
                lines.append(f"adam_documents_total {doc_count}")

                lines.append("# HELP adam_chunks_total Total semantic chunks indexed in repository")
                lines.append("# TYPE adam_chunks_total gauge")
                lines.append(f"adam_chunks_total {chunk_count}")

                lines.append("# HELP adam_sources_total Total registered public record sources")
                lines.append("# TYPE adam_sources_total gauge")
                lines.append(f"adam_sources_total {source_count}")
            except Exception:
                pass

        lines.append("")
        return "\n".join(lines)


GLOBAL_METRICS = MetricsCollector()
