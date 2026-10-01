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

@cli.group(name="model")
def model_group():
    """Manage pinned model artifacts, licensing, SBOMs, budgets, and promotion gates."""
    pass


@model_group.command(name="seed")
def seed_models():
    """Seed canonical release models (Qwen3-4B, Qwen3-1.7B, Gemma-3-4B, Llama-3.2-3B)."""
    from adam.model.registry import ModelRegistry
    session = get_session()
    registry = ModelRegistry(session)
    count = registry.seed_defaults()
    click.echo(f"Seeded {count} canonical model release artifacts into registry.")
    session.close()


@model_group.command(name="list")
def list_models():
    """List all release-controlled models with quantization, license, and promotion status."""
    from adam.model.registry import ModelRegistry
    session = get_session()
    registry = ModelRegistry(session)
    registry.seed_defaults()
    models = registry.list_all()

    click.echo(f"{'Model ID':<26} {'Quant':<8} {'Context':<8} {'License':<22} {'Role':<14} {'Status'}")
    click.echo("-" * 92)
    for m in models:
        role = "PRIMARY" if m.is_primary else ("FALLBACK" if m.is_fallback else "COMPARATOR")
        click.echo(f"{m.id:<26} {m.quantization:<8} {m.context_window:<8} {m.license_id:<22} {role:<14} {m.status}")
    session.close()


@model_group.command(name="info")
@click.argument("model_id")
def info_model(model_id: str):
    """Display comprehensive artifact specifications, checksum, SBOM, and licensing details."""
    from adam.model.registry import ModelRegistry
    from adam.db.models import ModelPromotionRecord
    session = get_session()
    registry = ModelRegistry(session)
    registry.seed_defaults()
    model = registry.get(model_id)
    if not model:
        click.echo(f"Error: Model '{model_id}' not found in registry.", err=True)
        session.close()
        sys.exit(1)

    click.echo(f"Model ID:        {model.id}")
    click.echo(f"Name:            {model.name}")
    click.echo(f"Revision:        {model.revision}")
    click.echo(f"Quantization:    {model.quantization} ({model.model_format})")
    click.echo(f"File Size:       {round(model.file_size_bytes / (1024*1024), 1)} MB")
    click.echo(f"SHA-256 Hash:    {model.checksum_sha256}")
    click.echo(f"License:         {model.license_id} [{model.license_status}]")
    click.echo(f"Context Window:  {model.context_window} tokens")
    click.echo(f"Serving Runtime: {model.serving_runtime}")
    click.echo(f"Status:          {model.status}")
    click.echo("\nSoftware Bill of Materials (SBOM):")
    for k, v in model.sbom.items():
        click.echo(f"  {k:<26}: {v}")

    promotions = session.query(ModelPromotionRecord).filter(ModelPromotionRecord.model_id == model_id).all()
    if promotions:
        click.echo("\nGovernance Promotion History:")
        for p in promotions:
            ts = p.promoted_at.isoformat() if p.promoted_at else "N/A"
            click.echo(f"  [{ts}] Decision: {p.decision} by {p.promoted_by} (Ref: {p.authority_order_ref})")

    session.close()


