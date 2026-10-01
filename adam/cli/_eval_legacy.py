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

@cli.command(name="eval")
@click.option("--populate", is_flag=True, default=False, help="Populate test corpus if missing.")
def run_eval(populate: bool):
    """Run offline gold set pilot gate benchmark and output scorecard."""
    from adam.db.session import get_session
    from adam.rag.evaluation import evaluate_gold_set, populate_eval_corpus

    session = get_session()
    if populate:
        click.echo("Seeding evaluation gold corpus...")
        populate_eval_corpus(session)

    click.echo("Executing pilot gate gold set evaluation (215 queries)...")
    scorecard = evaluate_gold_set(session)
    session.close()

    click.echo("\n" + "=" * 65)
    click.secho("ADAM PILOT GATE EVALUATION SCORECARD", bold=True)
    click.echo("=" * 65)
    click.echo(f"Total Queries Evaluated:    {scorecard.total_queries}")
    click.echo(f"Answer-Bearing Queries:     {scorecard.answer_bearing_queries}")
    click.echo(f"Recall@10 (Target >= 90%):   {scorecard.recall_at_10 * 100:.2f}%")
    click.echo(f"Citation Precision (>= 95%): {scorecard.citation_page_precision * 100:.2f}%")
    click.echo(f"No-Answer Refusal (100%):    {scorecard.no_answer_refusal_rate * 100:.2f}%")
    click.echo(f"Cross-Tenant / ACL Leaks:    {scorecard.acl_leak_count} (Gate Target: 0)")
    click.echo("-" * 65)
    status_text = "PASSED" if scorecard.gate_passed else "FAILED"
    status_color = "green" if scorecard.gate_passed else "red"
    click.secho(f"Pilot Gate Overall Status:   {status_text}", fg=status_color, bold=True)
    click.echo("=" * 65)



# ── Backup & Disaster Recovery CLI Commands ─────────────────────────────
