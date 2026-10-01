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

@cli.group(name="memory")
def memory_group():
    """Manage conversation memory sessions, encrypted turns, summaries, and user preferences."""
    pass


@memory_group.command(name="list-sessions")
@click.option("--user-id", default=None, help="Filter sessions by user ID")
def list_sessions(user_id: Optional[str]):
    """List conversation memory sessions with expiration and retention status."""
    from datetime import datetime, timezone
    from adam.db.models import ChatSession
    from adam.memory.retention import ensure_utc
    session = get_session()
    query = session.query(ChatSession)
    if user_id:
        query = query.filter(ChatSession.user_id == user_id.strip())

    sessions = query.order_by(ChatSession.created_at.desc()).all()
    if not sessions:
        click.echo("No conversation sessions found.")
        session.close()
        return

    now = datetime.now(timezone.utc)
    click.echo(f"{'Session ID':<24} {'User ID':<18} {'Ceiling':<12} {'Turns':<6} {'Status':<10} {'Expires In'}")
    click.echo("-" * 88)
    for s in sessions:
        turn_count = len(s.turns) if s.turns else 0
        is_expired = ensure_utc(s.expires_at) <= now
        status = "EXPIRED" if is_expired else "ACTIVE"
        time_left = "Expired" if is_expired else f"{int((ensure_utc(s.expires_at) - now).total_seconds() // 60)}m"
        click.echo(f"{s.id:<24} {s.user_id:<18} {s.classification_ceiling:<12} {turn_count:<6} {status:<10} {time_left}")

    session.close()


@memory_group.command(name="show-session")
@click.argument("session_id")
@click.option("--user-id", required=True, help="User ID for authorization check")
def show_session(session_id: str, user_id: str):
    """Display decrypted conversation turns and grounded summary for an authorized session."""
    from adam.memory.session import SessionManager, SessionAccessDeniedError
    from adam.memory.summary import SessionSummarizer
    session = get_session()
    manager = SessionManager(session)
    summarizer = SessionSummarizer(session)

    try:
        turns = manager.get_turns(session_id, requesting_user_id=user_id)
        summary = summarizer.get_summary(session_id, requesting_user_id=user_id)
    except SessionAccessDeniedError as e:
        click.echo(f"[ERROR] {e}", err=True)
        session.close()
        sys.exit(1)
    except KeyError as e:
        click.echo(f"[ERROR] {e}", err=True)
        session.close()
        sys.exit(1)

    click.echo(f"\n================================================================================")
    click.echo(f"SESSION DETAILS: {session_id} | USER: {user_id}")
    click.echo(f"================================================================================\n")

    click.echo("CONVERSATION TURNS:")
    for t in turns:
        cites_str = f" [Cited Chunks: {', '.join(t.cited_chunk_ids)}]" if t.cited_chunk_ids else ""
        click.echo(f"  [{t.created_at.strftime('%H:%M:%S')}] {t.role.upper()}: {t.content}{cites_str}")

    click.echo("\nGROUNDED SESSION SUMMARY:")
    if summary:
        click.echo(f"  Query Intents:     {', '.join(summary.query_intents) or 'None'}")
        click.echo(f"  Selected Filters:  {summary.selected_filters or 'None'}")
        click.echo(f"  Citations Opened:  {', '.join(summary.citations_opened) or 'None'}")
        click.echo(f"  User Corrections:  {', '.join(summary.user_corrections) or 'None'}")
        click.echo(f"  Source Turn IDs:   {', '.join(summary.source_turn_ids)}")
    else:
        click.echo("  No summary available for this session.")
    click.echo(f"\n================================================================================\n")
    session.close()


@memory_group.command(name="delete-session")
@click.argument("session_id")
@click.option("--user-id", required=True, help="User ID for authorization check")
def delete_session(session_id: str, user_id: str):
    """Explicitly delete a session and all encrypted turns, leaving a contentless audit log."""
    from adam.memory.session import SessionManager, SessionAccessDeniedError
    session = get_session()
    manager = SessionManager(session)

    try:
        manager.delete_session(session_id, requesting_user_id=user_id)
        click.echo(f"Session '{session_id}' and all associated content successfully deleted.")
    except SessionAccessDeniedError as e:
        click.echo(f"[ERROR] {e}", err=True)
        session.close()
        sys.exit(1)
    except KeyError as e:
        click.echo(f"[ERROR] {e}", err=True)
        session.close()
        sys.exit(1)

    session.close()


