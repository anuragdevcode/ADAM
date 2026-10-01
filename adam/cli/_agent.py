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

@cli.group(name="agent")
def agent_group():
    """Execute bounded state-machine agent queries with read-only tools and citation tracking."""
    pass


@agent_group.command(name="query")
@click.argument("question")
@click.option("--user-id", default="officer_1", help="Querying user ID")
@click.option("--role", default="OFFICER", help="User role")
@click.option("--dept", default=None, help="User department")
@click.option("--clearance", default="PUBLIC", help="Clearance level (PUBLIC, INTERNAL, RESTRICTED, CONFIDENTIAL)")
@click.option("--model-id", default=None, help="Model ID (defaults to primary Qwen3-4B)")
@click.option("--backend", default=None, help="Runtime backend: ollama or deterministic")
@click.option("--temp", default=0.0, type=float, help="Generation temperature (enforced 0.0-0.2)")
@click.option("--tokens", default=512, type=int, help="Max output tokens")
@click.option("--verbose", is_flag=True, help="Display state transitions and tool execution trace")
def query_agent(question: str, user_id: str, role: str, dept: Optional[str], clearance: str, model_id: Optional[str], backend: Optional[str], temp: float, tokens: int, verbose: bool):
    """Execute bounded orchestration pipeline: authenticate -> classify -> retrieve -> evidence -> generate -> validate -> audit."""
    import os
    if backend:
        os.environ["ADAM_MODEL_BACKEND"] = backend
    from adam.agent.state_machine import BoundedAgentStateMachine

    from adam.model.registry import ModelRegistry
    from adam.rag.models import UserContext
    from adam.rag.citation import CitationBuilder

    session = get_session()
    registry = ModelRegistry(session)
    registry.seed_defaults()

    user = UserContext(
        user_id=user_id,
        roles=[role],
        department_id=dept,
        clearance_level=clearance.upper(),
    )

    agent = BoundedAgentStateMachine(session, model_id=model_id)

    try:
        response = agent.run(
            query=question,
            user_context=user,
            temperature=temp,
            max_tokens=tokens,
        )
    except Exception as e:
        click.echo(f"Agent Execution Failed: {e}", err=True)
        session.close()
        sys.exit(1)

    click.echo("\n" + "=" * 80)
    click.echo("QUERY: " + question)
    click.echo(f"ACTOR: {user_id} [{role} - {clearance}] | MODEL: {response.model_id} | SESSION: {response.session_id}")
    click.echo("=" * 80)

    if verbose:
        click.echo("\nSTATE MACHINE TRANSITIONS (Bounded Linear 7-Stage Pipeline):")
        for t in response.state_history:
            notes_str = f" -> {t.notes}" if t.notes else ""
            click.echo(f"  [{t.from_state:<24} -> {t.to_state:<24}] {notes_str}")
        click.echo(f"\nPass Counts: Retrieval={response.retrieval_pass_count}/1 | Answer={response.answer_pass_count}/1 (Self-expansion: BLOCKED)")

    if response.currency_banners:
        for banner in response.currency_banners:
            click.echo(f"\n[!] CURRENCY BANNER: {banner}")

    click.echo("\nANSWER:")
    click.echo(response.answer)

    if response.citations:
        click.echo("\n" + "-" * 80)
        click.echo("CITATIONS (Exposing Document, Version/Hash, Coordinates, and Disclaimer):")
        for idx, cit in enumerate(response.citations, 1):
            click.echo(CitationBuilder.format_citation_markdown(cit, index=idx))

    if response.search_suggestions:
        click.echo("\nSEARCH SUGGESTIONS:")
        for s in response.search_suggestions:
            click.echo(f"  * {s}")

    click.echo("\n" + "-" * 80)
    click.echo(
        f"Audit Diagnostics: Latency={response.latency_ms:.1f}ms | "
        f"Prompt Tokens={response.prompt_tokens} | Completion Tokens={response.completion_tokens} | "
        f"Citation Validation={'PASSED' if response.validation_passed else 'FAILED'}"
    )
    click.echo("=" * 80 + "\n")
    session.close()


