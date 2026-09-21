"""Unified Ingestion Control Plane orchestrating the full ingestion operating system.

Features:
- Decoupled Control Plane from worker execution.
- Bounded queues with producer backpressure (queue.Queue(maxsize=100)).
- Cooperative DRAINING and CANCELLING state machine.
- 4 distinct operations: Resume, Retry-Failed, Incremental Rerun, Full Rerun.
- Persistent DB state of truth (SSE as an ephemeral broadcast delivery pipe).
- Normalized IngestionJobItem records eliminating single-row checkpoint bloat.
- Safe deletion reconciliation (runs only on 100% complete unconstrained discovery).
- Artifact version stamping and throttled telemetry (300ms debounce).
"""

import asyncio
import hashlib
import json
import logging
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple, Set, AsyncIterator

from sqlalchemy.orm import Session

from adam.config import COLLECTOR_VERSION
from adam.connectors.base import BaseConnector, DiscoveredItem, FetchResult
from adam.connectors.registry import ConnectorRegistry
from adam.db.models import (
    Source,
    Document,
    DocumentVersion,
    IngestionJob,
    IngestionJobItem,
    AuditEvent,
)
from adam.db.session import get_engine, get_session
from adam.extract.pipeline import DocumentExtractionPipeline
from adam.ingest.checkpoint import CompoundCursor, CheckpointState
from adam.ingest.crawler import UrlCrawlerGuard, DisallowedUrlError
from adam.ingest.validator import ContentValidator
from adam.rag.chunker import chunk_document_version
from adam.storage.base import get_storage_backend
from adam.vocabularies import (
    SourceStatus,
    LifecycleStatus,
    AuthorityLevel,
    DocType,
    DepartmentId,
)

logger = logging.getLogger(__name__)


