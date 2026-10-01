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

@cli.group(name="user")
def user_group():
    """Manage server-side user identities, roles, and clearance levels (S1)."""
    pass


@user_group.command(name="create")
@click.option("--username", required=True, help="Unique username")
@click.option("--password", required=True, help="Account password")
@click.option("--role", default="OFFICER", help="Role (ADMIN, OFFICER, RECORDS_OFFICER, REVIEWER, AUDITOR, etc.)")
@click.option("--clearance", default="PUBLIC", help="Clearance level (PUBLIC, INTERNAL, RESTRICTED, CONFIDENTIAL, ADMIN)")
@click.option("--dept", default="UNKNOWN", help="Department ID")
@click.option("--full-name", default="", help="Full name")
def create_user_cmd(username: str, password: str, role: str, clearance: str, dept: str, full_name: str):
    """Create a new user account with hashed password and server-side roles."""
    from adam.auth.service import create_user
    session = get_session()
    try:
        user = create_user(
            session,
            username=username,
            password=password,
            roles=[role],
            clearance=clearance,
            department=dept,
            full_name=full_name,
        )
        click.secho(f"User '{user.username}' created successfully (ID: {user.id}, Role: {role}, Clearance: {clearance}).", fg="green")
    except Exception as e:
        click.secho(f"Failed to create user: {e}", fg="red", err=True)
        raise SystemExit(1)
    finally:
        session.close()


@user_group.command(name="list")
def list_users_cmd():
    """List all registered user accounts and clearance levels."""
    from adam.db.models import User
    session = get_session()
    users = session.query(User).order_by(User.created_at.asc()).all()
    if not users:
        click.echo("No users registered.")
    else:
        click.echo(f"{'Username':<20} {'Roles':<25} {'Clearance':<15} {'Department':<20} {'Active':<8}")
        click.echo("-" * 90)
        for u in users:
            roles_str = ",".join(u.roles)
            click.echo(f"{u.username:<20} {roles_str:<25} {u.clearance_level:<15} {u.department_id:<20} {str(u.is_active):<8}")
    session.close()


# ── Database Migration CLI Commands (R3) ───────────────────────────────────
