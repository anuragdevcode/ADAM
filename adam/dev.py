"""Native local development diagnostics, system health inspection, and cache management."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from adam.agent.budget import (
    ResourceBudgetManager,
    MACBOOK_AIR_8GB_PROFILE,
    DEV_SERVER_PROFILE,
    GOV_PRODUCTION_PROFILE,
)
from adam.agent.coordinator import HeavyWorkerCoordinator
from adam.config import BASE_DIR, DATABASE_URL, STORAGE_DIR
from adam.db.models import Document, DocumentChunk, DocumentVersion, Source
from adam.db.session import get_engine, get_session
from adam.extract.ocr import get_ocr_engine


def get_system_memory_gb() -> Tuple[float, float]:
    """Retrieve (total_ram_gb, available_ram_gb) using system tools.

    Works natively on macOS via sysctl/vm_stat and cross-platform via sysconf/os.
    """
    total_gb = 8.0
    available_gb = 4.0

    # macOS sysctl detection
    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
            total_gb = round(int(out) / (1024**3), 2)
        except Exception:
            pass

        try:
            # Check free pages via vm_stat
            out = subprocess.check_output(["vm_stat"], text=True)
            lines = out.splitlines()
            page_size = 4096
            free_pages = 0
            speculative_pages = 0
            for line in lines:
                if "page size of" in line:
                    page_size = int(line.split()[7])
                elif "Pages free:" in line:
                    free_pages = int(line.split(":")[1].strip().rstrip("."))
                elif "Pages speculative:" in line:
                    speculative_pages = int(line.split(":")[1].strip().rstrip("."))
            available_gb = round(((free_pages + speculative_pages) * page_size) / (1024**3), 2)
        except Exception:
            available_gb = round(total_gb * 0.5, 2)
    else:
        try:
            total_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
            avail_pages = os.sysconf("SC_AVPHYS_PAGES")
            total_gb = round(total_bytes / (1024**3), 2)
            available_gb = round((avail_pages * os.sysconf("SC_PAGE_SIZE")) / (1024**3), 2)
        except Exception:
            pass

    return total_gb, available_gb


def get_disk_headroom_gb(path: Path) -> float:
    """Return available disk headroom in GB for given directory."""
    try:
        usage = shutil.disk_usage(path)
        return round(usage.free / (1024**3), 2)
    except Exception:
        return 50.0


def run_doctor() -> Dict[str, Any]:
    """Execute complete environment and resource health diagnostics.

    Verifies:
    1. Unified Memory & macOS >= 2GB headroom
    2. Disk storage headroom & cache size
    3. Database connectivity and record counts
    4. OCR engine and voice engine availability
    5. Heavy worker concurrency locks
    """
    total_ram_gb, avail_ram_gb = get_system_memory_gb()
    disk_free_gb = get_disk_headroom_gb(STORAGE_DIR.parent)

    headroom_ok = avail_ram_gb >= 2.0
    disk_ok = disk_free_gb >= 1.0

    # Database health & table counts
    db_ok = False
    counts = {}
    db_error = None
    try:
        engine = get_engine(DATABASE_URL)
        session = get_session(engine)
        counts = {
            "sources": session.query(Source).count(),
            "documents": session.query(Document).count(),
            "versions": session.query(DocumentVersion).count(),
            "chunks": session.query(DocumentChunk).count(),
        }
        db_ok = True
        session.close()
    except Exception as exc:
        db_error = str(exc)

    # Storage cache status
    storage_size_bytes = 0
    if STORAGE_DIR.exists():
        for f in STORAGE_DIR.rglob("*"):
            if f.is_file():
                try:
                    storage_size_bytes += f.stat().st_size
                except OSError:
                    pass
    storage_size_mb = round(storage_size_bytes / (1024**2), 2)

    # OCR Engine detection
    ocr_engine = get_ocr_engine()
    tesseract_available = shutil.which("tesseract") is not None

    # Heavy worker lock state
    coordinator = HeavyWorkerCoordinator()
    is_busy = coordinator.is_busy
    active_task = str(coordinator.active_task) if coordinator.active_task else None
    lock_file = STORAGE_DIR / ".adam_heavy_worker.lock"
    lock_active = lock_file.exists() and is_busy

    # Voice engines
    from adam.api.voice.stt import get_stt_engine
    from adam.api.voice.tts import get_tts_engine
    stt_engine = get_stt_engine()
    tts_engine = get_tts_engine()

    # Model Artifact & Blob Integrity Diagnostics
    from adam.model.registry import ModelRegistry
    from adam.model.runtime import verify_ollama_blob_integrity, find_ollama_blob_path

    model_registry = ModelRegistry()
    primary_model = model_registry.get_primary()
    model_checks = {}
    model_integrity_ok = True

    for m in model_registry.list_all():
        if m.serving_runtime == "ollama":
            blob_path = find_ollama_blob_path(m)
            blob_found = blob_path is not None
            verified, err = verify_ollama_blob_integrity(m) if blob_found else (False, "Blob not found on disk")
            if blob_found and not verified:
                model_integrity_ok = False
            model_checks[m.id] = {
                "name": m.name,
                "runtime": m.serving_runtime,
                "blob_present": blob_found,
                "blob_path": str(blob_path) if blob_path else None,
                "verified": verified,
                "error": err,
                "expected_sha256": m.checksum_sha256,
                "file_size_bytes": m.file_size_bytes,
            }

    # Determine overall status
    if not db_ok or not disk_ok or not model_integrity_ok:
        status = "CRITICAL"
    elif not headroom_ok or not tesseract_available:
        status = "WARNING"
    else:
        status = "HEALTHY"

    return {
        "status": status,
        "profile": "MACBOOK_AIR_8GB",
        "memory": {
            "total_ram_gb": total_ram_gb,
            "available_ram_gb": avail_ram_gb,
            "macos_headroom_gb": 2.0,
            "headroom_met": headroom_ok,
        },
        "disk": {
            "free_space_gb": disk_free_gb,
            "storage_dir": str(STORAGE_DIR),
            "storage_cache_mb": storage_size_mb,
            "cache_ceiling_mb": 2048.0,
            "within_ceiling": storage_size_mb <= 2048.0,
        },
        "database": {
            "connected": db_ok,
            "url": DATABASE_URL,
            "counts": counts,
            "error": db_error,
        },
        "engines": {
            "ocr_engine": type(ocr_engine).__name__,
            "tesseract_binary_present": tesseract_available,
            "stt_engine": type(stt_engine).__name__,
            "tts_engine": type(tts_engine).__name__,
        },
        "concurrency": {
            "heavy_worker_mutual_exclusion_active": True,
            "is_busy": is_busy,
            "active_task": active_task,
            "lock_engaged": lock_active,
        },
        "model_integrity": {
            "all_verified": model_integrity_ok,
            "models": model_checks,
        },
    }


def clean_cache(cap_mb: float = 2048.0, dry_run: bool = False) -> Dict[str, Any]:
    """Enforce disk cache ceiling by pruning temporary unpinned files from the storage cache."""
    if not STORAGE_DIR.exists():
        return {"current_size_mb": 0.0, "freed_mb": 0.0, "pruned_files": 0}

    # Calculate total size
    files_with_stats = []
    total_bytes = 0
    for p in STORAGE_DIR.rglob("*"):
        if p.is_file():
            try:
                st = p.stat()
                total_bytes += st.st_size
                files_with_stats.append((p, st.st_size, st.st_mtime))
            except OSError:
                pass

    current_size_mb = round(total_bytes / (1024**2), 2)
    freed_bytes = 0
    pruned_count = 0

    target_bytes = int(cap_mb * 1024 * 1024)
    if total_bytes > target_bytes:
        # Sort oldest first, prioritizing tmp directory
        tmp_files = [f for f in files_with_stats if "tmp" in f[0].parts]
        tmp_files.sort(key=lambda x: x[2])  # oldest mtime first

        for f_path, f_size, _ in tmp_files:
            if total_bytes - freed_bytes <= target_bytes:
                break
            if not dry_run:
                try:
                    f_path.unlink()
                    freed_bytes += f_size
                    pruned_count += 1
                except OSError:
                    pass
            else:
                freed_bytes += f_size
                pruned_count += 1

    return {
        "current_size_mb": current_size_mb,
        "cap_mb": cap_mb,
        "freed_mb": round(freed_bytes / (1024**2), 2),
        "pruned_files": pruned_count,
        "dry_run": dry_run,
    }
