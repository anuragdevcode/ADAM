"""Explicit, versioned, and idempotent schema migrations for ADAM database."""

import logging
from datetime import datetime, timezone
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from adam.db.models import Base

logger = logging.getLogger(__name__)

MIGRATION_VERSION = "001_ingestion_control_plane"


def apply_ingestion_migrations(engine: Engine) -> None:
    """Apply versioned schema migrations for Ingestion Control Plane idempotently."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        # 1. Create schema_migrations tracking table if absent
        if "schema_migrations" not in existing_tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE schema_migrations (
                        version VARCHAR(64) PRIMARY KEY,
                        applied_at TIMESTAMP NOT NULL
                    )
                    """
                )
            )

        # Check if migration already recorded
        res = conn.execute(
            text("SELECT version FROM schema_migrations WHERE version = :ver"),
            {"ver": MIGRATION_VERSION},
        ).fetchone()

        # 2. Ensure all model tables exist (Base.metadata.create_all handles new tables like ingestion_job_items)
        Base.metadata.create_all(bind=conn)

        # 3. Additive columns check for existing tables
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())

        if "sources" in tables:
            source_cols = {c["name"] for c in inspector.get_columns("sources")}
            if "source_type" not in source_cols:
                conn.execute(text("ALTER TABLE sources ADD COLUMN source_type VARCHAR(32) DEFAULT 'WEBSITE'"))
            if "config_json" not in source_cols:
                conn.execute(text("ALTER TABLE sources ADD COLUMN config_json JSON"))
            if "last_run_at" not in source_cols:
                conn.execute(text("ALTER TABLE sources ADD COLUMN last_run_at TIMESTAMP"))
            if "last_run_status" not in source_cols:
                conn.execute(text("ALTER TABLE sources ADD COLUMN last_run_status VARCHAR(32)"))

        if "ingestion_jobs" in tables:
            job_cols = {c["name"] for c in inspector.get_columns("ingestion_jobs")}
            if "job_type" not in job_cols:
                conn.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN job_type VARCHAR(32) DEFAULT 'FULL'"))
            if "current_stage" not in job_cols:
                conn.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN current_stage VARCHAR(64) DEFAULT 'IDLE'"))
            if "count_skipped" not in job_cols:
                conn.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN count_skipped INTEGER DEFAULT 0"))
            if "count_failed" not in job_cols:
                conn.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN count_failed INTEGER DEFAULT 0"))
            if "progress_pct" not in job_cols:
                conn.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN progress_pct FLOAT DEFAULT 0.0"))
            if "checkpoint_json" not in job_cols:
                conn.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN checkpoint_json JSON"))
            if "failures_json" not in job_cols:
                conn.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN failures_json JSON"))
            if "metrics_json" not in job_cols:
                conn.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN metrics_json JSON"))
            if "cancel_requested" not in job_cols:
                conn.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN cancel_requested BOOLEAN DEFAULT 0"))
            if "pause_requested" not in job_cols:
                conn.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN pause_requested BOOLEAN DEFAULT 0"))
            if "parent_job_id" not in job_cols:
                conn.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN parent_job_id VARCHAR(64)"))

        if not res:
            now = datetime.now(timezone.utc)
            conn.execute(
                text("INSERT INTO schema_migrations (version, applied_at) VALUES (:ver, :now)"),
                {"ver": MIGRATION_VERSION, "now": now},
            )
            logger.info("Applied migration %s successfully.", MIGRATION_VERSION)
