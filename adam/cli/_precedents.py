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

@cli.group(name="precedents")
def precedents_group():
    """Query and navigate the legal precedent graph."""
    pass


@precedents_group.command(name="show")
@click.argument("document_id")
def show_precedents(document_id: str):
    """Display precedent citations and incoming/outgoing references for a document."""
    from adam.db.models import Document, PrecedentReference, DocumentVersion
    session = get_session()
    doc = session.query(Document).filter(Document.id == document_id).first()
    if not doc:
        click.echo(f"Document '{document_id}' not found.", err=True)
        session.close()
        sys.exit(1)

    click.echo(f"Document: {doc.title} [{doc.id}]")
    click.echo(f"Department: {doc.department_id} | Status: {doc.lifecycle_status}")
    click.echo("-" * 80)

    # 1. Outgoing Citations (what this document cites)
    click.echo("OUTGOING PRECEDENT CITATIONS (Cited by this document):")
    outgoing = (
        session.query(PrecedentReference)
        .join(DocumentVersion, PrecedentReference.source_version_id == DocumentVersion.id)
        .filter(DocumentVersion.document_id == doc.id)
        .all()
    )
    if not outgoing:
        click.echo("  No precedent citations recorded.")
    else:
        for ref in outgoing:
            resolved = f" -> Target Doc: {ref.target_document_id}" if ref.target_document_id else " (External/Unresolved)"
            click.echo(
                f"  [{ref.relation_type}] Order: {ref.cited_order_number or 'N/A'} "
                f"Date: {ref.cited_date or 'N/A'} Act/Rule: {ref.cited_act_or_rule or 'N/A'}{resolved}"
            )
            click.echo(f"    Raw Citation: {ref.raw_citation_text}")

    click.echo("\nINCOMING PRECEDENT CITATIONS (Documents citing this order):")
    incoming = (
        session.query(PrecedentReference)
        .filter(PrecedentReference.target_document_id == doc.id)
        .all()
    )
    if not incoming:
        click.echo("  No subsequent orders cite this document yet.")
    else:
        for inc in incoming:
            src_doc = inc.source_version.document if inc.source_version else None
            src_title = src_doc.title if src_doc else "Unknown Doc"
            click.echo(f"  [{inc.relation_type}] Cited by: {src_title} (Doc ID: {src_doc.id if src_doc else 'N/A'})")

    session.close()
