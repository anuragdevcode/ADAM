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

@cli.group(name="backup")
def backup_group():
    """Backup, verification, and disaster recovery commands."""
    pass


@backup_group.command(name="create")
@click.option("--output", "-o", default=None, help="Target backup archive path (.tar.gz)")
def backup_create(output: Optional[str]):
    """Create a crash-consistent, cryptographically verified backup archive."""
    from adam.backup import create_backup
    from pathlib import Path

    out_p = Path(output) if output else None
    click.echo("Creating ADAM disaster recovery backup...")
    try:
        archive_path = create_backup(backup_path=out_p)
        click.secho(f"Backup successfully created at: {archive_path}", fg="green", bold=True)
    except Exception as e:
        click.secho(f"Backup creation failed: {e}", fg="red", err=True)
        raise SystemExit(1)


@backup_group.command(name="verify")
@click.argument("archive_path")
def backup_verify_cmd(archive_path: str):
    """Verify archive integrity, SHA256 checksums, and database header."""
    from adam.backup import verify_backup
    from pathlib import Path

    click.echo(f"Verifying backup archive: {archive_path}...")
    try:
        res = verify_backup(Path(archive_path))
        click.secho("Backup Verification: PASSED", fg="green", bold=True)
        click.echo(f"  Verified Files: {res['verified_files']}")
        click.echo("  Table Counts:")
        for tbl, cnt in res.get("table_counts", {}).items():
            click.echo(f"    {tbl:28s}: {cnt}")
    except Exception as e:
        click.secho(f"Backup verification FAILED: {e}", fg="red", err=True)
        raise SystemExit(1)


@backup_group.command(name="restore")
@click.argument("archive_path")
@click.option("--force", is_flag=True, default=False, help="Force overwrite without confirmation.")
def backup_restore_cmd(archive_path: str, force: bool):
    """Restore database, storage originals, and index aliases from backup archive."""
    from adam.backup import restore_backup
    from pathlib import Path

    if not force:
        click.confirm(
            f"Are you sure you want to restore from {archive_path}? This will overwrite active database and storage.",
            abort=True,
        )

    click.echo(f"Restoring environment from: {archive_path}...")
    try:
        res = restore_backup(Path(archive_path), force=force)
        click.secho("Disaster Recovery Restore: SUCCESS", fg="green", bold=True)
        click.echo(f"  Storage Files Restored: {res['storage_files_restored']}")
        click.echo(f"  Audit Events Intact:    {res['audit_events_count']}")
        click.echo(f"  Reconstruction Audits:  {res['reconstruction_audits_count']}")
    except Exception as e:
        click.secho(f"Disaster Recovery Restore FAILED: {e}", fg="red", err=True)
        raise SystemExit(1)


@backup_group.command(name="drill")
def backup_drill_cmd():
    """Execute an automated end-to-end disaster recovery restore drill in isolation (R6)."""
    import tempfile
    import time
    from pathlib import Path
    from adam.backup import create_backup, restore_backup, verify_backup
    from adam.db.session import get_engine
    from adam.db.models import compute_audit_event_hash
    from sqlalchemy import text

    click.secho("==================================================", bold=True)
    click.secho("EXECUTING ADAM DISASTER RECOVERY DRILL (R6)", bold=True)
    click.secho("==================================================", bold=True)

    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory() as drill_dir_str:
        drill_dir = Path(drill_dir_str)
        archive_path = drill_dir / "drill_backup.tar.gz"
        drill_storage = drill_dir / "storage"
        drill_db_path = drill_dir / "drill_adam.db"
        drill_db_url = f"sqlite:///{drill_db_path}"
        drill_source_storage = drill_dir / "src_storage"
        drill_source_storage.mkdir(parents=True, exist_ok=True)
        (drill_source_storage / "sample_go.pdf").write_bytes(b"%PDF-1.4 Official Government Order Content\n%%EOF")
        (drill_source_storage / "metadata.json").write_bytes(b'{"status": "APPROVED", "provenance": "VERIFIED"}')

        # 1. Snapshot creation
        click.echo("[1/4] Creating drill backup snapshot...")
        create_backup(backup_path=archive_path, storage_dir=drill_source_storage)

        # 2. Archive verification
        click.echo("[2/4] Cryptographically verifying backup archive...")
        verify_res = verify_backup(archive_path)
        click.echo(f"      Verified {verify_res['verified_files']} files and manifest checksums.")

        # 3. Restoration into isolated sandbox
        click.echo("[3/4] Restoring backup snapshot into isolated sandbox...")
        rest_res = restore_backup(
            archive_path=archive_path,
            target_storage_dir=drill_storage,
            target_db_url=drill_db_url,
            force=True,
        )

        # 4. Hash-chain audit trail verification on restored DB
        click.echo("[4/4] Verifying cryptographic audit chain on restored database...")
        from sqlalchemy.orm import sessionmaker
        from adam.db.models import AuditEvent
        eng = get_engine(drill_db_url)
        sess = sessionmaker(bind=eng)()
        events = sess.query(AuditEvent).order_by(AuditEvent.sequence_num.asc()).all()

        chain_ok = True
        prev = ""
        for ev in events:
            expected = compute_audit_event_hash(
                sequence_num=ev.sequence_num,
                timestamp_iso=ev.timestamp,
                entity_type=ev.entity_type,
                entity_id=ev.entity_id,
                action=ev.action,
                actor=ev.actor,
                details_json=ev.details_json,
                prev_hash=ev.prev_hash,
            )
            if ev.entry_hash != expected or (prev and ev.prev_hash != prev):
                chain_ok = False
                break
            prev = ev.entry_hash
        count_events = len(events)
        sess.close()
        eng.dispose()

        elapsed = time.perf_counter() - t0
        click.echo("-" * 50)
        if chain_ok:
            click.secho(f"DRILL RESULT: PASSED (RTO: {elapsed:.2f}s, Audit Records: {count_events})", fg="green", bold=True)
            click.secho("Restored environment verified consistent and tamper-evident.", fg="green")
        else:
            click.secho("DRILL RESULT: FAILED (Audit chain validation error)", fg="red", bold=True)
            raise SystemExit(1)
        click.secho("==================================================", bold=True)