@memory_group.command(name="purge-expired")
def purge_expired():
    """Purge expired conversation sessions, removing encrypted content while retaining audit records."""
    from adam.memory.retention import purge_expired_sessions
    session = get_session()
    res = purge_expired_sessions(session, actor="cli_admin")
    click.echo(f"Purge complete: {res['purged_sessions']} expired session(s) and {res['purged_turns']} turn(s) purged.")
    session.close()


@memory_group.command(name="set-preference")
@click.argument("user_id")
@click.option("--purpose", required=True, help="Stated administrative purpose for storing preference")
@click.option("--data", required=True, help="JSON-formatted preference data")
@click.option("--opt-in/--no-opt-in", default=True, help="Explicit user opt-in consent")
def set_preference(user_id: str, purpose: str, data: str, opt_in: bool):
    """Store persistent user preferences with explicit opt-in and stated purpose."""
    from adam.memory.preferences import UserPreferenceManager, OptInRequiredError, PurposeLimitationError
    import json
    session = get_session()
    manager = UserPreferenceManager(session)

    try:
        parsed_data = json.loads(data)
        manager.set_preference(user_id=user_id, purpose=purpose, preferences=parsed_data, opt_in=opt_in)
        click.echo(f"Preferences successfully stored for user '{user_id}'.")
    except (json.JSONDecodeError, OptInRequiredError, PurposeLimitationError, ValueError) as e:
        click.echo(f"[ERROR] {e}", err=True)
        session.close()
        sys.exit(1)

    session.close()


@memory_group.command(name="get-preference")
@click.argument("user_id")
def get_preference(user_id: str):
    """Retrieve decrypted persistent preferences for an opted-in user."""
    from adam.memory.preferences import UserPreferenceManager
    session = get_session()
    manager = UserPreferenceManager(session)
    pref = manager.get_preference(user_id)
    if pref is None:
        click.echo(f"No active or opted-in preferences found for user '{user_id}'.")
    else:
        import json
        click.echo(json.dumps(pref, indent=2, ensure_ascii=False))
    session.close()


@memory_group.command(name="delete-preference")
@click.argument("user_id")
def delete_preference(user_id: str):
    """Permanently delete persistent preferences for a user."""
    from adam.memory.preferences import UserPreferenceManager
    session = get_session()
    manager = UserPreferenceManager(session)
    deleted = manager.delete_preference(user_id)
    if deleted:
        click.echo(f"Preferences permanently deleted for user '{user_id}'.")
    else:
        click.echo(f"No preferences found for user '{user_id}'.")
    session.close()


@memory_group.command(name="re-encrypt")
@click.option("--target-version", default=1, type=int, help="Target key version to re-encrypt records into.")
def reencrypt_memory(target_version: int):
    """Re-encrypt all stored turns, summaries, and user preferences with target key version."""
    from adam.memory.crypto import get_cipher
    from adam.db.models import ChatTurn, SessionSummary, UserPreference
    session = get_session()
    cipher = get_cipher()

    turns_count = 0
    summaries_count = 0
    prefs_count = 0

    # 1. Chat turns
    turns = session.query(ChatTurn).all()
    for t in turns:
        if t.content_ciphertext:
            t.content_ciphertext = cipher.reencrypt(t.content_ciphertext, target_version=target_version)
            turns_count += 1

    # 2. Session summaries
    summaries = session.query(SessionSummary).all()
    for s in summaries:
        if s.summary_ciphertext:
            s.summary_ciphertext = cipher.reencrypt(s.summary_ciphertext, target_version=target_version)
            summaries_count += 1

    # 3. User preferences
    prefs = session.query(UserPreference).all()
    for p in prefs:
        if p.preference_ciphertext:
            p.preference_ciphertext = cipher.reencrypt(p.preference_ciphertext, target_version=target_version)
            prefs_count += 1

    session.commit()
    session.close()
    click.echo(f"Successfully re-encrypted memory records to version {target_version}: {turns_count} turns, {summaries_count} summaries, {prefs_count} preferences.")
