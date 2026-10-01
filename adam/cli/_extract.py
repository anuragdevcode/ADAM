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

@cli.group(name="extract")
def extract_group():
    """Extract clean structured text, tables, metadata, and precedent citations."""
    pass


@extract_group.command(name="run")
@click.option("--version-id", default=None, help="Specific DocumentVersion ID to process")
@click.option("--source-id", default=None, help="Process all pending versions from this source")
def run_extraction(version_id: Optional[str], source_id: Optional[str]):
    """Execute text, table, and precedent extraction pipeline on ingested records."""
    from adam.extract.pipeline import DocumentExtractionPipeline
    session = get_session()
    storage = LocalStorageBackend(STORAGE_DIR)
    pipeline = DocumentExtractionPipeline(session, storage)

    try:
        if version_id:
            ver = pipeline.process_version(version_id)
            click.echo(
                f"Extracted version {ver.id}:\n"
                f"  Pages:      {len(ver.pages)}\n"
                f"  Words:      {sum(p.word_count for p in ver.pages)}\n"
                f"  Subject:    {ver.attributes.subject if ver.attributes else 'N/A'}\n"
                f"  Precedents: {len(ver.precedent_references)}"
            )
        else:
            count = pipeline.process_all(source_id=source_id)
            click.echo(f"Extraction completed: processed {count} document versions.")
    except Exception as e:
        click.echo(f"Extraction failed: {e}", err=True)
        sys.exit(1)
    finally:
        session.close()


@extract_group.command(name="quality-report")
@click.option("--version-id", required=True, help="DocumentVersion ID to report on")
def extract_quality_report(version_id: str):
    """Display page-level extraction quality report and review status."""
    session = get_session()
    version = session.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
    pages = (
        session.query(DocumentPage)
        .filter(DocumentPage.version_id == version_id)
        .order_by(DocumentPage.page_number)
        .all()
    )
    if not version and not pages:
        click.echo(f"Error: Document version '{version_id}' not found.", err=True)
        session.close()
        sys.exit(1)

    click.echo(f"Quality Report for Version: {version_id}")
    click.echo(f"{'Page':<6} {'Review Status':<16} {'Confidence':<12} {'Scanned':<10} {'Word Count':<10}")
    click.echo("-" * 60)
    for p in pages:
        conf_str = f"{p.text_confidence:.2f}" if p.text_confidence is not None else "N/A"
        scanned_str = "Yes" if p.is_scanned else "No"
        click.echo(f"{p.page_number:<6} {p.review_status:<16} {conf_str:<12} {scanned_str:<10} {p.word_count:<10}")

    total_pages = len(pages)
    flagged_count = sum(1 for p in pages if p.review_status == ReviewStatus.FLAGGED.value)
    auto_approved_count = sum(1 for p in pages if p.review_status == ReviewStatus.AUTO_APPROVED.value)

    click.echo("\nSummary:")
    click.echo(f"  Total Pages:         {total_pages}")
    click.echo(f"  Flagged Count:       {flagged_count}")
    click.echo(f"  Auto-Approved Count: {auto_approved_count}")
    session.close()


@extract_group.command(name="processing-runs")
@click.option("--version-id", required=True, help="DocumentVersion ID to list processing runs for")
def extract_processing_runs(version_id: str):
    """List processing runs and OCR audit history for a document version."""
    session = get_session()
    version = session.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
    runs = (
        session.query(ProcessingRun)
        .filter(ProcessingRun.version_id == version_id)
        .order_by(ProcessingRun.started_at.asc())
        .all()
    )
    if not version and not runs:
        click.echo(f"Error: Document version '{version_id}' not found.", err=True)
        session.close()
        sys.exit(1)

    if not runs:
        click.echo(f"No processing runs found for version '{version_id}'.")
        session.close()
        return

    click.echo(f"Processing Runs for Version: {version_id}")
    click.echo("-" * 80)
    for r in runs:
        started = r.started_at.isoformat() if r.started_at else "N/A"
        completed = r.completed_at.isoformat() if r.completed_at else "N/A"
        click.echo(
            f"Run ID:         {r.id}\n"
            f"  Started At:     {started}\n"
            f"  Completed At:   {completed}\n"
            f"  Result:         {r.result}\n"
            f"  OCR Engine:     {r.ocr_engine or 'NONE'}\n"
            f"  Parser Version: {r.parser_version}\n"
            f"  Config Hash:    {r.config_hash}\n"
            + "-" * 40
        )
    session.close()