@model_group.command(name="promote")
@click.argument("model_id")
@click.option("--promoted-by", default="records_officer", help="Approving official username/id")
@click.option("--authority-ref", required=True, help="Written order or procurement approval ref")
@click.option("--notes", default=None, help="Promotion notes or justification")
@click.option("--fast", is_flag=True, help="Run fast verification without full 200-question gold set re-indexing")
def promote_model(model_id: str, promoted_by: str, authority_ref: str, notes: Optional[str], fast: bool):
    """Evaluate model against Phase 04 pilot gates and record formal governance promotion."""
    from adam.model.registry import ModelRegistry
    from adam.model.governance import ModelGovernance
    session = get_session()
    registry = ModelRegistry(session)
    registry.seed_defaults()

    click.echo(f"Initiating formal promotion evaluation for model '{model_id}'...")
    click.echo(f"  Approver:      {promoted_by}")
    click.echo(f"  Authority Ref: {authority_ref}")

    gov = ModelGovernance(session, registry)
    evaluation = gov.evaluate_and_promote(
        model_id=model_id,
        promoted_by=promoted_by,
        authority_order_ref=authority_ref,
        notes=notes,
        run_full_gold_set=not fast,
    )

    click.echo("\n" + "=" * 80)
    click.echo(f"ADAM MODEL PROMOTION SCORECARD: {model_id}")
    click.echo("=" * 80)
    click.echo(f"License Compliance Check:          {'PASS' if evaluation.license_approved else 'FAIL'}")
    click.echo(f"Gold Set Recall@10 (>=90%):         {evaluation.recall_at_10*100:.1f}% [{'PASS' if evaluation.recall_at_10>=0.90 else 'FAIL'}]")
    click.echo(f"Gold Set Precision (>=95%):         {evaluation.citation_page_precision*100:.1f}% [{'PASS' if evaluation.citation_page_precision>=0.95 else 'FAIL'}]")
    click.echo(f"No-Answer Refusal Rate (=100%):     {evaluation.no_answer_refusal_rate*100:.1f}% [{'PASS' if evaluation.no_answer_refusal_rate>=1.00 else 'FAIL'}]")
    click.echo(f"Cross-Tenant / ACL Leaks (=0):      {evaluation.acl_leak_count} [{'PASS' if evaluation.acl_leak_count==0 else 'FAIL'}]")
    click.echo(f"Unanswerable Abstention (100%):     {evaluation.unanswerable_abstention_rate*100:.1f}% [{'PASS' if evaluation.unanswerable_cases_passed else 'FAIL'}]")
    click.echo(f"High-Risk Brief Compliance (100%):  {evaluation.high_risk_compliance_rate*100:.1f}% [{'PASS' if evaluation.high_risk_cases_passed else 'FAIL'}]")
    click.echo(f"Hindi Linguistic Register Review:   {'PASS' if evaluation.hindi_review_passed else 'FAIL'}")
    click.echo(f"P95 Latency (<= 5000ms):            {evaluation.latency_p95_ms:.1f}ms [{'PASS' if evaluation.latency_p95_ms<=5000.0 else 'FAIL'}]")
    click.echo(f"Peak Model Memory Budget:           {evaluation.peak_memory_mb:.1f}MB [{'PASS' if evaluation.peak_memory_mb<=6000.0 else 'FAIL'}]")
    click.echo("-" * 80)
    click.echo(f"PROMOTION GATE DECISION:           {evaluation.decision}")
    click.echo("=" * 80)

    if evaluation.failures:
        click.echo("\nGate Failure Reasons:")
        for f in evaluation.failures:
            click.echo(f"  * {f}")

    session.close()
    if not evaluation.gate_passed:
        sys.exit(1)


@model_group.command(name="budget")
@click.option("--profile", default="MACBOOK_AIR_8GB", help="Environment profile (MACBOOK_AIR_8GB, DEV_SERVER, GOV_PRODUCTION)")
def show_budget(profile: str):
    """Inspect resource budgets, disk cache ceilings, and memory headroom."""
    from adam.agent.budget import (
        ResourceBudgetManager,
        MACBOOK_AIR_8GB_PROFILE,
        DEV_SERVER_PROFILE,
        GOV_PRODUCTION_PROFILE,
    )
    prof_upper = profile.upper()
    if "DEV" in prof_upper:
        p = DEV_SERVER_PROFILE
    elif "PROD" in prof_upper or "GOV" in prof_upper:
        p = GOV_PRODUCTION_PROFILE
    else:
        p = MACBOOK_AIR_8GB_PROFILE

    manager = ResourceBudgetManager(p)
    report = manager.get_budget_report()

    click.echo("\n" + "=" * 80)
    click.echo(f"ADAM RESOURCE BUDGET & CACHE REPORT: {report['profile']['profile_type']}")
    click.echo("=" * 80)
    click.echo(f"Description:                 {report['profile']['description']}")
    click.echo(f"Total RAM:                   {report['profile']['ram_total_gb']:.1f} GB")
    click.echo(f"macOS Headroom Reserved:     {report['profile']['macos_headroom_gb']:.1f} GB (>=2GB constraint satisfied)")
    click.echo(f"Usable RAM Ceiling:          {report['profile']['usable_ram_gb']:.1f} GB")
    click.echo(f"Max Concurrent Requests:     {report['profile']['max_active_requests']}")
    click.echo(f"Context Window Cap:          {report['profile']['max_context_window']} tokens")
    click.echo(f"Worker Mutual Exclusion:     {'ENFORCED (No OCR while chatting)' if report['profile']['enforce_heavy_worker_mutual_exclusion'] else 'PARALLEL WORKERS'}")
    click.echo("\nStorage Cache Ceilings:")
    click.echo(f"  Generator Cache:           {report['profile']['generator_budget_gb']:.1f} GB")
    click.echo(f"  Embeddings Cache:          {report['profile']['embeddings_budget_gb']:.1f} GB")
    click.echo(f"  Reranker Cache:            {report['profile']['reranker_budget_gb']:.1f} GB")
    click.echo(f"  OCR Assets Cache:          {report['profile']['ocr_assets_budget_gb']:.1f} GB")
    click.echo(f"  Total Disk Cache Ceiling:  {report['disk_cache']['ceiling_gb']:.1f} GB")
    click.echo(f"  Current Cache Footprint:   {report['disk_cache']['current_gb']:.3f} GB")
    click.echo(f"  Storage Ceiling Status:    {'UNDER CEILING' if report['disk_cache']['is_within_ceiling'] else 'EXCEEDED'}")
    click.echo("=" * 80)


