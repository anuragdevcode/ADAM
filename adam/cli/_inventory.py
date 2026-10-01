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

@cli.group(name="inventory")
def inventory_group():
    """Export and verify cryptographically signed inventories."""
    pass


@inventory_group.command(name="export")
@click.argument("source_id")
@click.option("--output", "-o", default=None, help="Output file path (JSON)")
@click.option("--key", default=None, help="HMAC secret signing key")
def export_inventory(source_id: str, output: Optional[str], key: Optional[str]):
    """Export signed inventory manifest for a source (Acceptance Criteria 1)."""
    session = get_session()
    try:
        manifest = SignedInventory.generate_for_source(
            session=session,
            source_id=source_id,
            secret_key=key or SIGNING_SECRET,
        )
        content = json.dumps(manifest, indent=2, ensure_ascii=False)
        if output:
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            click.echo(f"Signed inventory exported to {output} ({manifest['total_records']} records)")
        else:
            click.echo(content)
    except Exception as e:
        click.echo(f"Error exporting inventory: {e}", err=True)
        sys.exit(1)
    finally:
        session.close()


@inventory_group.command(name="verify")
@click.argument("manifest_path", type=click.Path(exists=True))
@click.option("--key", default=None, help="HMAC secret signing key")
def verify_inventory(manifest_path: str, key: Optional[str]):
    """Verify cryptographic signature and record integrity of an inventory manifest."""
    raw = Path(manifest_path).read_text(encoding="utf-8")
    manifest = json.loads(raw)
    valid, err = SignedInventory.verify_manifest(manifest, secret_key=key or SIGNING_SECRET)
    if valid:
        click.echo(f"SUCCESS: Inventory manifest is authentic and untampered ({manifest.get('total_records')} records verified).")
    else:
        click.echo(f"FAILED: Signature or integrity check failed: {err}", err=True)
        sys.exit(1)
