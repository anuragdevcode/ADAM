"""ADAM Backup and Disaster Recovery Engine.

Per Phase 09 specification (09-testing-integration.md):
- 'Backup restore recreates originals, metadata and index aliases; audit trail remains usable.'
"""

import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from adam.config import BASE_DIR, DATABASE_URL, STORAGE_DIR


class BackupVerificationError(RuntimeError):
    """Raised when backup manifest checksum or database validation fails."""
    pass


class DisasterRecoveryError(RuntimeError):
    """Raised when disaster recovery restore cannot recreate the environment."""
    pass


def _sha256_file(filepath: Path) -> str:
    """Compute SHA256 digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _get_sqlite_path(db_url: str) -> Optional[Path]:
    """Extract filesystem path from SQLite connection URL."""
    if not db_url.startswith("sqlite:"):
        return None
    cleaned = db_url.replace("sqlite:////", "/").replace("sqlite:///", "")
    return Path(cleaned).resolve()


def _get_table_counts(engine) -> Dict[str, int]:
    """Query record counts across key metadata and audit trail tables."""
    counts = {}
    tables = [
        "sources",
        "documents",
        "document_versions",
        "document_chunks",
        "audit_events",
        "agent_execution_audits",
        "answer_reconstruction_audits",
        "feedback_records",
    ]
    with engine.connect() as conn:
        for tbl in tables:
            try:
                res = conn.execute(text(f"SELECT count(*) FROM {tbl}"))
                counts[tbl] = res.scalar() or 0
            except Exception:
                counts[tbl] = 0
    return counts


def create_backup(
    backup_path: Optional[Path] = None,
    storage_dir: Optional[Path] = None,
    db_url: Optional[str] = None,
) -> Path:
    """Create a crash-consistent, cryptographically verified backup archive.

    Backs up:
    1. Database snapshot via SQLite online backup API (no table locking).
    2. Storage directory containing originals, page renders, and index caches.
    3. Manifest with SHA256 file checksums and table record counts.

    Returns the absolute path to the generated .tar.gz archive.
    """
    db_url = db_url or DATABASE_URL
    storage_dir = (storage_dir or STORAGE_DIR).resolve()
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if backup_path is None:
        backups_dir = storage_dir / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backups_dir / f"adam_backup_{timestamp}.tar.gz"
    else:
        backup_path = Path(backup_path).resolve()
        backup_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as staging_dir_str:
        staging_dir = Path(staging_dir_str)
        staged_data = staging_dir / "data"
        staged_data.mkdir(parents=True, exist_ok=True)

        # ── 1. Database Online Backup ─────────────────────────────────────
        sqlite_file = _get_sqlite_path(db_url)
        db_type = "sqlite" if sqlite_file else "other"
        staged_db = staged_data / "adam.db"

        if sqlite_file and sqlite_file.exists():
            # Use SQLite online backup API for crash consistency
            src_conn = sqlite3.connect(str(sqlite_file))
            try:
                src_conn.execute("REINDEX")
            except Exception:
                pass
            dest_conn = sqlite3.connect(str(staged_db))
            with dest_conn:
                src_conn.backup(dest_conn)
            dest_conn.close()
            src_conn.close()
        elif sqlite_file:
            # Create an empty db file if none exists yet
            conn = sqlite3.connect(str(staged_db))
            conn.close()

        # Query metadata and audit counts from staged database
        staged_engine = create_engine(f"sqlite:///{staged_db}")
        table_counts = _get_table_counts(staged_engine)
        staged_engine.dispose()

        # ── 2. Storage Directory Backup ───────────────────────────────────
        staged_storage = staged_data / "storage"
        staged_storage.mkdir(parents=True, exist_ok=True)

        if storage_dir.exists():
            for root, dirs, files in os.walk(storage_dir):
                # Avoid recursing into backups/ or temp directories
                dirs[:] = [d for d in dirs if d not in ("backups", "__pycache__", ".tmp")]
                rel_root = Path(root).relative_to(storage_dir)
                dest_dir = staged_storage / rel_root
                dest_dir.mkdir(parents=True, exist_ok=True)
                for f in files:
                    if f.endswith(".tmp"):
                        continue
                    src_f = Path(root) / f
                    shutil.copy2(src_f, dest_dir / f)

        # ── 3. Compute Checksums & Write Manifest ────────────────────────
        file_checksums: Dict[str, str] = {}
        total_bytes = 0
        total_files = 0

        for root, _, files in os.walk(staged_data):
            for f in files:
                file_p = Path(root) / f
                rel_p = str(file_p.relative_to(staging_dir))
                chk = _sha256_file(file_p)
                file_checksums[rel_p] = chk
                total_bytes += file_p.stat().st_size
                total_files += 1

        manifest = {
            "adam_backup_version": "1.0.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database_type": db_type,
            "total_files": total_files,
            "total_bytes": total_bytes,
            "table_counts": table_counts,
            "file_checksums": file_checksums,
        }

        manifest_path = staging_dir / "backup_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # ── 4. Package Archive ───────────────────────────────────────────
        with tarfile.open(backup_path, "w:gz") as tar:
            tar.add(manifest_path, arcname="backup_manifest.json")
            tar.add(staged_data, arcname="data")

    return backup_path


def _safe_extractall(tar: tarfile.TarFile, target_dir: Path) -> None:
    """Extract tar archive safely with Python 3.12+ filter='data' when available."""
    if hasattr(tarfile, "data_filter"):
        tar.extractall(target_dir, filter="data")
    else:
        tar.extractall(target_dir)


def verify_backup(archive_path: Path) -> Dict[str, Any]:
    """Verify archive integrity, manifest checksums, and database header."""
    archive_path = Path(archive_path).resolve()
    if not archive_path.exists():
        raise BackupVerificationError(f"Backup archive not found: {archive_path}")

    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                _safe_extractall(tar, temp_dir)
        except Exception as e:
            raise BackupVerificationError(f"Failed to unpack tar archive: {e}")

        manifest_file = temp_dir / "backup_manifest.json"
        if not manifest_file.exists():
            raise BackupVerificationError("Missing backup_manifest.json in archive")

        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        checksums = manifest.get("file_checksums", {})
        verified_count = 0
        for rel_p, expected_chk in checksums.items():
            full_p = temp_dir / rel_p
            if not full_p.exists():
                raise BackupVerificationError(f"Missing file declared in manifest: {rel_p}")
            actual_chk = _sha256_file(full_p)
            if actual_chk != expected_chk:
                raise BackupVerificationError(
                    f"Checksum mismatch for {rel_p}: expected {expected_chk}, got {actual_chk}"
                )
            verified_count += 1

        # Check SQLite DB header if present
        staged_db = temp_dir / "data" / "adam.db"
        if staged_db.exists():
            with open(staged_db, "rb") as f:
                header = f.read(16)
                if not header.startswith(b"SQLite format 3\x00"):
                    raise BackupVerificationError("Invalid SQLite header in backed-up database")

        return {
            "valid": True,
            "manifest": manifest,
            "verified_files": verified_count,
            "table_counts": manifest.get("table_counts", {}),
        }


def restore_backup(
    archive_path: Path,
    target_storage_dir: Optional[Path] = None,
    target_db_url: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Restore database, storage originals, and index aliases from backup archive.

    Verifies the audit trail remains usable and uncorrupted post-restore.
    """
    archive_path = Path(archive_path).resolve()
    target_storage_dir = (target_storage_dir or STORAGE_DIR).resolve()
    target_db_url = target_db_url or DATABASE_URL

    # Step 1: Cryptographic Verification
    verification = verify_backup(archive_path)
    manifest = verification["manifest"]

    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        with tarfile.open(archive_path, "r:gz") as tar:
            _safe_extractall(tar, temp_dir)

        # Step 2: Restore Database
        sqlite_file = _get_sqlite_path(target_db_url)
        staged_db = temp_dir / "data" / "adam.db"
        if sqlite_file and staged_db.exists():
            sqlite_file.parent.mkdir(parents=True, exist_ok=True)
            if sqlite_file.exists() and not force:
                # Use SQLite online backup API to overwrite safely
                dest_conn = sqlite3.connect(str(sqlite_file))
                src_conn = sqlite3.connect(str(staged_db))
                with dest_conn:
                    src_conn.backup(dest_conn)
                src_conn.close()
                dest_conn.close()
            else:
                shutil.copy2(staged_db, sqlite_file)

        # Step 3: Restore Storage Directory
        staged_storage = temp_dir / "data" / "storage"
        files_restored = 0
        if staged_storage.exists():
            target_storage_dir.mkdir(parents=True, exist_ok=True)
            for root, _, files in os.walk(staged_storage):
                rel_root = Path(root).relative_to(staged_storage)
                dest_dir = target_storage_dir / rel_root
                dest_dir.mkdir(parents=True, exist_ok=True)
                for f in files:
                    src_f = Path(root) / f
                    dest_f = dest_dir / f
                    shutil.copy2(src_f, dest_f)
                    files_restored += 1

        # Step 4: Verify Post-Restore Audit Trail Usability
        engine = create_engine(target_db_url)
        with engine.connect() as conn:
            if conn.dialect.name == "sqlite":
                try:
                    conn.execute(text("REINDEX"))
                except Exception:
                    pass
                integrity = conn.execute(text("PRAGMA integrity_check")).scalar()
                if integrity != "ok":
                    raise DisasterRecoveryError(f"Database PRAGMA integrity_check failed: {integrity}")
            else:
                conn.execute(text("SELECT 1"))

        current_counts = _get_table_counts(engine)
        expected_counts = manifest.get("table_counts", {})

        # Confirm audit trail remains queryable
        with engine.connect() as conn:
            audit_events_count = conn.execute(text("SELECT count(*) FROM audit_events")).scalar()
            rec_audits_count = conn.execute(
                text("SELECT count(*) FROM answer_reconstruction_audits")
            ).scalar()

        engine.dispose()

        return {
            "status": "SUCCESS",
            "restored_at": datetime.now(timezone.utc).isoformat(),
            "verified_files": verification["verified_files"],
            "storage_files_restored": files_restored,
            "table_counts": current_counts,
            "expected_counts": expected_counts,
            "audit_trail_verified": True,
            "audit_events_count": audit_events_count,
            "reconstruction_audits_count": rec_audits_count,
        }
