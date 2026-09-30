"""Abstract base class and models for immutable object storage."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


class StorageError(Exception):
    """Base exception for storage errors."""
    pass


class ChecksumMismatchError(StorageError):
    """Raised when provided SHA-256 does not match computed SHA-256."""
    pass


class ImmutableObjectOverwriteError(StorageError):
    """Raised when an attempt is made to overwrite an immutable object with different bytes."""
    pass


@dataclass(frozen=True)
class StorageObject:
    """Metadata for an immutable stored object."""
    key: str
    sha256: str
    byte_size: int
    created_at: datetime


class StorageBackend(ABC):
    """Abstract interface for immutable blob / object storage."""

    @abstractmethod
    def store(
        self,
        key: str,
        data: bytes,
        expected_sha256: Optional[str] = None
    ) -> StorageObject:
        """Store immutable bytes under the given key.

        If the key already exists with identical bytes, the operation is an idempotent no-op.
        If the key exists with different bytes, ImmutableObjectOverwriteError is raised.
        """
        pass

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Retrieve bytes stored under key."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if an object exists at key."""
        pass

    @abstractmethod
    def get_metadata(self, key: str) -> Optional[StorageObject]:
        """Get metadata for object at key."""
        pass

    @abstractmethod
    def verify_integrity(self, key: str, expected_sha256: str) -> bool:
        """Verify that stored bytes match the expected SHA-256 hash."""
        pass


def get_storage_backend(base_dir: Optional[str] = None) -> StorageBackend:
    """Factory providing configured local or S3-compatible storage backend (R6)."""
    import os
    backend_type = os.environ.get("STORAGE_BACKEND", "local").lower()
    if backend_type in ("s3", "minio"):
        from adam.storage.s3 import S3StorageBackend
        bucket = os.environ.get("S3_BUCKET_NAME", "adam-storage")
        endpoint = os.environ.get("S3_ENDPOINT_URL")
        access_key = os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("MINIO_ROOT_USER")
        secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("MINIO_ROOT_PASSWORD")
        region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        prefix = os.environ.get("S3_PREFIX", "")
        return S3StorageBackend(
            bucket_name=bucket,
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            prefix=prefix,
        )

    from adam.storage.local import LocalStorageBackend
    from adam.config import STORAGE_DIR
    return LocalStorageBackend(base_dir or STORAGE_DIR)
