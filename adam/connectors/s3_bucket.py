"""Amazon S3 and S3-Compatible (MinIO, Ceph) Bucket Connector for bulk records.

Discovers documents in designated S3 buckets and path prefixes,
extracts object metadata and S3 tags, and fetches payloads for ingestion.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional, Tuple

from adam.connectors.base import BaseConnector, DiscoveredItem, FetchResult
from adam.db.models import Source
from adam.vocabularies import AuthorityLevel, Classification, DocType

logger = logging.getLogger(__name__)


class S3BucketConnector(BaseConnector):
    """Acquires files from Amazon S3 or S3-compatible object storage (MinIO/Ceph)."""

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        prefix: str = "",
        endpoint_url: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        region_name: str = "ap-south-1",
    ):
        self.bucket_name = bucket_name
        self.prefix = prefix.strip("/")
        self.endpoint_url = endpoint_url
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.region_name = region_name

    def _get_s3_client(self, source: Optional[Source] = None) -> Any:
        import boto3
        from botocore.config import Config

        cfg = source.config_json or {} if source else {}
        b_name = self.bucket_name or cfg.get("bucket_name")
        ep_url = self.endpoint_url or cfg.get("endpoint_url")
        key_id = self.aws_access_key_id or cfg.get("aws_access_key_id")
        secret = self.aws_secret_access_key or cfg.get("aws_secret_access_key")
        region = self.region_name or cfg.get("region_name", "ap-south-1")

        client_kwargs: Dict[str, Any] = {
            "region_name": region,
            "config": Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
        }
        if ep_url:
            client_kwargs["endpoint_url"] = ep_url
        if key_id and secret:
            client_kwargs["aws_access_key_id"] = key_id
            client_kwargs["aws_secret_access_key"] = secret

        return boto3.client("s3", **client_kwargs)

    @property
    def supports_deletion_detection(self) -> bool:
        return True

    def test_connection(self, source: Source) -> Tuple[bool, str]:
        """Verify S3 credentials and bucket accessibility."""
        try:
            cfg = source.config_json or {}
            bucket = self.bucket_name or cfg.get("bucket_name")
            if not bucket:
                return False, "S3 bucket_name is required in configuration."

            client = self._get_s3_client(source)
            client.head_bucket(Bucket=bucket)
            return True, f"Successfully connected to S3 bucket '{bucket}'."
        except Exception as exc:
            return False, f"S3 connection test failed: {exc}"

    def discover(self, source: Source) -> Iterator[DiscoveredItem]:
        """List objects under bucket and prefix matching document extensions."""
        cfg = source.config_json or {}
        bucket = self.bucket_name or cfg.get("bucket_name")
        prefix = (self.prefix or cfg.get("prefix", "")).strip("/")
        allowed_exts = {".pdf", ".docx", ".txt", ".json", ".csv", ".xlsx", ".tif", ".tiff"}

        client = self._get_s3_client(source)
        paginator = client.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue

                ext = ("." + key.rsplit(".", 1)[-1].lower()) if "." in key else ""
                if ext not in allowed_exts:
                    continue

                filename = key.rsplit("/", 1)[-1]
                title = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()
                source_url = f"s3://{bucket}/{key}"
                last_modified = obj.get("LastModified")

                yield DiscoveredItem(
                    source_url=source_url,
                    title=title,
                    doc_type=DocType.GO.value,
                    department_id=source.department_id,
                    displayed_date=last_modified.date() if last_modified else None,
                    authority_level=AuthorityLevel.DEPARTMENTAL_SECRETARY.value,
                    classification=source.access_classification or Classification.PUBLIC.value,
                    language="hi" if ("hindi" in key.lower() or "hin" in key.lower()) else "en",
                    metadata={
                        "bucket": bucket,
                        "s3_key": key,
                        "size_bytes": obj.get("Size", 0),
                        "etag": obj.get("ETag", "").strip('"'),
                        "last_modified": last_modified.isoformat() if last_modified else None,
                    },
                )

    def fetch(self, item: DiscoveredItem) -> FetchResult:
        """Download document bytes from S3."""
        meta = item.metadata or {}
        bucket = meta.get("bucket")
        key = meta.get("s3_key")
        now = datetime.now(timezone.utc)

        if not bucket or not key:
            if item.source_url.startswith("s3://"):
                parts = item.source_url[5:].split("/", 1)
                bucket = parts[0]
                key = parts[1] if len(parts) > 1 else ""

        client = self._get_s3_client()
        resp = client.get_object(Bucket=bucket, Key=key)
        data = resp["Body"].read()

        return FetchResult(
            source_url=item.source_url,
            data=data,
            http_status=200,
            http_headers={"content-type": resp.get("ContentType", "application/pdf")},
            retrieved_at=now,
        )
