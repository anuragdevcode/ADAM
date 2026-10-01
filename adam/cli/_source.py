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

@cli.group(name="source")
def source_group():
    """Manage departmental source onboarding, approvals, and governance."""
    pass


@source_group.command(name="onboard")
@click.option("--id", "source_id", default=None, help="Custom unique source ID")
@click.option("--name", required=True, help="Display name of portal/source")
@click.option("--dept", "department_id", required=True, help="Department ID (controlled vocabulary)")
@click.option("--owner", "owner_name", required=True, help="Departmental owner name")
@click.option("--contact", "owner_contact", required=True, help="Departmental owner contact email/phone")
@click.option("--authority-ref", required=True, help="Written authorization reference number")
@click.option("--domains", required=True, help="Comma-separated permitted government domains")
@click.option("--paths", required=True, help="Comma-separated permitted URL path prefixes")
@click.option("--classification", default=Classification.PUBLIC.value, help="Security classification")
@click.option("--cadence", default=RefreshCadence.WEEKLY.value, help="Refresh crawl cadence")
@click.option("--rate-limit", default=30, type=int, help="Maximum requests permitted per minute")
@click.option("--retention", default="PERMANENT", help="Document retention policy")
@click.option("--actor", default="records_officer", help="User performing onboarding")
def onboard_source(
    source_id: Optional[str],
    name: str,
    department_id: str,
    owner_name: str,
    owner_contact: str,
    authority_ref: str,
    domains: str,
    paths: str,
    classification: str,
    cadence: str,
    rate_limit: int,
    retention: str,
    actor: str,
):
    """Submit a source onboarding sheet for approval."""
    engine = get_engine()
    init_db(engine)
    session = get_session(engine)

    sheet = SourceOnboardingSheet(
        id=source_id,
        name=name,
        department_id=department_id,
        owner_name=owner_name,
        owner_contact=owner_contact,
        written_authority_ref=authority_ref,
        permitted_domains=[d.strip() for d in domains.split(",") if d.strip()],
        permitted_path_prefixes=[p.strip() for p in paths.split(",") if p.strip()],
        access_classification=classification,
        refresh_cadence=cadence,
        rate_limit_per_minute=rate_limit,
        retention_policy=retention,
    )

    registry = SourceRegistry(session)
    try:
        source = registry.onboard(sheet, actor=actor)
        session.commit()
        click.echo(f"Source onboarded successfully: {source.id} [{source.status}]")
    except Exception as e:
        session.rollback()
        click.echo(f"Error onboarding source: {e}", err=True)
        sys.exit(1)
    finally:
        session.close()


@source_group.command(name="approve")
@click.argument("source_id")
@click.option("--approver", required=True, help="Authorized departmental records officer or admin")
@click.option("--notes", default=None, help="Approval notes or executive order ref")
def approve_source(source_id: str, approver: str, notes: Optional[str]):
    """Approve an onboarded or paused source for automated crawl."""
    session = get_session()
    registry = SourceRegistry(session)
    try:
        source = registry.approve(source_id, approver=approver, notes=notes)
        session.commit()
        click.echo(f"Source approved: {source.id} [Status: {source.status}] by {approver}")
    except Exception as e:
        session.rollback()
        click.echo(f"Error approving source: {e}", err=True)
        sys.exit(1)
    finally:
        session.close()


@source_group.command(name="pause")
@click.argument("source_id")
@click.option("--actor", required=True, help="User pausing the connector")
@click.option("--reason", required=True, help="Justification for pausing connector")
def pause_source(source_id: str, actor: str, reason: str):
    """Pause an active connector without deleting history."""
    session = get_session()
    registry = SourceRegistry(session)
    try:
        source = registry.pause(source_id, actor=actor, reason=reason)
        session.commit()
        click.echo(f"Source paused: {source.id} [Status: {source.status}] by {actor}")
    except Exception as e:
        session.rollback()
        click.echo(f"Error pausing source: {e}", err=True)
        sys.exit(1)
    finally:
        session.close()


@source_group.command(name="remove")
@click.argument("source_id")
@click.option("--actor", required=True, help="User removing connector")
@click.option("--reason", required=True, help="Removal justification")
def remove_source(source_id: str, actor: str, reason: str):
    """Soft-remove connector while preserving all historical audit and document records."""
    session = get_session()
    registry = SourceRegistry(session)
    try:
        source = registry.remove(source_id, actor=actor, reason=reason)
        session.commit()
        click.echo(f"Source soft-removed: {source.id} [Status: {source.status}]. Audit history preserved.")
    except Exception as e:
        session.rollback()
        click.echo(f"Error removing source: {e}", err=True)
        sys.exit(1)
    finally:
        session.close()


@source_group.command(name="list")
@click.option("--dept", default=None, help="Filter by department")
@click.option("--status", default=None, help="Filter by source status")
def list_sources(dept: Optional[str], status: Optional[str]):
    """List registered sources and their governance status."""
    session = get_session()
    registry = SourceRegistry(session)
    sources = registry.list(department_id=dept, status=status)
    if not sources:
        click.echo("No sources found matching criteria.")
        session.close()
        return

    click.echo(f"{'ID':<24} {'Status':<18} {'Dept':<22} {'Name'}")
    click.echo("-" * 80)
    for s in sources:
        click.echo(f"{s.id:<24} {s.status:<18} {s.department_id:<22} {s.name}")
    session.close()


@source_group.command(name="seed")
@click.option("--actor", default="records_officer", help="User performing seeding")
def seed_sources(actor: str):
    """Seed the initial Uttarakhand sources playbook from 01-data-acquisition.md."""
    from adam.seeds import INITIAL_SOURCES_PLAYBOOK
    engine = get_engine()
    init_db(engine)
    session = get_session(engine)
    registry = SourceRegistry(session)

    count = 0
    for sheet in INITIAL_SOURCES_PLAYBOOK:
        existing = registry.get(sheet.id)
        if not existing:
            src = registry.onboard(sheet, actor=actor)
            registry.approve(src.id, approver=actor)
            count += 1
        else:
            existing.permitted_domains = sheet.permitted_domains
            existing.permitted_path_prefixes = sheet.permitted_path_prefixes
            if existing.status != "APPROVED":
                registry.approve(existing.id, approver=actor)
            count += 1

    session.commit()
    session.close()
    click.echo(f"Seeded and updated {count} sources from initial playbook.")




@source_group.command(name="audit")
@click.argument("source_id")
def source_audit(source_id: str):
    """Display immutable audit trail for a source."""
    session = get_session()
    registry = SourceRegistry(session)
    events = registry.get_audit_history(source_id)
    if not events:
        click.echo(f"No audit events found for source '{source_id}'.")
        session.close()
        return

    click.echo(f"Audit Trail for Source: {source_id}")
    click.echo("-" * 80)
    for ev in events:
        ts = ev.timestamp.isoformat() if ev.timestamp else "N/A"
        click.echo(f"[{ts}] Action: {ev.action:<16} Actor: {ev.actor:<16}")
        if ev.details_json:
            click.echo(f"  Details: {json.dumps(ev.details_json)}")
    session.close()
