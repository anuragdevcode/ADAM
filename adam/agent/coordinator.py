"""Heavy worker concurrency coordinator and mutual exclusion locks.

Per Phase 04 specification:
- 'reserve >=2GB macOS headroom; do not run OCR/indexing while chatting; use one active heavy worker'
"""

import json
import os
import threading
import time
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, Generator

from adam.agent.budget import ResourceBudgetManager, MACBOOK_AIR_8GB_PROFILE
from adam.agent.filelock import try_lock_exclusive, unlock


class HeavyTaskType(str, Enum):
    """Heavy background or inference operations competing for unified memory."""
    CHAT_INFERENCE = "CHAT_INFERENCE"
    OCR_PROCESSING = "OCR_PROCESSING"
    INDEXING = "INDEXING"
    MODEL_LOAD = "MODEL_LOAD"


class ResourceContentionError(RuntimeError):
    """Raised when an active heavy worker prevents concurrent heavy operations."""
    pass


class HeavyWorkerCoordinator:
    """Coordinates heavy workers to enforce 'do not run OCR/indexing while chatting'.

    On memory-constrained profiles (like MacBook Air 8GB), ensures strict mutual exclusion
    between chat inference and background OCR/indexing tasks across both threads and OS processes.
    """

    _instance = None
    _class_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._class_lock:
            if cls._instance is None:
                cls._instance = super(HeavyWorkerCoordinator, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, budget_manager: Optional[ResourceBudgetManager] = None):
        if getattr(self, "_initialized", False):
            if budget_manager is not None:
                self.budget_manager = budget_manager
            return
        self.budget_manager = budget_manager or ResourceBudgetManager()
        self._active_tasks: Dict[str, HeavyTaskType] = {}
        self._task_started_times: Dict[str, float] = {}
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._lock_file_handle = None
        self._initialized = True

    @classmethod
    def reset(cls) -> None:
        """Reset singleton state and active locks for clean test isolation."""
        with cls._class_lock:
            if cls._instance is not None:
                with cls._instance._lock:
                    if cls._instance._lock_file_handle:
                        try:
                            unlock(cls._instance._lock_file_handle)
                            cls._instance._lock_file_handle.close()
                        except (OSError, ValueError):
                            pass
                        cls._instance._lock_file_handle = None
                    cls._instance._active_tasks.clear()
                    cls._instance._task_started_times.clear()
                cls._instance = None

    @property
    def is_busy(self) -> bool:
        with self._lock:
            return len(self._active_tasks) > 0

    @property
    def active_task(self) -> Optional[HeavyTaskType]:
        with self._lock:
            if not self._active_tasks:
                return None
            return next(iter(self._active_tasks.values()))

    def _get_lockfile_paths(self) -> tuple[Path, Path]:
        storage_dir = getattr(self.budget_manager, "storage_dir", Path(".adam_storage"))
        locks_dir = storage_dir / "locks"
        locks_dir.mkdir(parents=True, exist_ok=True)
        return locks_dir / "heavy_worker.lock", locks_dir / "heavy_worker.json"

    @contextmanager
    def acquire_worker(
        self,
        task_type: HeavyTaskType,
        task_id: str = "task",
        timeout_seconds: float = 0.0,
    ) -> Generator[None, None, None]:
        """Context manager to acquire heavy worker with thread and process-level mutual exclusion checking."""
        enforce_exclusive = self.budget_manager.profile.enforce_heavy_worker_mutual_exclusion
        max_active = self.budget_manager.profile.max_active_requests
        lock_file_path, state_file_path = self._get_lockfile_paths()
        fd = None

        # ── 1. In-process Thread Synchronization ─────────────────────────
        with self._lock:
            start_wait = time.time()
            while True:
                if enforce_exclusive and len(self._active_tasks) > 0:
                    current_task = next(iter(self._active_tasks.values()))
                    current_id = next(iter(self._active_tasks.keys()))
                    if timeout_seconds <= 0.0:
                        raise ResourceContentionError(
                            f"Cannot execute '{task_type.value}': heavy worker is currently occupied "
                            f"by '{current_task.value}' (task ID: {current_id}). "
                            "Phase 04 specification strictly prohibits running OCR/indexing while chatting "
                            "under the MacBook Air 8GB memory budget."
                        )
                    elapsed = time.time() - start_wait
                    if elapsed >= timeout_seconds:
                        raise ResourceContentionError(
                            f"Timed out waiting for heavy worker after {timeout_seconds}s. "
                            f"Worker occupied by '{current_task.value}'."
                        )
                    self._condition.wait(timeout=max(0.01, timeout_seconds - elapsed))
                elif not enforce_exclusive and len(self._active_tasks) >= max_active:
                    if timeout_seconds <= 0.0:
                        raise ResourceContentionError(
                            f"Server concurrency limit reached ({len(self._active_tasks)}/{max_active} active). "
                            f"Cannot execute '{task_type.value}' without exceeding budget."
                        )
                    elapsed = time.time() - start_wait
                    if elapsed >= timeout_seconds:
                        raise ResourceContentionError(
                            f"Timed out waiting for available server slot after {timeout_seconds}s."
                        )
                    self._condition.wait(timeout=max(0.01, timeout_seconds - elapsed))
                else:
                    break

            # ── 2. Cross-Process OS File Lock (for exclusive profile) ─────
            if enforce_exclusive:
                fd = open(lock_file_path, "a+")
                flock_start = time.time()
                while True:
                    try:
                        try_lock_exclusive(fd)
                        break
                    except (BlockingIOError, OSError):
                        if timeout_seconds <= 0.0:
                            fd.close()
                            raise ResourceContentionError(
                                f"Cannot execute '{task_type.value}': heavy worker is currently occupied "
                                "by another OS worker process. Phase 04 specification strictly prohibits "
                                "running OCR/indexing while chatting under the MacBook Air 8GB memory budget."
                            )
                        flock_elapsed = time.time() - flock_start
                        if flock_elapsed >= timeout_seconds:
                            fd.close()
                            raise ResourceContentionError(
                                f"Timed out waiting for process lock on heavy worker after {timeout_seconds}s."
                            )
                        time.sleep(0.05)

                try:
                    state_file_path.write_text(
                        json.dumps({
                            "pid": os.getpid(),
                            "task_type": task_type.value,
                            "task_id": task_id,
                            "started_at": time.time(),
                        }),
                        encoding="utf-8",
                    )
                except OSError:
                    pass

            # Register task in-process
            self._active_tasks[task_id] = task_type
            self._task_started_times[task_id] = time.time()

        try:
            yield
        finally:
            with self._lock:
                self._active_tasks.pop(task_id, None)
                self._task_started_times.pop(task_id, None)

                if enforce_exclusive and fd is not None:
                    try:
                        if state_file_path.exists():
                            state_file_path.unlink()
                    except OSError:
                        pass
                    try:
                        unlock(fd)
                        fd.close()
                    except OSError:
                        pass

                self._condition.notify_all()

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic status of heavy worker coordinator."""
        with self._lock:
            busy = len(self._active_tasks) > 0
            first_task = next(iter(self._active_tasks.values())) if busy else None
            first_id = next(iter(self._active_tasks.keys())) if busy else None
            first_time = next(iter(self._task_started_times.values())) if busy else None
            elapsed = round(time.time() - first_time, 2) if (busy and first_time) else 0.0
            return {
                "is_busy": busy,
                "active_tasks_count": len(self._active_tasks),
                "active_task": str(first_task.value) if first_task else None,
                "active_task_id": first_id,
                "elapsed_seconds": elapsed,
                "mutual_exclusion_enforced": self.budget_manager.profile.enforce_heavy_worker_mutual_exclusion,
            }
