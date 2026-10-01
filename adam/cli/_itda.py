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

@cli.group(name="itda")
def itda_group():
    """Ingest authentic ITDA-curated sample sets and departmental batches."""
    pass


@itda_group.command(name="ingest-batch")
@click.argument("batch_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--dept", default="FINANCE_TREASURY", help="Department ID")
@click.option("--owner", default="ITDA / Uttarakhand Departmental Lead", help="Owner name")
@click.option("--contact", default="itda@uk.gov.in", help="Departmental contact")
@click.option("--authority-ref", default="ITDA-CURATED-BATCH-2024", help="Written authority reference")
def ingest_itda_batch(batch_dir: str, dept: str, owner: str, contact: str, authority_ref: str):
    """Onboard and ingest an authentic ITDA-curated batch of government orders."""
    from adam.connectors.itda import ITDASampleBatchConnector
    from adam.extract.pipeline import DocumentExtractionPipeline
    session = get_session()
    storage = LocalStorageBackend(STORAGE_DIR)
    registry = SourceRegistry(session)

    source_id = f"src_itda_{Path(batch_dir).name.lower().replace(' ', '_')[:24]}"
    existing = registry.get(source_id)
    if not existing:
        sheet = SourceOnboardingSheet(
            id=source_id,
            name=f"ITDA Curated Batch ({Path(batch_dir).name})",
            department_id=dept,
            owner_name=owner,
            owner_contact=contact,
            written_authority_ref=authority_ref,
            permitted_domains=["local.uk.gov.in", "localhost"],
            permitted_path_prefixes=["/"],
            access_classification=Classification.PUBLIC.value,
        )
        registry.onboard(sheet, actor="itda_admin")
        registry.approve(source_id, approver="itda_admin", notes="Authorized curated batch set.")
        session.commit()

    connector = ITDASampleBatchConnector(batch_dir)
    pipeline = IngestionPipeline(session, storage, connector)
    run_rec = pipeline.run(source_id, actor="itda_batch_ingest")

    # Run extraction on newly ingested batch
    ext_pipeline = DocumentExtractionPipeline(session, storage)
    extracted_count = ext_pipeline.process_all(source_id=source_id, actor="itda_extractor")

    click.echo(
        f"ITDA Batch Ingestion Complete:\n"
        f"  Source ID:         {source_id}\n"
        f"  Files Found:       {run_rec.count_found}\n"
        f"  Files Ingested:    {run_rec.count_downloaded}\n"
        f"  Documents Parsed:  {extracted_count}"
    )
    session.close()
