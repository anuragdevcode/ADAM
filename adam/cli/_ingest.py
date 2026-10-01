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

@cli.group(name="ingest")
def ingest_group():
    """Execute authorized acquisition crawls and delta runs."""
    pass


@ingest_group.command(name="run")
@click.argument("source_id")
@click.option("--actor", default="cli_operator", help="User or agent initiating crawl")
@click.option("--limit", default=None, type=int, help="Limit number of documents to download")
@click.option("--process/--no-process", default=False, help="Automatically run extraction and chunking")
def run_ingest(source_id: str, actor: str, limit: Optional[int], process: bool):
    """Run an authorized ingestion crawl for a registered source."""
    engine = get_engine()
    init_db(engine)
    session = get_session(engine)
    storage = LocalStorageBackend(STORAGE_DIR)

    source = session.query(Source).filter(Source.id == source_id).first()
    if not source:
        click.echo(f"Error: Source '{source_id}' not found.", err=True)
        session.close()
        sys.exit(1)

    # Sync latest permitted domains and prefixes from seeds
    from adam.seeds import INITIAL_SOURCES_PLAYBOOK
    for sheet in INITIAL_SOURCES_PLAYBOOK:
        if sheet.id == source_id:
            source.permitted_domains = list(sheet.permitted_domains)
            source.permitted_path_prefixes = list(sheet.permitted_path_prefixes)
            session.commit()
            break

    # Select connector according to department / domain
    if "ukrd" in source.id or any("ukrd" in d for d in source.permitted_domains):
        connector = UkrdConnector()
    elif "gazette" in source.id or any("gazette" in d for d in source.permitted_domains):
        connector = EGazetteConnector()
    else:
        connector = EkoshTreasuryConnector()

    pipeline = IngestionPipeline(session, storage, connector)
    try:
        run_record = pipeline.run(source_id, actor=actor, max_items=limit)
        click.echo(
            f"Ingestion run completed: {run_record.id}\n"
            f"  Count Found:      {run_record.count_found}\n"
            f"  Count Downloaded: {run_record.count_downloaded}\n"
            f"  Failures:         {len(run_record.failures_json or [])}"
        )
        if process and run_record.count_downloaded > 0:
            from adam.extract.pipeline import DocumentExtractionPipeline
            from adam.rag.chunker import chunk_document_version
            extract_pipe = DocumentExtractionPipeline(session, storage)
            versions = (
                session.query(DocumentVersion)
                .join(Document, DocumentVersion.document_id == Document.id)
                .filter(Document.source_id == source_id)
                .order_by(DocumentVersion.retrieved_at.desc())
                .limit(run_record.count_downloaded)
                .all()
            )
            processed_count = 0
            for v in versions:
                try:
                    extract_pipe.process_version(v.id)
                    chunk_document_version(session, v.id)
                    processed_count += 1
                except Exception as ex:
                    click.echo(f"  Warning: extraction/chunking failed for {v.id}: {ex}")
            session.commit()
            click.echo(f"  Processed & Chunked: {processed_count} versions into searchable repository.")
    except Exception as e:
        click.echo(f"Ingestion failed: {e}", err=True)
        sys.exit(1)
    finally:
        session.close()


@ingest_group.command(name="live")
@click.option("--source-id", default="src_ekosh_treasury_go", help="Target official source ID")
@click.option("--limit", default=5, type=int, help="Maximum number of genuine orders to acquire")
@click.option("--process/--no-process", default=True, help="Automatically run extraction and chunking")
@click.option("--actor", default="records_officer", help="User or agent initiating crawl")
def live_ingest(source_id: str, limit: int, process: bool, actor: str):
    """Acquire genuine, historical orders from live Uttarakhand portals into the repository."""
    click.echo(f"=== Live Acquisition from Uttarakhand Portal [{source_id}] ===")
    ctx = click.get_current_context()
    ctx.invoke(run_ingest, source_id=source_id, actor=actor, limit=limit, process=process)
