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

@cli.group(name="review")
def review_group():
    """Manage page-level quality review, annotations, and corrections."""
    pass


@review_group.command(name="list")
@click.option("--version-id", default=None, help="Filter by DocumentVersion ID")
@click.option("--status", default=ReviewStatus.FLAGGED.value, help="Filter by review status (default: FLAGGED)")
def list_review_pages(version_id: Optional[str], status: Optional[str]):
    """List document pages matching review status filter."""
    session = get_session()
    query = session.query(DocumentPage)
    if version_id:
        query = query.filter(DocumentPage.version_id == version_id)
    if status and status.upper() != "ALL":
        query = query.filter(DocumentPage.review_status == status.upper())
    pages = query.order_by(DocumentPage.version_id, DocumentPage.page_number).all()

    if not pages:
        click.echo("No pages found matching review criteria.")
        session.close()
        return

    click.echo(f"{'Page ID':<36} {'Page #':<8} {'Version ID':<36} {'Status':<16} {'Confidence':<10}")
    click.echo("-" * 115)
    for p in pages:
        conf_str = f"{p.text_confidence:.2f}" if p.text_confidence is not None else "N/A"
        click.echo(f"{p.id:<36} {p.page_number:<8} {p.version_id:<36} {p.review_status:<16} {conf_str:<10}")
    session.close()


@review_group.command(name="approve")
@click.argument("page_id")
@click.option("--reviewer", default="admin", help="Reviewer username or ID (default: admin)")
def approve_page(page_id: str, reviewer: str):
    """Approve a document page review status."""
    session = get_session()
    page = session.query(DocumentPage).filter(DocumentPage.id == page_id).first()
    if not page:
        click.echo(f"Error: DocumentPage '{page_id}' not found.", err=True)
        session.close()
        sys.exit(1)

    previous_status = page.review_status
    page.review_status = ReviewStatus.REVIEWED.value

    audit = AuditEvent(
        entity_type="DOCUMENT_PAGE",
        entity_id=page.id,
        action="REVIEW_APPROVE",
        actor=reviewer,
        details_json={
            "page_number": page.page_number,
            "version_id": page.version_id,
            "previous_status": previous_status,
            "new_status": ReviewStatus.REVIEWED.value,
        },
    )
    session.add(audit)

    try:
        session.commit()
        click.echo(f"Page approved: {page.id} [Status: {page.review_status}] by {reviewer}")
    except Exception as e:
        session.rollback()
        click.echo(f"Error approving page: {e}", err=True)
        sys.exit(1)
    finally:
        session.close()


@review_group.command(name="correct")
@click.argument("page_id")
@click.option("--text", required=True, help="Corrected transcript text for the page")
@click.option("--reviewer", default="admin", help="Reviewer username or ID (default: admin)")
def correct_page(page_id: str, text: str, reviewer: str):
    """Submit a reviewer correction for a document page."""
    session = get_session()
    page = session.query(DocumentPage).filter(DocumentPage.id == page_id).first()
    if not page:
        click.echo(f"Error: DocumentPage '{page_id}' not found.", err=True)
        session.close()
        sys.exit(1)

    previous_status = page.review_status
    annotation = ReviewAnnotation(
        page_id=page.id,
        reviewer=reviewer,
        corrected_text=text,
        annotation_type="TEXT_CORRECTION",
    )
    session.add(annotation)

    page.review_status = ReviewStatus.CORRECTED.value
    page.selected_text = text

    audit = AuditEvent(
        entity_type="DOCUMENT_PAGE",
        entity_id=page.id,
        action="REVIEW_CORRECT",
        actor=reviewer,
        details_json={
            "annotation_id": annotation.id,
            "page_number": page.page_number,
            "version_id": page.version_id,
            "previous_status": previous_status,
            "new_status": ReviewStatus.CORRECTED.value,
        },
    )
    session.add(audit)

    try:
        session.commit()
        click.echo(
            f"Page corrected: {page.id} [Status: {page.review_status}] by {reviewer}\n"
            f"  Annotation ID: {annotation.id}"
        )
    except Exception as e:
        session.rollback()
        click.echo(f"Error correcting page: {e}", err=True)
        sys.exit(1)
    finally:
        session.close()
