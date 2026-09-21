"""Transactional and retry-safe ingestion worker ensuring zero partial index publication on failure."""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from adam.db.models import (
    Source,
    Document,
    DocumentVersion,
    DocumentPage,
    TextBlock,
    DocumentChunk,
    IngestionJob,
    AuditEvent,
)
from adam.extract.pipeline import DocumentExtractionPipeline
from adam.ingest.validator import ContentValidator
from adam.rag.chunker import chunk_document_version
from adam.storage.base import get_storage_backend
from adam.vocabularies import Classification, LifecycleStatus


class TransactionalIngestionRunner:
    """Executes document ingestion with strict transactional isolation and atomic rollback."""

    def __init__(self, db: Session):
        self.db = db
        self.storage = get_storage_backend()

    def run_ingestion(
        self,
        source_id: str,
        user_id: str,
        trace_id: str,
        files: Optional[List[Tuple[str, bytes]]] = None,
        idempotency_key: Optional[str] = None,
    ) -> IngestionJob:
        """Execute ingestion job. On any failure, rolls back transaction so no partial index data is published."""
        source = self.db.query(Source).filter(Source.id == source_id).first()
        if not source:
            raise ValueError(f"Source with id '{source_id}' not found.")

        # Create tracking job
        job = IngestionJob(
            source_id=source_id,
            status="PROCESSING",
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            collector_version="v1.0.0",
            count_found=len(files) if files else 0,
            count_ingested=0,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        if not files:
            # Empty submission
            job.status = "COMPLETED"
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            return job

        ingested_count = 0

        # Process each file within its own transactional boundary
        for filename, file_bytes in files:
            try:
                # 1. Content validation (magic bytes & security checks)
                val_res = ContentValidator.validate(file_bytes, "application/pdf")
                if not val_res.is_safe:
                    raise ValueError(f"Content validation failed: {'; '.join(val_res.issues)}")

                # 2. Storage write
                sha256 = hashlib.sha256(file_bytes).hexdigest()
                storage_key = f"originals/{source_id}/{sha256}.pdf"
                self.storage.store(storage_key, file_bytes)

                # 3. Create Document and DocumentVersion
                doc_title = filename.rsplit(".", 1)[0].replace("_", " ").title()
                doc = Document(
                    source_id=source.id,
                    department_id=source.department_id,
                    title=doc_title,
                    classification=source.access_classification or Classification.PUBLIC.value,
                    doc_type="GOVERNMENT_ORDER",
                    lifecycle_status=LifecycleStatus.ACTIVE.value,
                )
                self.db.add(doc)
                self.db.flush()

                version = DocumentVersion(
                    document_id=doc.id,
                    original_object_key=storage_key,
                    source_url=f"local://{source_id}/{filename}",
                    sha256=sha256,
                    byte_size=len(file_bytes),
                    mime_type="application/pdf",
                )
                self.db.add(version)
                self.db.flush()

                # Record IngestionJobItem for unified control plane observability
                job_item = IngestionJobItem(
                    job_id=job.id,
                    item_key=f"local://{source_id}/{filename}",
                    title=doc_title,
                    status="SUCCESS",
                    sha256=sha256,
                    document_id=doc.id,
                    version_id=version.id,
                )
                self.db.add(job_item)

                # 4. Extract pages, text blocks, quality status
                pipeline = DocumentExtractionPipeline(self.db, self.storage)
                pipeline.process_version(version.id)

                # 5. Semantic structure chunking
                chunk_document_version(self.db, version.id)

                # 6. Audit event
                audit = AuditEvent(
                    entity_type="INGESTION_JOB",
                    entity_id=job.id,
                    action="DOCUMENT_INDEXED",
                    actor=user_id,
                    details_json={"document_id": doc.id, "version_id": version.id, "sha256": sha256},
                )
                self.db.add(audit)

                # Commit only when entire document lifecycle succeeded
                self.db.commit()
                ingested_count += 1

            except Exception as exc:
                # Strict atomic rollback: partial index entries and chunks are wiped
                self.db.rollback()

                # Mark job as failed and persist error
                failed_job = self.db.query(IngestionJob).filter(IngestionJob.id == job.id).first()
                if failed_job:
                    failed_job.status = "FAILED"
                    failed_job.current_stage = "FAILED"
                    failed_job.count_failed = (failed_job.count_failed or 0) + 1
                    failed_job.error_message = f"File '{filename}' failed: {str(exc)}"
                    failed_job.completed_at = datetime.now(timezone.utc)
                    self.db.commit()

                raise RuntimeError(f"Ingestion failed atomically: {exc}") from exc

        # Mark job completed successfully
        job.status = "COMPLETED"
        job.current_stage = "COMPLETED"
        job.count_ingested = ingested_count
        job.progress_pct = 100.0
        job.completed_at = datetime.now(timezone.utc)
        source.last_run_at = job.completed_at
        source.last_run_status = "COMPLETED"
        self.db.commit()
        return job
