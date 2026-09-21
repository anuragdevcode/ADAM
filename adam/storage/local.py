"""Local filesystem implementation of immutable object storage."""

import hashlib
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from adam.storage.base import (
    StorageBackend,
    StorageObject,
    StorageError,
    ChecksumMismatchError,
    ImmutableObjectOverwriteError,
)


class LocalStorageBackend(StorageBackend):
    """Immutable local filesystem object storage backend.

    Stores objects by key or sha256. Guarantees byte immutability and atomic writes.
    """

    def __init__(self, root_dir: Path | str):
        self.root_dir = Path(root_dir)
        self.objects_dir = self.root_dir / "objects"
        self.tmp_dir = self.root_dir / "tmp"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, key: str) -> Path:
        clean_key = key.lstrip("/\\")
        # If key is sha256 or starts with hex hash, partition by first 2 chars
        if len(clean_key) >= 4 and all(c in "0123456789abcdefABCDEF-_" for c in clean_key[:4]):
            prefix = clean_key[:2]
            candidate = self.objects_dir / prefix / clean_key
        else:
            candidate = self.objects_dir / clean_key

        # Strict path traversal check: resolved path must be within objects_dir
        resolved = candidate.resolve()
        objects_root = self.objects_dir.resolve()
        if not resolved.is_relative_to(objects_root):
            raise StorageError(f"Access denied: path traversal attempt detected in key '{key}'")
        return candidate

    def store(
        self,
        key: str,
        data: bytes,
        expected_sha256: Optional[str] = None
    ) -> StorageObject:
        computed_sha256 = hashlib.sha256(data).hexdigest()

        if expected_sha256 and expected_sha256.lower() != computed_sha256.lower():
            raise ChecksumMismatchError(
                f"Checksum mismatch for key {key}: expected {expected_sha256}, got {computed_sha256}"
            )

        target_path = self._resolve_path(key)

        if target_path.exists():
            # Object already exists - check if content is identical
            existing_data = target_path.read_bytes()
            existing_sha256 = hashlib.sha256(existing_data).hexdigest()
            if existing_sha256 == computed_sha256:
                # Idempotent re-store: return existing metadata
                stat = target_path.stat()
                created_at = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)
                return StorageObject(
                    key=key,
                    sha256=existing_sha256,
                    byte_size=len(existing_data),
                    created_at=created_at,
                )
            else:
                # Byte mismatch: immutable objects must never be overwritten!
                raise ImmutableObjectOverwriteError(
                    f"Cannot overwrite existing object at {key} with different content! "
                    f"Existing hash: {existing_sha256}, New hash: {computed_sha256}"
                )

        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write via temporary file
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.tmp_dir, delete=False
            ) as tf:
                temp_file = Path(tf.name)
                tf.write(data)
                tf.flush()
                os.fsync(tf.fileno())

            # Atomically move to target path
            temp_file.replace(target_path)
            # Make file read-only to preserve immutability on disk
            try:
                os.chmod(target_path, 0o444)
            except OSError:
                pass
        except Exception as e:
            if temp_file and temp_file.exists():
                temp_file.unlink(missing_ok=True)
            raise StorageError(f"Failed to store object {key}: {e}") from e

        now = datetime.now(timezone.utc)
        return StorageObject(
            key=key,
            sha256=computed_sha256,
            byte_size=len(data),
            created_at=now,
        )

    def get(self, key: str) -> bytes:
        target_path = self._resolve_path(key)
        if not target_path.exists():
            raise FileNotFoundError(f"Storage object not found: {key}")
        return target_path.read_bytes()

    def retrieve(self, key: str) -> bytes:
        """Alias for get(key) to support alternate retrieval naming conventions."""
        return self.get(key)

    def exists(self, key: str) -> bool:
        return self._resolve_path(key).exists()

    def get_metadata(self, key: str) -> Optional[StorageObject]:
        target_path = self._resolve_path(key)
        if not target_path.exists():
            return None
        data = target_path.read_bytes()
        stat = target_path.stat()
        return StorageObject(
            key=key,
            sha256=hashlib.sha256(data).hexdigest(),
            byte_size=len(data),
            created_at=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
        )

    def verify_integrity(self, key: str, expected_sha256: str) -> bool:
        meta = self.get_metadata(key)
        if not meta:
            return False
        return meta.sha256.lower() == expected_sha256.lower()