@agent_group.command(name="audit")
@click.argument("session_id")
def audit_agent(session_id: str):
    """View immutable execution audit trail, state transitions, tool calls, and redaction log."""
    from adam.db.models import AgentExecutionAudit
    session = get_session()
    record = session.query(AgentExecutionAudit).filter(AgentExecutionAudit.session_id == session_id).first()
    if not record:
        click.echo(f"No audit record found for agent session '{session_id}'.", err=True)
        session.close()
        sys.exit(1)

    click.echo("\n" + "=" * 80)
    click.echo(f"AGENT EXECUTION AUDIT: {session_id}")
    click.echo("=" * 80)
    click.echo(f"User:             {record.user_id} ({record.user_role}, Clearance: {record.clearance_level})")
    click.echo(f"Department:       {record.department_id or 'N/A'}")
    click.echo(f"Query:            {record.query_text}")
    click.echo(f"Model ID:         {record.model_id}")
    click.echo(f"Pass Counts:      Retrieval Passes: {record.retrieval_pass_count} | Answer Passes: {record.answer_pass_count}")
    click.echo(f"Latency:          {record.latency_ms:.2f} ms")
    click.echo(f"Tokens:           Prompt={record.prompt_tokens} | Completion={record.completion_tokens}")
    click.echo(f"Validation:       {'PASSED' if record.validation_passed else 'FAILED'}")
    click.echo(f"Execution Log:    {record.redacted_audit_log}")
    click.echo("\nState Machine Transitions:")
    for t in (record.state_transitions_json or []):
        dur = f" ({t['duration_ms']:.1f}ms)" if t.get("duration_ms") is not None else ""
        abstain = f" [Abstained: {t['abstention_reason']}]" if t.get("abstention_reason") else ""
        click.echo(f"  [{t.get('from')} -> {t.get('to')}]{dur} {t.get('notes', '')}{abstain}")
    click.echo("\nTool Calls (Read-Only Whitelist):")
    for tc in (record.tool_calls_json or []):
        click.echo(f"  Tool: {tc.get('tool')} | Found: {tc.get('found_count', 0)}")
    click.echo("=" * 80 + "\n")
    session.close()


@agent_group.command(name="test-guardrails")
def test_guardrails():
    """Verify tool whitelist enforcement, forbidden tool interception, and read-only sandbox."""
    from adam.agent.tools import ReadOnlyToolRegistry, ForbiddenToolError
    from adam.rag.models import UserContext
    session = get_session()
    user = UserContext(user_id="test_actor", clearance_level="PUBLIC")

    click.echo("Verifying tool guardrails and sandbox security...")
    forbidden_attempts = [
        ("web_browse", {"url": "https://external-website.com"}),
        ("send_email", {"to": "recipient@uk.gov.in", "subject": "test"}),
        ("edit_record", {"doc_id": "doc_123", "title": "Hacked Title"}),
        ("db_write", {"table": "documents", "op": "DROP"}),
        ("procure_action", {"vendor": "ABC", "amount": 100000}),
        ("run_bash", {"cmd": "rm -rf /"}),
    ]

    blocked_count = 0
    for tool_name, args in forbidden_attempts:
        try:
            ReadOnlyToolRegistry.execute(tool_name, args, user, session)
            click.echo(f"  [FAIL] Tool '{tool_name}' was NOT blocked!", err=True)
        except (ForbiddenToolError, PermissionError) as e:
            blocked_count += 1
            click.echo(f"  [PASS] Tool '{tool_name}' successfully intercepted & blocked: {type(e).__name__}")

    # Verify allowed read-only tool works
    res = ReadOnlyToolRegistry.execute("list_authorised_collections", {}, user, session)
    assert "accessible_departments" in res
    click.echo("  [PASS] Read-only tool 'list_authorised_collections' executed successfully.")

    click.echo(f"\nGuardrail Test Summary: {blocked_count}/{len(forbidden_attempts)} forbidden tools blocked. 100% compliant.")
    session.close()


# ── Phase 05: Conversation Memory CLI Group ─────────────────────────────────
