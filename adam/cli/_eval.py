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

@cli.group(name="eval")
def eval_group():
    """Held-out dataset evaluation, model bake-off, and adversarial red-teaming."""
    pass


@eval_group.command(name="heldout")
@click.option("--max-queries", "-n", default=None, type=int, help="Limit number of queries to evaluate")
@click.option("--report", "-r", default="docs/benchmarks/held_out_scorecard.md", help="Output path for markdown scorecard")
@click.option("--bakeoff", is_flag=True, default=False, help="Include model bake-off matrix in report")
def eval_heldout(max_queries: Optional[int], report: str, bakeoff: bool):
    """Execute evaluation over held-out Uttarakhand corpus with Wilson 95% CIs."""
    from adam.db.session import get_session
    from adam.evaluation.held_out_runner import evaluate_held_out_dataset, generate_scorecard_markdown

    click.echo(f"Evaluating held-out Uttarakhand dataset (max_queries={max_queries or 'ALL (320)'})...")
    with get_session() as session:
        card = evaluate_held_out_dataset(session, max_queries=max_queries)

    click.secho("\n─── Pilot Gate Quality Summary ───", bold=True)
    click.echo(f"Total Queries Evaluated:    {card.total_queries_evaluated}")
    click.echo(f"Retrieval Recall@10:        {card.recall_at_10*100:.2f}% (95% CI: [{card.recall_at_10_ci['ci_lower']*100:.2f}%, {card.recall_at_10_ci['ci_upper']*100:.2f}%])")
    click.echo(f"Citation Page Precision:    {card.citation_page_precision*100:.2f}% (95% CI: [{card.citation_precision_ci['ci_lower']*100:.2f}%, {card.citation_precision_ci['ci_upper']*100:.2f}%])")
    click.echo(f"Answer Faithfulness:        {card.answer_faithfulness*100:.2f}% (95% CI: [{card.answer_faithfulness_ci['ci_lower']*100:.2f}%, {card.answer_faithfulness_ci['ci_upper']*100:.2f}%])")
    click.echo(f"Abstention Refusal Rate:    {card.no_answer_refusal_rate*100:.2f}% (95% CI: [{card.no_answer_refusal_ci['ci_lower']*100:.2f}%, {card.no_answer_refusal_ci['ci_upper']*100:.2f}%])")
    click.echo(f"Abstention Brier / ECE:     {card.abstention_brier_score:.4f} / {card.abstention_ece:.4f}")
    click.echo(f"ACL Red-Team Leaks:         {card.acl_leaks_count} / 205 probes ({card.acl_redteam_safety_rate*100:.2f}% safe)")

    status_color = "green" if card.gate_passed else "red"
    click.secho(f"\nOverall Quality Gate: {'PASSED' if card.gate_passed else 'FAILED'}", fg=status_color, bold=True)

    if report:
        generate_scorecard_markdown(card, output_file=report)
        click.secho(f"Published dynamic markdown scorecard to: {report}", fg="cyan")


@eval_group.command(name="redteam")
def eval_redteam():
    """Execute all 205 adversarial security probes against ACL boundaries."""
    from adam.db.session import get_session
    from adam.evaluation.acl_red_team import run_acl_red_team_suite
    from adam.rag.retriever import HybridRetriever

    click.echo("Running 205 adversarial ACL & clearance probes...")
    with get_session() as session:
        retriever = HybridRetriever(session=session)
        res = run_acl_red_team_suite(retriever, session)

    click.secho("\n─── ACL Red-Team Adversarial Summary ───", bold=True)
    click.echo(f"Probes Evaluated:  {res['total_probes_evaluated']}")
    click.echo(f"Probes Blocked:    {res['blocked_probes_count']}")
    click.echo(f"Probes Leaked:     {res['leaked_probes_count']}")
    click.echo(f"Safety Rate:       {res['safety_rate']*100:.2f}% (Wilson 95% CI: [{res['wilson_95_ci']['ci_lower']*100:.2f}%, {res['wilson_95_ci']['ci_upper']*100:.2f}%])")

    for cat, stats in res.get("by_attack_category", {}).items():
        click.echo(f"  - {cat:30s}: {stats['blocked']}/{stats['total']} safe ({stats['safety_rate']*100:.1f}%)")

    verdict = "green" if res["zero_leak_verified"] else "red"
    click.secho(f"\nZero-Leak Security Boundary: {'VERIFIED (0 Leaks)' if res['zero_leak_verified'] else 'FAILED'}", fg=verdict, bold=True)


@eval_group.command(name="bakeoff")
def eval_bakeoff():
    """Benchmark target models (qwen3.5:4b vs qwen3:4b vs qwen3:1.7b) on local hardware."""
    from adam.evaluation.bakeoff import CANONICAL_BAKEOFF_DATA, generate_bakeoff_markdown_table

    click.secho("\n─── Target Hardware Model Bake-Off Matrix ───", bold=True)
    table = generate_bakeoff_markdown_table(CANONICAL_BAKEOFF_DATA)
    click.echo(table)
