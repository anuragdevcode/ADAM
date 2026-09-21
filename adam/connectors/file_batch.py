"""File Batch and Local Directory Connector for bulk administrative records.

Supports batch directory scanning (harmonizing with ITDA sample batches) as well as
in-memory multi-file uploads.
"""

import hashlib
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Iterator, Optional, Dict, Any, List, Tuple

from adam.connectors.base import BaseConnector, DiscoveredItem, FetchResult
from adam.db.models import Source
from adam.vocabularies import DocType, AuthorityLevel, Classification


class FileBatchConnector(BaseConnector):
    """Acquires files from local directory paths or in-memory uploaded batches."""

    def __init__(
        self,
        batch_dir: Optional[Path | str] = None,
        in_memory_files: Optional[List[Tuple[str, bytes]]] = None,
    ):
        self.batch_dir = Path(batch_dir) if batch_dir else None
        self.in_memory_files = in_memory_files or []

    @property
    def supports_deletion_detection(self) -> bool:
        # Local batch directory scans are exhaustive
        return self.batch_dir is not None and self.batch_dir.exists()

    def test_connection(self, source: Source) -> Tuple[bool, str]:
        """Verify local directory existence or uploaded file payload."""
        cfg = source.config_json or {}
        batch_dir = self.batch_dir or (Path(cfg["batch_dir"]) if cfg.get("batch_dir") else None)

        if batch_dir:
            if not batch_dir.exists():
                return False, f"Directory '{batch_dir}' does not exist on filesystem."
            if not batch_dir.is_dir():
                return False, f"Path '{batch_dir}' is not a directory."
            return True, f"Directory '{batch_dir}' is accessible."

        if self.in_memory_files:
            return True, f"{len(self.in_memory_files)} uploaded files ready for processing."

        return True, "File batch connector configured."

    def discover(self, source: Source) -> Iterator[DiscoveredItem]:
        cfg = source.config_json or {}
        batch_dir = self.batch_dir or (Path(cfg["batch_dir"]) if cfg.get("batch_dir") else None)

        # 1. In-memory files
        if self.in_memory_files:
            if not hasattr(self, "_in_memory_map"):
                self._in_memory_map = {}
            for filename, file_bytes in self.in_memory_files:
                doc_title = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()
                source_url = f"local://{source.id}/{filename}"
                self._in_memory_map[source_url] = file_bytes
                yield DiscoveredItem(
                    source_url=source_url,
                    title=doc_title,
                    doc_type=DocType.GO.value,
                    department_id=source.department_id,
                    authority_level=AuthorityLevel.DEPARTMENTAL_SECRETARY.value,
                    classification=source.access_classification or Classification.PUBLIC.value,
                    metadata={"filename": filename, "is_in_memory": True},
                )
            return

        # 2. Local directory scan
        if batch_dir and batch_dir.exists():
            resolved_batch = batch_dir.resolve()
            if source.permitted_path_prefixes:
                allowed = any(
                    str(resolved_batch).startswith(str(Path(p).resolve())) or p == "/"
                    for p in source.permitted_path_prefixes
                )
                if not allowed:
                    raise ValueError(
                        f"Batch directory '{batch_dir}' is outside authorized path prefixes: {source.permitted_path_prefixes}"
                    )

            for path in sorted(batch_dir.glob("**/*")):
                if path.is_file() and not path.name.startswith("."):
                    ext = path.suffix.lower()
                    if ext in (".pdf", ".docx", ".doc", ".txt", ".csv", ".json"):
                        doc_title = path.stem.replace("_", " ").replace("-", " ").title()
                        source_url = f"file://{path.resolve()}"
                        yield DiscoveredItem(
                            source_url=source_url,
                            title=doc_title,
                            doc_type=DocType.GO.value,
                            department_id=source.department_id,
                            authority_level=AuthorityLevel.DEPARTMENTAL_SECRETARY.value,
                            classification=source.access_classification or Classification.PUBLIC.value,
                            metadata={"file_path": str(path.resolve()), "filename": path.name},
                        )

    def fetch(self, item: DiscoveredItem) -> FetchResult:
        # If in-memory bytes provided
        if hasattr(self, "_in_memory_map") and item.source_url in self._in_memory_map:
            data = self._in_memory_map[item.source_url]
            mime = "application/pdf" if data.startswith(b"%PDF-") else "application/octet-stream"
            return FetchResult(
                source_url=item.source_url,
                data=data,
                http_status=200,
                http_headers={"content-type": mime},
                retrieved_at=datetime.now(timezone.utc),
            )

        # If file path provided
        file_path_str = item.metadata.get("file_path")
        if file_path_str:
            p = Path(file_path_str)
            data = p.read_bytes()
            mime = "application/pdf" if data.startswith(b"%PDF-") else "application/octet-stream"
            return FetchResult(
                source_url=item.source_url,
                data=data,
                http_status=200,
                http_headers={"content-type": mime},
                retrieved_at=datetime.now(timezone.utc),
            )

        raise ValueError(f"No valid data payload or file path for item '{item.source_url}'")
