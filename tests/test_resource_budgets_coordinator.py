"""Unit tests for Phase 04 Resource Budgets, Storage Cache Ceilings, and Heavy Worker Coordinator."""

import pytest
from pathlib import Path
from adam.agent.budget import (
    ResourceBudgetManager,
    MACBOOK_AIR_8GB_PROFILE,
    DEV_SERVER_PROFILE,
    GOV_PRODUCTION_PROFILE,
)
from adam.agent.coordinator import (
    HeavyWorkerCoordinator,
    HeavyTaskType,
    ResourceContentionError,
)
from adam.vocabularies import EnvironmentProfileType


def test_environment_profiles_specifications():
    """Verify hardware profile configurations against Phase 04 specification table."""
    # 1. 8GB MacBook Air profile
    mac = MACBOOK_AIR_8GB_PROFILE
    assert mac.profile_type == EnvironmentProfileType.MACBOOK_AIR_8GB
    assert mac.ram_total_gb == 8.0
    assert mac.macos_headroom_gb >= 2.0  # reserve >=2GB macOS headroom
    assert mac.usable_ram_gb == 6.0
    assert mac.max_active_requests == 1   # single request
    assert 2048 <= mac.max_context_window <= 4096  # 2k-4k context
    assert mac.enforce_heavy_worker_mutual_exclusion is True

    # 2. Team / Dev server profile
    dev = DEV_SERVER_PROFILE
    assert dev.profile_type == EnvironmentProfileType.DEV_SERVER
    assert 8.0 <= dev.ram_total_gb <= 16.0
    assert 10.0 <= dev.disk_cache_ceiling_gb <= 20.0  # 10-20GB model cache

    # 3. Government production profile
    prod = GOV_PRODUCTION_PROFILE
    assert prod.profile_type == EnvironmentProfileType.GOV_PRODUCTION
    assert 30.0 <= prod.disk_cache_ceiling_gb <= 40.0  # 30-40GB disk cache ceiling


def test_disk_cache_ceiling_and_headroom(tmp_path: Path):
    """Verify disk cache ceiling calculation and macOS headroom checks."""
    manager = ResourceBudgetManager(MACBOOK_AIR_8GB_PROFILE, storage_dir=tmp_path)

    # Empty cache is within ceiling
    is_ok, current_gb, ceiling_gb = manager.check_cache_ceiling()
    assert is_ok is True
    assert current_gb == 0.0
    assert ceiling_gb == 10.0

    headroom = manager.check_mac_headroom()
    assert headroom["headroom_satisfied"] is True
    assert headroom["headroom_reserved_gb"] >= 2.0


def test_heavy_worker_mutual_exclusion():
    """Enforce: 'do not run OCR/indexing while chatting; use one active heavy worker'."""
    coordinator = HeavyWorkerCoordinator(ResourceBudgetManager(MACBOOK_AIR_8GB_PROFILE))

    # 1. Simulate active chat inference session
    with coordinator.acquire_worker(HeavyTaskType.CHAT_INFERENCE, task_id="chat_session_01"):
        assert coordinator.is_busy is True
        assert coordinator.active_task == HeavyTaskType.CHAT_INFERENCE

        # 2. Attempting background OCR while chatting raises ResourceContentionError
        with pytest.raises(ResourceContentionError) as exc_info:
            with coordinator.acquire_worker(HeavyTaskType.OCR_PROCESSING, task_id="ocr_job_99", timeout_seconds=0.0):
                pass
        assert "OCR/indexing while chatting" in str(exc_info.value)
        assert "MacBook Air 8GB" in str(exc_info.value)

        # 3. Attempting background indexing while chatting raises ResourceContentionError
        with pytest.raises(ResourceContentionError):
            with coordinator.acquire_worker(HeavyTaskType.INDEXING, task_id="index_job_42", timeout_seconds=0.0):
                pass

    # 4. Once chat inference finishes, OCR can acquire worker freely
    assert coordinator.is_busy is False
    with coordinator.acquire_worker(HeavyTaskType.OCR_PROCESSING, task_id="ocr_job_99"):
        assert coordinator.active_task == HeavyTaskType.OCR_PROCESSING
    assert coordinator.is_busy is False


def test_heavy_worker_cross_process_locking(tmp_path: Path):
    """Verify that file locking enforces mutual exclusion across independent processes."""
    from adam.agent.filelock import try_lock_exclusive, unlock
    HeavyWorkerCoordinator.reset()
    budget_mgr = ResourceBudgetManager(MACBOOK_AIR_8GB_PROFILE, storage_dir=tmp_path)
    coordinator = HeavyWorkerCoordinator(budget_mgr)

    # 1. Acquire worker in current process
    with coordinator.acquire_worker(HeavyTaskType.CHAT_INFERENCE, task_id="proc_1_chat"):
        # 2. Simulate another OS process trying to lock the same lockfile
        lock_file, _ = coordinator._get_lockfile_paths()
        fd2 = open(lock_file, "a+")
        try:
            # Another process attempting non-blocking lock must get BlockingIOError
            with pytest.raises((BlockingIOError, OSError)):
                try_lock_exclusive(fd2)
        finally:
            fd2.close()

    # 3. After worker exits, external process can acquire lock freely
    fd3 = open(lock_file, "a+")
    try:
        try_lock_exclusive(fd3)
        unlock(fd3)
    finally:
        fd3.close()


def test_heavy_worker_server_multi_worker_tracking():
    """Verify that DEV_SERVER profile allows concurrent workers up to max_active_requests."""
    HeavyWorkerCoordinator.reset()
    budget_mgr = ResourceBudgetManager(DEV_SERVER_PROFILE)
    coordinator = HeavyWorkerCoordinator(budget_mgr)

    assert coordinator.budget_manager.profile.enforce_heavy_worker_mutual_exclusion is False
    max_active = coordinator.budget_manager.profile.max_active_requests

    # 1. Concurrently acquire 2 workers
    with coordinator.acquire_worker(HeavyTaskType.CHAT_INFERENCE, task_id="chat_req_1"):
        with coordinator.acquire_worker(HeavyTaskType.OCR_PROCESSING, task_id="ocr_req_2"):
            status = coordinator.get_status()
            assert status["is_busy"] is True
            assert status["active_tasks_count"] == 2

    assert coordinator.is_busy is False
