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

@cli.group(name="audit")
def audit_group():
    """Cryptographic audit trail inspection and verification (S13)."""
    pass


@audit_group.command(name="verify")
def verify_audit():
    """Verify cryptographic hash-chain integrity of the immutable audit log."""
    from adam.db.models import AuditEvent, compute_audit_event_hash
    session = get_session()
    events = session.query(AuditEvent).order_by(AuditEvent.sequence_num.asc()).all()

    if not events:
        click.echo("Audit log is empty. 0 records to verify.")
        session.close()
        return

    expected_prev = "0" * 64
    for i, event in enumerate(events):
        seq = event.sequence_num
        expected_seq = i + 1
        if seq != expected_seq:
            click.secho(
                f"INTEGRITY VIOLATION: Sequence break at record ID {event.id}. "
                f"Expected sequence {expected_seq}, found {seq}.",
                fg="red",
                err=True,
            )
            session.close()
            raise SystemExit(1)

        if event.prev_hash != expected_prev:
            click.secho(
                f"INTEGRITY VIOLATION: Broken hash chain at record ID {event.id} (sequence #{seq}). "
                f"Expected prev_hash {expected_prev}, found {event.prev_hash}.",
                fg="red",
                err=True,
            )
            session.close()
            raise SystemExit(1)

        ts_iso = event.timestamp.isoformat() if hasattr(event.timestamp, "isoformat") else str(event.timestamp)
        recomputed_hash = compute_audit_event_hash(
            sequence_num=event.sequence_num,
            timestamp_iso=ts_iso,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            action=event.action,
            actor=event.actor,
            details_json=event.details_json,
            prev_hash=event.prev_hash,
        )

        if event.entry_hash != recomputed_hash:
            click.secho(
                f"INTEGRITY VIOLATION: Tampered audit record at ID {event.id} (sequence #{seq}). "
                f"Stored entry_hash {event.entry_hash}, recomputed {recomputed_hash}.",
                fg="red",
                err=True,
            )
            session.close()
            raise SystemExit(1)

        expected_prev = event.entry_hash

    click.secho(
        f"Audit log integrity verified: {len(events)} cryptographically chained records checked. Zero tampering detected.",
        fg="green",
        bold=True,
    )
    session.close()
