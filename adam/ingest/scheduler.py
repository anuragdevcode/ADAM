"""Embedded, thread-safe recurring ingestion scheduler for ADAM.

Allows scheduling periodic synchronization and crawling of authoritative government
data sources (e.g. daily eGazette crawl, hourly eKosh sync) with interval and
cron-expression support, database state tracking, and mutual exclusion safety.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class ScheduledTask:
    """Definition and execution state of a recurring scheduled task."""
    task_id: str
    source_id: str
    schedule_type: str  # 'interval' or 'cron'
    interval_seconds: Optional[int] = None
    cron_expression: Optional[str] = None
    is_enabled: bool = True
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    last_status: Optional[str] = None
    error_count: int = 0

    def compute_next_run(self, from_time: Optional[datetime] = None) -> datetime:
        """Calculate the next execution timestamp based on schedule type."""
        now = from_time or datetime.now(timezone.utc)
        if self.schedule_type == "interval" and self.interval_seconds:
            return now + timedelta(seconds=self.interval_seconds)
        elif self.schedule_type == "cron" and self.cron_expression:
            return self._parse_next_cron(now, self.cron_expression)
        return now + timedelta(hours=24)

    @staticmethod
    def _parse_next_cron(now: datetime, expr: str) -> datetime:
        """Simple standard 5-part cron parser (minute, hour, day, month, weekday)."""
        parts = expr.strip().split()
        if len(parts) != 5:
            # Default to next hour if expression is non-standard
            return now + timedelta(hours=1)

        target = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        # Search forward up to 7 days
        for _ in range(7 * 24 * 60):
            m, h, dom, mon, dow = parts
            match_m = m == "*" or str(target.minute) == m
            match_h = h == "*" or str(target.hour) == h
            match_dom = dom == "*" or str(target.day) == dom
            match_mon = mon == "*" or str(target.month) == mon
            match_dow = dow == "*" or str(target.weekday()) == dow

            if match_m and match_h and match_dom and match_mon and match_dow:
                return target
            target += timedelta(minutes=1)

        return now + timedelta(hours=24)


class IngestionScheduler:
    """Thread-safe embedded scheduler managing recurring ingestion and sync tasks."""

    _instance: Optional[IngestionScheduler] = None
    _lock = threading.Lock()

    def __new__(cls) -> IngestionScheduler:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(IngestionScheduler, cls).__new__(cls)
                cls._instance._init_scheduler()
            return cls._instance

    def _init_scheduler(self) -> None:
        self._tasks: Dict[str, ScheduledTask] = {}
        self._mutex = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._is_running = False

    def schedule_interval(
        self,
        source_id: str,
        interval_seconds: int,
        task_id: Optional[str] = None,
    ) -> ScheduledTask:
        """Schedule a data source for periodic ingestion every N seconds."""
        t_id = task_id or f"sched_{source_id}_{interval_seconds}s"
        with self._mutex:
            task = ScheduledTask(
                task_id=t_id,
                source_id=source_id,
                schedule_type="interval",
                interval_seconds=interval_seconds,
                is_enabled=True,
                last_run_at=None,
            )
            task.next_run_at = task.compute_next_run()
            self._tasks[t_id] = task
            return task

    def schedule_cron(
        self,
        source_id: str,
        cron_expression: str,
        task_id: Optional[str] = None,
    ) -> ScheduledTask:
        """Schedule a data source using a standard 5-part cron expression (e.g. '0 2 * * *')."""
        t_id = task_id or f"sched_{source_id}_cron"
        with self._mutex:
            task = ScheduledTask(
                task_id=t_id,
                source_id=source_id,
                schedule_type="cron",
                cron_expression=cron_expression,
                is_enabled=True,
                last_run_at=None,
            )
            task.next_run_at = task.compute_next_run()
            self._tasks[t_id] = task
            return task

    def cancel_task(self, task_id: str) -> bool:
        """Cancel and remove a scheduled task."""
        with self._mutex:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
            return False

    def list_tasks(self) -> List[Dict[str, Any]]:
        """List all scheduled tasks and their execution states."""
        with self._mutex:
            return [
                {
                    "task_id": t.task_id,
                    "source_id": t.source_id,
                    "schedule_type": t.schedule_type,
                    "interval_seconds": t.interval_seconds,
                    "cron_expression": t.cron_expression,
                    "is_enabled": t.is_enabled,
                    "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
                    "next_run_at": t.next_run_at.isoformat() if t.next_run_at else None,
                    "last_status": t.last_status,
                }
                for t in self._tasks.values()
            ]

    def start(self) -> None:
        """Start background scheduler loop."""
        with self._mutex:
            if self._is_running:
                return
            self._stop_event.clear()
            self._is_running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="ingest-scheduler")
            self._thread.start()
            logger.info("Ingestion scheduler started.")

    def stop(self) -> None:
        """Stop background scheduler loop cleanly."""
        with self._mutex:
            if not self._is_running:
                return
            self._stop_event.set()
            self._is_running = False
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=1.0)
            logger.info("Ingestion scheduler stopped.")

    def _run_loop(self) -> None:
        """Internal daemon loop checking task schedules and launching jobs."""
        while not self._stop_event.is_set():
            now = datetime.now(timezone.utc)
            tasks_to_run = []

            with self._mutex:
                for task in self._tasks.values():
                    if task.is_enabled and task.next_run_at and now >= task.next_run_at:
                        tasks_to_run.append(task)

            for task in tasks_to_run:
                self._trigger_task(task)

            self._stop_event.wait(timeout=1.0)

    def _trigger_task(self, task: ScheduledTask) -> None:
        """Execute scheduled ingestion job via IngestionControlPlane."""
        now = datetime.now(timezone.utc)
        task.last_run_at = now
        task.next_run_at = task.compute_next_run(now)

        try:
            from adam.ingest.control_plane import IngestionControlPlane
            cp = IngestionControlPlane()
            cp.start_job(
                source_id=task.source_id,
                job_type="DISCOVER_AND_INGEST",
                user_id="system_scheduler",
            )
            task.last_status = "SUCCESS"
            task.error_count = 0
            logger.info(f"Scheduler triggered ingestion for source '{task.source_id}'.")
        except Exception as e:
            task.last_status = "FAILED"
            task.error_count += 1
            logger.warning(f"Scheduler failed to trigger job for '{task.source_id}': {e}")


GLOBAL_SCHEDULER = IngestionScheduler()
