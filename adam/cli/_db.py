"""Command line interface for ADAM Uttarakhand records acquisition and governance."""

import json
import sys
from pathlib import Path
from typing import Optional

# Ensure adam package root is importable when executed directly as a script
package_root = str(Path(__file__).resolve().parent.parent)
if package_root not in sys.path:
    sys.path.insert(0, package_root)

import click

from adam.config import DATABASE_URL, STORAGE_DIR, SIGNING_SECRET
from adam.connectors.egazette import EGazetteConnector
from adam.connectors.ekosh import EkoshTreasuryConnector
from adam.connectors.ukrd import UkrdConnector
from adam.db.session import get_engine, get_session, init_db
from adam.db.models import (
    AuditEvent,
    Document,
    DocumentPage,
    DocumentVersion,
    ExtractedTable,
    ProcessingRun,
    ReviewAnnotation,
    Source,
    TextBlock,
)
from adam.ingest.manifest import SignedInventory
from adam.ingest.pipeline import IngestionPipeline
from adam.ingest.registry import SourceRegistry, SourceOnboardingSheet
from adam.storage.local import LocalStorageBackend
from adam.vocabularies import (
    Classification,
    RefreshCadence,
    ReviewStatus,
    SourceStatus,
)


from adam.cli import cli

@cli.group(name="db")
def db_group():
    """Database schema migration and versioning commands."""
    pass


@db_group.command(name="upgrade")
@click.option("--revision", "-r", default="head", help="Target revision (default: head)")
def db_upgrade(revision: str):
    """Apply database migrations up to the specified revision."""
    import os
    from alembic.config import Config
    from alembic import command
    from adam.config import get_database_url

    ini_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    alembic_cfg = Config(ini_path)
    alembic_cfg.set_main_option("sqlalchemy.url", get_database_url())
    click.echo(f"Applying database migrations to revision: {revision}...")
    try:
        command.upgrade(alembic_cfg, revision)
        click.secho(f"Successfully upgraded database schema to {revision}.", fg="green", bold=True)
    except Exception as e:
        click.secho(f"Migration upgrade failed: {e}", fg="red", err=True)
        raise SystemExit(1)


@db_group.command(name="downgrade")
@click.option("--revision", "-r", required=True, help="Target revision (e.g. -1 or base)")
def db_downgrade(revision: str):
    """Revert database migrations down to the specified revision."""
    import os
    from alembic.config import Config
    from alembic import command
    from adam.config import get_database_url

    ini_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    alembic_cfg = Config(ini_path)
    alembic_cfg.set_main_option("sqlalchemy.url", get_database_url())
    click.echo(f"Reverting database migrations down to: {revision}...")
    try:
        command.downgrade(alembic_cfg, revision)
        click.secho(f"Successfully reverted database schema to {revision}.", fg="green", bold=True)
    except Exception as e:
        click.secho(f"Migration downgrade failed: {e}", fg="red", err=True)
        raise SystemExit(1)


@db_group.command(name="current")
def db_current():
    """Display current applied migration revision."""
    import os
    from alembic.config import Config
    from alembic import command
    from adam.config import get_database_url

    ini_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    alembic_cfg = Config(ini_path)
    alembic_cfg.set_main_option("sqlalchemy.url", get_database_url())
    command.current(alembic_cfg)


# ── Phase 03: Comprehensive Evaluation & Held-Out Harness ───────────────────