class JobController:
    """Thread-safe cooperative controller for an active ingestion job."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.listeners: Set[asyncio.Queue] = set()
        self.last_broadcast_time: float = 0.0
        self.lock = threading.Lock()

    def request_pause(self) -> None:
        self.pause_event.set()

    def request_stop(self) -> None:
        self.stop_event.set()

    def is_paused(self) -> bool:
        return self.pause_event.is_set()

    def is_stopped(self) -> bool:
        return self.stop_event.is_set()

    def add_listener(self, q: asyncio.Queue) -> None:
        with self.lock:
            self.listeners.add(q)

    def remove_listener(self, q: asyncio.Queue) -> None:
        with self.lock:
            self.listeners.discard(q)

    def broadcast(self, event_data: Dict[str, Any], force: bool = False) -> None:
        now = time.time()
        # Throttled broadcast (max once every 300ms) unless force=True
        if not force and (now - self.last_broadcast_time < 0.3):
            return

        self.last_broadcast_time = now
        with self.lock:
            for q in list(self.listeners):
                try:
                    q.put_nowait(event_data)
                except Exception:
                    pass


class IngestionControlPlane:
    """Production-grade Ingestion Control Plane managing the complete ingestion lifecycle."""

    def __init__(self, max_workers: int = 3):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ingest-worker")
        self._controllers: Dict[str, JobController] = {}
        self._lock = threading.Lock()

    def _get_or_create_controller(self, job_id: str) -> JobController:
        with self._lock:
            if job_id not in self._controllers:
                self._controllers[job_id] = JobController(job_id)
            return self._controllers[job_id]

    def _cleanup_controller(self, job_id: str) -> None:
        with self._lock:
            self._controllers.pop(job_id, None)

    # ── Job Lifecycle Commands ──────────────────────────────────────────────

    def start_job(
        self,
        source_id: str,
        job_type: str = "FULL",  # FULL, INCREMENTAL
        files: Optional[List[Tuple[str, bytes]]] = None,
        max_items: Optional[int] = None,
        user_id: str = "admin",
        trace_id: Optional[str] = None,
    ) -> IngestionJob:
        """Submit a new ingestion job for asynchronous execution."""
        session = get_session()
        try:
            source = session.query(Source).filter(Source.id == source_id).first()
            if not source:
                raise ValueError(f"Source with id '{source_id}' not found.")

            job_id = f"job_{uuid.uuid4().hex[:12]}"
            trace_id = trace_id or f"tr_{uuid.uuid4().hex[:12]}"

            job = IngestionJob(
                id=job_id,
                source_id=source.id,
                status="QUEUED",
                job_type=job_type.upper(),
                current_stage="IDLE",
                trace_id=trace_id,
                collector_version=COLLECTOR_VERSION,
                count_found=len(files) if files else 0,
                count_ingested=0,
                count_skipped=0,
                count_failed=0,
                progress_pct=0.0,
                checkpoint_json=CheckpointState().to_dict(),
                failures_json=[],
                metrics_json={"started_timestamp": datetime.now(timezone.utc).isoformat()},
                started_at=datetime.now(timezone.utc),
            )
            session.add(job)
            session.commit()
            session.refresh(job)

            # Enqueue background execution
            controller = self._get_or_create_controller(job_id)
            self._executor.submit(
                self._run_job_pipeline,
                job_id=job_id,
                source_id=source_id,
                job_type=job_type.upper(),
                files=files,
                max_items=max_items,
                user_id=user_id,
                controller=controller,
            )

            return job
        finally:
            session.close()

    def pause_job(self, job_id: str, user_id: str = "admin") -> IngestionJob:
        """Request cooperative pause. Job enters DRAINING until in-flight items complete, then PAUSED."""
        session = get_session()
        try:
            job = session.query(IngestionJob).filter(IngestionJob.id == job_id).first()
            if not job:
                raise ValueError(f"Job '{job_id}' not found.")

            if job.status not in ("PROCESSING", "DISCOVERY", "QUEUED"):
                raise ValueError(f"Cannot pause job '{job_id}' in status '{job.status}'.")

            job.pause_requested = True
            job.status = "DRAINING"
            job.current_stage = "DRAINING"
            session.commit()

            controller = self._get_or_create_controller(job_id)
            controller.request_pause()
            controller.broadcast({"type": "status_change", "job_id": job_id, "status": "DRAINING"}, force=True)

            return job
        finally:
            session.close()

    def resume_job(self, job_id: str, user_id: str = "admin") -> IngestionJob:
        """Resume execution of a PAUSED job from its saved checkpoint compound cursor."""
        session = get_session()
        try:
            job = session.query(IngestionJob).filter(IngestionJob.id == job_id).first()
            if not job:
                raise ValueError(f"Job '{job_id}' not found.")

            if job.status != "PAUSED":
                raise ValueError(f"Cannot resume job '{job_id}' with status '{job.status}'. Only PAUSED jobs can be resumed.")

            job.status = "QUEUED"
            job.pause_requested = False
            job.cancel_requested = False
            job.current_stage = "RESUMING"
            session.commit()

            controller = self._get_or_create_controller(job_id)
            controller.pause_event.clear()
            controller.stop_event.clear()

            self._executor.submit(
                self._run_job_pipeline,
                job_id=job_id,
                source_id=job.source_id,
                job_type=job.job_type,
                files=None,
                max_items=None,
                user_id=user_id,
                controller=controller,
                is_resume=True,
            )

            return job
        finally:
            session.close()

    def stop_job(self, job_id: str, user_id: str = "admin") -> IngestionJob:
        """Request cooperative cancellation. Job enters CANCELLING, rolls back current item, then CANCELLED."""
        session = get_session()
        try:
            job = session.query(IngestionJob).filter(IngestionJob.id == job_id).first()
            if not job:
                raise ValueError(f"Job '{job_id}' not found.")

            if job.status in ("COMPLETED", "CANCELLED", "FAILED"):
                return job

            job.cancel_requested = True
            job.status = "CANCELLING"
            job.current_stage = "CANCELLING"
            session.commit()

            controller = self._get_or_create_controller(job_id)
            controller.request_stop()
            controller.broadcast({"type": "status_change", "job_id": job_id, "status": "CANCELLING"}, force=True)

            return job
        finally:
            session.close()

    def retry_job(self, parent_job_id: str, user_id: str = "admin") -> IngestionJob:
        """Create and run a RETRY job targeting only the failed items from parent_job_id."""
        session = get_session()
        try:
            parent_job = session.query(IngestionJob).filter(IngestionJob.id == parent_job_id).first()
            if not parent_job:
                raise ValueError(f"Parent job '{parent_job_id}' not found.")

            failed_items = (
                session.query(IngestionJobItem)
                .filter(IngestionJobItem.job_id == parent_job_id, IngestionJobItem.status == "FAILED")
                .all()
            )
            if not failed_items:
                raise ValueError(f"Job '{parent_job_id}' has no failed items to retry.")

            retry_job_id = f"job_{uuid.uuid4().hex[:12]}"
            retry_job = IngestionJob(
                id=retry_job_id,
                source_id=parent_job.source_id,
                parent_job_id=parent_job.id,
                status="QUEUED",
                job_type="RETRY",
                current_stage="IDLE",
                trace_id=f"tr_{uuid.uuid4().hex[:12]}",
                collector_version=COLLECTOR_VERSION,
                count_found=len(failed_items),
                count_ingested=0,
                count_skipped=0,
                count_failed=0,
                progress_pct=0.0,
                checkpoint_json=CheckpointState(total_discovered=len(failed_items)).to_dict(),
                failures_json=[],
                metrics_json={"retry_parent_id": parent_job.id},
                started_at=datetime.now(timezone.utc),
            )
            session.add(retry_job)
            session.commit()
            session.refresh(retry_job)

            controller = self._get_or_create_controller(retry_job_id)
            self._executor.submit(
                self._run_job_pipeline,
                job_id=retry_job_id,
                source_id=parent_job.source_id,
                job_type="RETRY",
                files=None,
                max_items=None,
                user_id=user_id,
                controller=controller,
                parent_failed_keys=[fi.item_key for fi in failed_items],
            )

            return retry_job
        finally:
            session.close()

    # ── Pipeline Worker Execution ───────────────────────────────────────────

    def _run_job_pipeline(
        self,
        job_id: str,
        source_id: str,
        job_type: str,
        files: Optional[List[Tuple[str, bytes]]],
        max_items: Optional[int],
        user_id: str,
        controller: JobController,
        is_resume: bool = False,
        parent_failed_keys: Optional[List[str]] = None,
    ) -> None:
        """Background worker coordinating bounded discovery and item processing."""
        session = get_session()
        storage = get_storage_backend()

        try:
            job = session.query(IngestionJob).filter(IngestionJob.id == job_id).first()
            source = session.query(Source).filter(Source.id == source_id).first()
            if not job or not source:
                return

            job.status = "DISCOVERY"
            job.current_stage = "DISCOVERY"
            session.commit()
            controller.broadcast({"type": "stage_change", "job_id": job_id, "stage": "DISCOVERY", "status": "DISCOVERY"}, force=True)

            connector = ConnectorRegistry.resolve_connector(source, in_memory_files=files)

            # Read compound cursor if resuming or incremental
            checkpoint = CheckpointState.from_dict(job.checkpoint_json)
            compound_cursor = checkpoint.cursor.to_dict() if (is_resume or job_type == "INCREMENTAL") else None

            # 1. Bounded Queue with Backpressure (maxsize=100)
            discovery_queue: queue.Queue = queue.Queue(maxsize=100)
            discovery_error: List[str] = []
            discovery_exhausted = threading.Event()
            current_run_urls: Set[str] = set()

            def _discovery_producer():
                try:
                    if job_type == "RETRY" and parent_failed_keys:
                        # Only discover items matching failed keys
                        for item in connector.discover(source):
                            if controller.is_stopped() or controller.is_paused():
                                break
                            if item.source_url in parent_failed_keys:
                                discovery_queue.put(item)
                    elif job_type == "INCREMENTAL" or is_resume:
                        for item in connector.discover_incremental(source, compound_cursor=compound_cursor):
                            if controller.is_stopped() or controller.is_paused():
                                break
                            discovery_queue.put(item)
                    else:
                        for item in connector.discover(source):
                            if controller.is_stopped() or controller.is_paused():
                                break
                            discovery_queue.put(item)
                except Exception as ex:
                    logger.error("Discovery error on job %s: %s", job_id, ex)
                    discovery_error.append(str(ex))
                finally:
                    discovery_exhausted.set()
                    discovery_queue.put(None)  # Sentinel

            producer_thread = threading.Thread(target=_discovery_producer, name=f"discovery-{job_id}", daemon=True)
            producer_thread.start()

            # 2. Worker Consumer Loop
            job.status = "PROCESSING"
            job.current_stage = "FETCH_AND_VALIDATE"
            session.commit()
            controller.broadcast({"type": "stage_change", "job_id": job_id, "stage": "FETCH_AND_VALIDATE", "status": "PROCESSING"}, force=True)

            guard = UrlCrawlerGuard(
                permitted_domains=source.permitted_domains,
                permitted_path_prefixes=source.permitted_path_prefixes,
            )

            total_found = job.count_found if is_resume else 0
            ingested_count = job.count_ingested
            skipped_count = job.count_skipped
            failed_count = job.count_failed

            while True:
                # Check for stop request
                if controller.is_stopped():
                    job.status = "CANCELLED"
                    job.current_stage = "CANCELLED"
                    job.completed_at = datetime.now(timezone.utc)
                    session.commit()
                    controller.broadcast({"type": "status_change", "job_id": job_id, "status": "CANCELLED"}, force=True)
                    return

                # Check for pause request
                if controller.is_paused():
                    job.status = "PAUSED"
                    job.current_stage = "PAUSED"
                    job.checkpoint_json = checkpoint.to_dict()
                    session.commit()
                    controller.broadcast({"type": "status_change", "job_id": job_id, "status": "PAUSED"}, force=True)
                    return

                try:
                    item: Optional[DiscoveredItem] = discovery_queue.get(timeout=1.0)
                except queue.Empty:
                    if discovery_exhausted.is_set():
                        break
                    continue

                if item is None:
                    # Sentinel reached
                    break

                total_found += 1
                job.count_found = total_found
                item_url = item.source_url
                current_run_urls.add(item_url)

                # Find or create IngestionJobItem
                job_item = (
                    session.query(IngestionJobItem)
                    .filter(IngestionJobItem.job_id == job_id, IngestionJobItem.item_key == item_url)
                    .first()
                )
                if not job_item:
                    job_item = IngestionJobItem(
                        job_id=job.id,
                        item_key=item_url,
                        title=item.title,
                        status="PROCESSING",
                    )
                    session.add(job_item)
                    session.flush()

                item_start_time = time.perf_counter()

                try:
                    # Stage 2: URL Guard Check
                    if item.source_url.startswith("http"):
                        canonical_url = guard.normalize_url(item.source_url)
                        guard.validate_or_raise(canonical_url)
                    else:
                        canonical_url = item.source_url

                    # Stage 2: Fetch & Content Validation
                    fetch_res = connector.fetch(item)
                    if fetch_res.http_status != 200:
                        raise ValueError(f"HTTP status {fetch_res.http_status} fetching document.")

                    data = fetch_res.data
                    sha256_hash = hashlib.sha256(data).hexdigest()
                    job_item.sha256 = sha256_hash

                    val_res = ContentValidator.validate(
                        data,
                        declared_mime_type=fetch_res.http_headers.get("content-type"),
                    )
                    if not val_res.is_safe:
                        raise ValueError(f"Content validation failed: {'; '.join(val_res.issues)}")

                    # Stage 3: SHA-256 Deduplication Check
                    existing_identical = (
                        session.query(DocumentVersion)
                        .join(Document, DocumentVersion.document_id == Document.id)
                        .filter(
                            Document.source_id == source.id,
                            DocumentVersion.source_url == canonical_url,
                            DocumentVersion.sha256 == sha256_hash,
                        )
                        .first()
                    )

                    if existing_identical:
                        # Deduplicated skip
                        skipped_count += 1
                        job_item.status = "SKIPPED"
                        job_item.document_id = existing_identical.document_id
                        job_item.version_id = existing_identical.id
                        job_item.duration_ms = (time.perf_counter() - item_start_time) * 1000.0
                        job.count_skipped = skipped_count
                        processed_total = ingested_count + skipped_count + failed_count
                        job.progress_pct = min(100.0, round((processed_total / max(1, total_found)) * 100.0, 1) if total_found > 0 else 0.0)
                        session.commit()
                        continue

                    # Stage 4: Storage & Version Creation
                    storage_key = f"{source.id}/{sha256_hash[:2]}/{sha256_hash}.bin"
                    storage.store(storage_key, data, expected_sha256=sha256_hash)

                    existing_doc_ver = (
                        session.query(DocumentVersion)
                        .join(Document, DocumentVersion.document_id == Document.id)
                        .filter(
                            Document.source_id == source.id,
                            DocumentVersion.source_url == canonical_url,
                        )
                        .order_by(DocumentVersion.retrieved_at.desc())
                        .first()
                    )

                    if existing_doc_ver:
                        # Supersede existing version
                        doc = existing_doc_ver.document
                        ver_id = f"ver_{uuid.uuid4().hex[:12]}"
                        version = DocumentVersion(
                            id=ver_id,
                            document_id=doc.id,
                            source_url=canonical_url,
                            source_locator=item.detail_page_url,
                            issued_on=item.displayed_date,
                            go_number=item.go_number,
                            gazette_number=item.gazette_number,
                            supersedes_version_id=existing_doc_ver.id,
                            sha256=sha256_hash,
                            mime_type=val_res.detected_mime_type,
                            byte_size=val_res.byte_size,
                            retrieved_at=fetch_res.retrieved_at,
                            provenance_status=val_res.suggested_provenance,
                            original_object_key=storage_key,
                            http_headers=fetch_res.http_headers,
                            metadata_json={**item.metadata, "validation_issues": val_res.issues},
                        )
                        session.add(version)
                        doc.current_version_id = ver_id
                        doc.updated_at = datetime.now(timezone.utc)
                    else:
                        # Brand new document
                        doc_id = f"doc_{uuid.uuid4().hex[:12]}"
                        ver_id = f"ver_{uuid.uuid4().hex[:12]}"
                        doc = Document(
                            id=doc_id,
                            source_id=source.id,
                            department_id=DepartmentId.validate_or_preserve(item.department_id or source.department_id),
                            doc_type=DocType.validate_or_preserve(item.doc_type),
                            title=item.title.strip() or "Untitled Official Document",
                            language=item.language or "hi",
                            authority_level=AuthorityLevel.validate_or_preserve(item.authority_level),
                            classification=source.access_classification,
                            current_version_id=ver_id,
                            lifecycle_status=LifecycleStatus.ACTIVE.value,
                        )
                        session.add(doc)
                        version = DocumentVersion(
                            id=ver_id,
                            document_id=doc_id,
                            source_url=canonical_url,
                            source_locator=item.detail_page_url,
                            issued_on=item.displayed_date,
                            go_number=item.go_number,
                            gazette_number=item.gazette_number,
                            sha256=sha256_hash,
                            mime_type=val_res.detected_mime_type,
                            byte_size=val_res.byte_size,
                            retrieved_at=fetch_res.retrieved_at,
                            provenance_status=val_res.suggested_provenance,
                            original_object_key=storage_key,
                            http_headers=fetch_res.http_headers,
                            metadata_json={**item.metadata, "validation_issues": val_res.issues},
                        )
                        session.add(version)

                    session.flush()

                    # Stage 5: Extraction & OCR Pipeline
                    extract_pipe = DocumentExtractionPipeline(session, storage)
                    extract_pipe.process_version(version.id, actor=user_id)

                    # Stage 6: Semantic Structure Chunking & Indexing
                    chunk_document_version(session, version.id)

                    # Success update
                    ingested_count += 1
                    job_item.status = "SUCCESS"
                    job_item.document_id = doc.id
                    job_item.version_id = version.id
                    job_item.duration_ms = (time.perf_counter() - item_start_time) * 1000.0

                    # Update checkpoint cursor
                    if "watermark_val" in item.metadata:
                        checkpoint.cursor.watermark = item.metadata["watermark_val"]
                        checkpoint.cursor.last_id = item.metadata.get("id_val")
                        checkpoint.high_watermark = item.metadata["watermark_val"]
                    checkpoint.processed_count += 1

                    session.commit()

                except Exception as item_err:
                    session.rollback()
                    failed_count += 1
                    logger.warning("Item %s failed: %s", item_url, item_err)

                    # Mark item failed
                    failed_item = (
                        session.query(IngestionJobItem)
                        .filter(IngestionJobItem.job_id == job_id, IngestionJobItem.item_key == item_url)
                        .first()
                    )
                    if failed_item:
                        failed_item.status = "FAILED"
                        failed_item.error_message = str(item_err)
                        failed_item.retry_count += 1
                        failed_item.duration_ms = (time.perf_counter() - item_start_time) * 1000.0
                    else:
                        failed_item = IngestionJobItem(
                            job_id=job_id,
                            item_key=item_url,
                            title=item.title,
                            status="FAILED",
                            error_message=str(item_err),
                            retry_count=1,
                            duration_ms=(time.perf_counter() - item_start_time) * 1000.0,
                        )
                        session.add(failed_item)

                    # Append to job failure summary
                    failures = list(job.failures_json or [])
                    failures.append({"item_key": item_url, "error": str(item_err), "timestamp": datetime.now(timezone.utc).isoformat()})
                    job.failures_json = failures
                    session.commit()

                # Update job progress aggregates
                processed_total = ingested_count + skipped_count + failed_count
                pct = round((processed_total / max(1, total_found)) * 100.0, 1) if total_found > 0 else 0.0

                job.count_ingested = ingested_count
                job.count_skipped = skipped_count
                job.count_failed = failed_count
                job.progress_pct = min(100.0, pct)
                session.commit()

                controller.broadcast({
                    "type": "progress",
                    "job_id": job_id,
                    "count_found": total_found,
                    "count_ingested": ingested_count,
                    "count_skipped": skipped_count,
                    "count_failed": failed_count,
                    "progress_pct": job.progress_pct,
                    "current_stage": job.current_stage,
                })

                if max_items and ingested_count >= max_items:
                    break

            # 3. Safe Deletion Reconciliation (Delta Quarantine)
            # ONLY execute if: Full sync, unconstrained by max_items, zero discovery errors, and connector supports deletion detection
            safe_to_reconcile = (
                job_type == "FULL"
                and max_items is None
                and not discovery_error
                and getattr(connector, "supports_deletion_detection", False)
                and current_run_urls
            )

            if safe_to_reconcile:
                job.current_stage = "DELTA_RECONCILIATION"
                session.commit()

                active_docs = (
                    session.query(Document)
                    .filter(Document.source_id == source.id, Document.lifecycle_status == LifecycleStatus.ACTIVE.value)
                    .all()
                )
                for adoc in active_docs:
                    doc_urls = {v.source_url for v in adoc.versions}
                    if not doc_urls.intersection(current_run_urls):
                        adoc.lifecycle_status = LifecycleStatus.QUARANTINED.value
                        adoc.updated_at = datetime.now(timezone.utc)
                        audit = AuditEvent(
                            entity_type="DOCUMENT",
                            entity_id=adoc.id,
                            action="QUARANTINE_REMOVAL",
                            actor=user_id,
                            details_json={"reason": "URL disappeared from source during verified complete full sync."},
                        )
                        session.add(audit)
                session.commit()

            # 4. Finalize Job Status
            job.completed_at = datetime.now(timezone.utc)
            checkpoint.discovery_complete = True
            job.checkpoint_json = checkpoint.to_dict()

            if discovery_error and total_found == 0:
                job.status = "FAILED"
                job.error_message = "; ".join(discovery_error)
            elif failed_count > 0 and ingested_count > 0:
                job.status = "PARTIAL_SUCCESS"
            elif failed_count > 0 and ingested_count == 0 and skipped_count == 0:
                job.status = "FAILED"
                job.error_message = "All discovered items failed during processing."
            else:
                job.status = "COMPLETED"

            job.current_stage = "COMPLETED"
            job.progress_pct = 100.0

            # Update Source status and last run
            source.last_run_at = job.completed_at
            source.last_run_status = job.status
            if checkpoint.high_watermark:
                cfg = dict(source.config_json or {})
                cfg["last_synced_watermark"] = checkpoint.high_watermark
                source.config_json = cfg

            session.commit()

            controller.broadcast({
                "type": "completion",
                "job_id": job_id,
                "status": job.status,
                "count_ingested": ingested_count,
                "count_skipped": skipped_count,
                "count_failed": failed_count,
                "progress_pct": 100.0,
            }, force=True)

        except Exception as fatal_err:
            logger.error("Fatal exception in ingestion pipeline for job %s: %s", job_id, fatal_err, exc_info=True)
            session.rollback()
            failed_job = session.query(IngestionJob).filter(IngestionJob.id == job_id).first()
            if failed_job:
                failed_job.status = "FAILED"
                failed_job.error_message = str(fatal_err)
                failed_job.completed_at = datetime.now(timezone.utc)
                session.commit()
            controller.broadcast({"type": "status_change", "job_id": job_id, "status": "FAILED", "error": str(fatal_err)}, force=True)

        finally:
            session.close()
            self._cleanup_controller(job_id)

    # ── Live Telemetry Subscription ─────────────────────────────────────────

    async def stream_job_telemetry(self, job_id: str) -> AsyncIterator[str]:
        """Stream real-time job progress as throttled Server-Sent Events (SSE)."""
        controller = self._get_or_create_controller(job_id)
        q: asyncio.Queue = asyncio.Queue()
        controller.add_listener(q)

        # Immediate first snapshot from DB
        session = get_session()
        try:
            job = session.query(IngestionJob).filter(IngestionJob.id == job_id).first()
            if job:
                initial_event = {
                    "type": "snapshot",
                    "job_id": job.id,
                    "status": job.status,
                    "current_stage": job.current_stage,
                    "count_found": job.count_found,
                    "count_ingested": job.count_ingested,
                    "count_skipped": job.count_skipped,
                    "count_failed": job.count_failed,
                    "progress_pct": job.progress_pct,
                }
                yield f"data: {json.dumps(initial_event)}\n\n"
        finally:
            session.close()

        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") == "completion" or event.get("status") in ("COMPLETED", "PARTIAL_SUCCESS", "FAILED", "CANCELLED"):
                        break
                except asyncio.TimeoutError:
                    # SSE keep-alive comment
                    yield ": keep-alive\n\n"
        finally:
            controller.remove_listener(q)


# Global Control Plane Singleton
GLOBAL_INGESTION_CONTROL_PLANE = IngestionControlPlane()
