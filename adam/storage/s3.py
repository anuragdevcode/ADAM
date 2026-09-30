"""S3 and MinIO compatible implementation of immutable object storage."""

import hashlib
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from adam.storage.base import (
    StorageBackend,
    StorageObject,
    StorageError,
    ChecksumMismatchError,
    ImmutableObjectOverwriteError,
)

logger = logging.getLogger(__name__)


class S3StorageBackend(StorageBackend):
    """Immutable AWS S3 and MinIO object storage backend.

    Guarantees byte immutability, cryptographic checksum verification,
    and metadata persistence via S3 object metadata headers.
    """

    def __init__(
        self,
        bucket_name: str,
        endpoint_url: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        region_name: str = "us-east-1",
        prefix: str = "",
        s3_client: Optional[object] = None,
    ):
        self.bucket_name = bucket_name
        self.endpoint_url = endpoint_url
        self.prefix = prefix.strip("/")
        if s3_client is not None:
            self._client = s3_client
        else:
            try:
                import boto3
                from botocore.config import Config

                boto_config = Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"} if endpoint_url else {},
                    retries={"max_attempts": 3, "mode": "standard"},
                )
                self._client = boto3.client(
                    "s3",
                    endpoint_url=endpoint_url,
                    aws_access_key_id=aws_access_key_id,
                    aws_secret_access_key=aws_secret_access_key,
                    region_name=region_name,
                    config=boto_config,
                )
            except ImportError:
                raise StorageError("boto3 is required for S3StorageBackend. Install with: pip install boto3")

    def _full_key(self, key: str) -> str:
        clean = key.lstrip("/\\")
        if self.prefix:
            return f"{self.prefix}/{clean}"
        return clean

    def store(
        self,
        key: str,
        data: bytes,
        expected_sha256: Optional[str] = None,
    ) -> StorageObject:
        computed_sha256 = hashlib.sha256(data).hexdigest()

        if expected_sha256 and expected_sha256.lower() != computed_sha256.lower():
            raise ChecksumMismatchError(
                f"Checksum mismatch for key {key}: expected {expected_sha256}, got {computed_sha256}"
            )

        full_key = self._full_key(key)

        # Check for existing object to enforce immutability
        try:
            head = self._client.head_object(Bucket=self.bucket_name, Key=full_key)
            existing_sha256 = head.get("Metadata", {}).get("sha256")
            if not existing_sha256:
                # If custom metadata missing, download and verify
                existing_bytes = self.get(key)
                existing_sha256 = hashlib.sha256(existing_bytes).hexdigest()

            if existing_sha256.lower() == computed_sha256.lower():
                created_at = head.get("LastModified", datetime.now(timezone.utc))
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                return StorageObject(
                    key=key,
                    sha256=existing_sha256,
                    byte_size=len(data),
                    created_at=created_at,
                )
            else:
                raise ImmutableObjectOverwriteError(
                    f"Cannot overwrite existing S3 object at {key} with different content! "
                    f"Existing hash: {existing_sha256}, New hash: {computed_sha256}"
                )
        except ImmutableObjectOverwriteError:
            raise
        except Exception:
            # Object does not exist, proceed to put
            pass

        now = datetime.now(timezone.utc)
        metadata = {
            "sha256": computed_sha256,
            "byte_size": str(len(data)),
            "created_at": now.isoformat(),
        }

        try:
            self._client.put_object(
                Bucket=self.bucket_name,
                Key=full_key,
                Body=data,
                Metadata=metadata,
                ContentType="application/octet-stream",
            )
        except Exception as e:
            raise StorageError(f"Failed to store object to S3: {e}") from e

        return StorageObject(
            key=key,
            sha256=computed_sha256,
            byte_size=len(data),
            created_at=now,
        )

    def get(self, key: str) -> bytes:
        full_key = self._full_key(key)
        try:
            response = self._client.get_object(Bucket=self.bucket_name, Key=full_key)
            return response["Body"].read()
        except Exception as e:
            err_code = getattr(getattr(e, "response", None), "get", lambda k: {})("Error", {}).get("Code", "")
            if "NoSuchKey" in str(e) or "404" in str(e) or err_code == "NoSuchKey":
                raise FileNotFoundError(f"Object not found in S3 bucket {self.bucket_name}: {key}") from e
            raise StorageError(f"Failed to retrieve object from S3: {e}") from e

    def exists(self, key: str) -> bool:
        full_key = self._full_key(key)
        try:
            self._client.head_object(Bucket=self.bucket_name, Key=full_key)
            return True
        except Exception:
            return False

    def get_metadata(self, key: str) -> Optional[StorageObject]:
        full_key = self._full_key(key)
        try:
            head = self._client.head_object(Bucket=self.bucket_name, Key=full_key)
            meta = head.get("Metadata", {})
            sha256 = meta.get("sha256")
            byte_size = int(meta.get("byte_size", head.get("ContentLength", 0)))
            created_at = head.get("LastModified", datetime.now(timezone.utc))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if not sha256:
                content = self.get(key)
                sha256 = hashlib.sha256(content).hexdigest()
            return StorageObject(
                key=key,
                sha256=sha256,
                byte_size=byte_size,
                created_at=created_at,
            )
        except Exception:
            return None

    def verify_integrity(self, key: str, expected_sha256: str) -> bool:
        try:
            meta = self.get_metadata(key)
            if meta and meta.sha256.lower() == expected_sha256.lower():
                return True
            content = self.get(key)
            return hashlib.sha256(content).hexdigest().lower() == expected_sha256.lower()
        except Exception:
            return False
