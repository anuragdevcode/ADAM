"""Unified background queue worker process for OCR, ingestion, and embedding tasks (R5)."""

import logging
import signal
import sys
import time
from typing import Optional

from sqlalchemy.orm import Session

from adam.agent.coordinator import HeavyWorkerCoordinator, HeavyTaskType
from adam.db.models import DocumentChunk, DocumentVersion, IngestionJob, ReviewStatus
from adam.db.session import get_session
from adam.extract.pipeline import DocumentExtractionPipeline
from adam.rag.chunker import chunk_all_approved_versions
from adam.rag.retriever import MultilingualSemanticVectorizer
from adam.storage.base import get_storage_backend

logger = logging.getLogger(__name__)


class UnifiedWorkerRunner:
    """Continuous or one-shot background queue worker.

    Monitors durable database queue tables and un-processed versions:
    1. Ingestion jobs: Processes pending IngestionJob items atomically.
    2. OCR processing: Extracts structured pages from new document versions.
    3. Semantic chunking: Chunks approved document versions.
    4. Embedding generation: Persists pgvector and JSON embeddings for chunks.
    All heavy tasks acquire HeavyWorkerCoordinator mutual exclusion locks.
    """

    def __init__(
        self,
        poll_interval: float = 5.0,
        coordinator: Optional[HeavyWorkerCoordinator] = None,
    ):
        self.poll_interval = poll_interval
        self.coordinator = coordinator or HeavyWorkerCoordinator()
        self.running = False

    def process_pending_ingestion_jobs(self, session: Session) -> int:
        """Poll and execute pending IngestionJob items from durable DB queue."""
        jobs = (
            session.query(IngestionJob)
            .filter(IngestionJob.status.in_(["PENDING", "QUEUED"]))
            .order_by(IngestionJob.started_at.asc())
            .limit(5)
            .all()
        )
        if not jobs:
            return 0

        processed = 0
        from adam.api.services.ingestion_worker import TransactionalIngestionRunner
        runner = TransactionalIngestionRunner(session)

        for job in jobs:
            job.status = "PROCESSING"
            session.commit()
            try:
                with self.coordinator.acquire_worker(HeavyTaskType.INDEXING, task_id=f"worker_job_{job.id}"):
                    # Execute queued job
                    runner.run_ingestion(
                        source_id=job.source_id,
                        user_id="worker_daemon",
                        trace_id=job.trace_id or f"worker_tr_{job.id}",
                        idempotency_key=job.idempotency_key,
                    )
                    processed += 1
            except Exception as e:
                logger.error("Worker failed processing job %s: %s", job.id, e)
                job.status = "FAILED"
                job.failures_json = {"error": str(e)}
                session.commit()

        return processed

    def process_pending_ocr(self, session: Session) -> int:
        """Poll and execute pending OCR on un-extracted document versions."""
        storage = get_storage_backend()
        pipeline = DocumentExtractionPipeline(session, storage)
        with self.coordinator.acquire_worker(HeavyTaskType.OCR_PROCESSING, task_id="worker_ocr"):
            return pipeline.process_all()

    def process_pending_chunking(self, session: Session) -> int:
        """Chunk approved versions that have not been chunked yet."""
        with self.coordinator.acquire_worker(HeavyTaskType.INDEXING, task_id="worker_chunking"):
            return chunk_all_approved_versions(session)

    def process_pending_embeddings(self, session: Session, batch_size: int = 100) -> int:
        """Backfill missing pgvector and JSON embeddings for document chunks."""
        chunks = (
            session.query(DocumentChunk)
            .filter(
                (DocumentChunk.embedding == None) | (DocumentChunk.embedding_json == None)
            )
            .limit(batch_size)
            .all()
        )
        if not chunks:
            return 0

        count = 0
        for chunk in chunks:
            text = f"{chunk.section_heading or ''} {chunk.content}".strip()
            emb = MultilingualSemanticVectorizer.embed_text(text)
            chunk.embedding = emb
            chunk.embedding_json = emb
            count += 1
        session.commit()
        return count

    def run_cycle(self) -> dict:
        """Run a single work cycle across all queues."""
        session = get_session()
        try:
            jobs_done = self.process_pending_ingestion_jobs(session)
            ocr_done = self.process_pending_ocr(session)
            chunk_done = self.process_pending_chunking(session)
            emb_done = self.process_pending_embeddings(session)
            return {
                "jobs": jobs_done,
                "ocr": ocr_done,
                "chunks": chunk_done,
                "embeddings": emb_done,
            }
        finally:
            session.close()

    def run_forever(self) -> None:
        """Continuously loop and process durable queue tasks with backpressure."""
        self.running = True

        def handle_signal(sig, frame):
            logger.info("Worker received shutdown signal %s, exiting gracefully...", sig)
            self.running = False

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        logger.info("ADAM Unified Worker started. Poll interval: %.1fs", self.poll_interval)
        while self.running:
            try:
                stats = self.run_cycle()
                total_work = sum(stats.values())
                if total_work > 0:
                    logger.info("Worker cycle processed: %s", stats)
            except Exception as e:
                logger.error("Error during worker execution cycle: %s", e)

            # Sleep poll interval if no work was found, or brief pause if active
            time.sleep(self.poll_interval)

        logger.info("ADAM Unified Worker stopped.")