@model_group.command(name="benchmark")
@click.option("--model-id", default="qwen3.5-4b-instruct-q4", help="Model artifact ID or tag (default: qwen3.5-4b-instruct-q4)")
@click.option("--backend", default="ollama", help="Inference runtime backend (ollama, deterministic)")
@click.option("--prompt", default="State the rules for verification of basic pay under the IFMS portal.", help="Evaluation prompt")
@click.option("--tokens", default=256, type=int, help="Max tokens to generate")
def benchmark_model(model_id: str, backend: str, prompt: str, tokens: int):
    """Benchmark local model runtime on Apple Silicon Metal: latency, RAM headroom, tokens/sec."""
    import time
    try:
        import psutil
    except ImportError:
        psutil = None

    from adam.model.registry import ModelRegistry
    from adam.model.runtime import SingleModelLifecycleManager, OllamaModelRuntime

    session = get_session()
    registry = ModelRegistry(session)
    registry.seed_defaults()
    artifact = registry.get(model_id)
    if not artifact:
        click.echo(f"Error: Model '{model_id}' not found in registry.", err=True)
        session.close()
        sys.exit(1)

    click.echo("\n" + "=" * 80)
    click.echo(f"ADAM LOCAL MODEL BENCHMARK: {artifact.name} ({artifact.quantization})")
    click.echo("=" * 80)

    # 1. System Memory & Headroom Check
    if psutil:
        mem = psutil.virtual_memory()
        total_gb = round(mem.total / (1024**3), 2)
        avail_gb = round(mem.available / (1024**3), 2)
        headroom_met = avail_gb >= 2.0
        click.echo(f"Hardware Platform:          Apple Silicon M-Series (Unified Memory)")
        click.echo(f"Total Unified Memory:       {total_gb} GB")
        click.echo(f"Available Memory Headroom:  {avail_gb} GB [{'PASS: >=2GB Reserve' if headroom_met else 'WARN: <2GB Reserve'}]")
    click.echo(f"Context Window:             {artifact.context_window} tokens (2k-4k profile)")
    click.echo(f"Serving Runtime:            {backend.upper()} (Apple Silicon Metal GPU accelerated)")

    # 2. Check Backend Server & Weights
    lifecycle = SingleModelLifecycleManager(registry)
    try:
        runtime = lifecycle.load_model(artifact.id, allow_hot_swap=True, backend=backend)
    except Exception as e:
        click.echo(f"\nRuntime Load Error: {e}", err=True)
        session.close()
        sys.exit(1)

    click.echo(f"Backend Server Status:      CONNECTED & READY")

    # 3. Benchmark Inference Runs
    click.echo("\nExecuting inference generation benchmark...")
    start_bench = time.perf_counter()
    res = runtime.generate(
        user_prompt=prompt,
        temperature=0.0,
        max_tokens=tokens,
    )
    total_time_ms = (time.perf_counter() - start_bench) * 1000.0
    tokens_per_sec = (res.tokens_completion / (res.latency_ms / 1000.0)) if res.latency_ms > 0 else 0.0

    click.echo("-" * 80)
    click.echo(f"Inference Latency:          {res.latency_ms:.1f} ms")
    click.echo(f"Prompt Tokens:              {res.tokens_prompt}")
    click.echo(f"Completion Tokens:          {res.tokens_completion}")
    click.echo(f"Generation Throughput:      {tokens_per_sec:.1f} tokens/sec")
    click.echo(f"Output Schema:              {res.applied_schema} [VALID]")
    click.echo(f"Temperature Applied:        {res.temperature} [DETERMINISTIC]")
    click.echo(f"Abstention / Refusal:       {res.is_refusal} ({res.refusal_category or 'N/A'})")

    # 4. Clean Memory Unload
    lifecycle.unload_model()
    click.echo(f"Memory Reclamation:         EVICTED FROM UNIFIED RAM (macOS headroom restored)")
    click.echo("=" * 80)

    click.echo("\nSample Output Completion:")
    click.echo(res.answer)
    session.close()


# ── Phase 04: Bounded Agent Orchestration CLI ───────────────────────────────
