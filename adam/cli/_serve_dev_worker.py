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

@cli.command(name="serve")
@click.option("--host", default="0.0.0.0", show_default=True, help="Host to bind the API server.")
@click.option("--port", default=8000, show_default=True, type=int, help="Port to bind the API server.")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload for development.")
def serve(host: str, port: int, reload: bool):
    """Start the ADAM FastAPI server (text chat + voice interface).

    Serves the REST/SSE API consumed by the Next.js web UI.
    The UI at ui/ connects to this server on the configured port.
    """
    try:
        import uvicorn
    except ImportError:
        click.echo("[ERROR] uvicorn is not installed. Run: pip install uvicorn[standard]", err=True)
        raise SystemExit(1)

    click.echo(f"Starting ADAM API server on http://{host}:{port}")
    click.echo(f"API docs: http://localhost:{port}/docs")
    click.echo("Web UI: start separately with: cd ui && npm run dev")
    uvicorn.run("adam.api.app:app", host=host, port=port, reload=reload)


# ── Phase 08: Native Local Development & Diagnostics ────────────────────────


@cli.group(name="dev")
def dev_group():
    """Native local development diagnostics, bootstrap, and cache governance."""
    pass


@dev_group.command(name="doctor")
def dev_doctor():
    """Run local environment health and hardware resource diagnostics."""
    from adam.dev import run_doctor

    click.echo("Running ADAM Local Development Environment Diagnostics...\n")
    report = run_doctor()

    status_color = "green" if report["status"] == "HEALTHY" else ("yellow" if report["status"] == "WARNING" else "red")
    click.secho(f"System Status: {report['status']} (Profile: {report['profile']})", fg=status_color, bold=True)
    click.echo("-" * 65)

    mem = report["memory"]
    click.echo("Unified Memory (RAM):")
    click.echo(f"  Total RAM:         {mem['total_ram_gb']} GB")
    click.echo(f"  Available RAM:     {mem['available_ram_gb']} GB")
    click.echo(f"  macOS Headroom:    {mem['macos_headroom_gb']} GB required (Met: {mem['headroom_met']})")

    disk = report["disk"]
    click.echo("\nStorage & Cache:")
    click.echo(f"  Storage Directory: {disk['storage_dir']}")
    click.echo(f"  Free Disk Space:   {disk['free_space_gb']} GB")
    click.echo(f"  Current Cache:     {disk['storage_cache_mb']} MB / {disk['cache_ceiling_mb']} MB (Within Ceiling: {disk['within_ceiling']})")

    db = report["database"]
    click.echo("\nDatabase Connection:")
    click.echo(f"  URL:               {db['url']}")
    click.echo(f"  Connected:         {db['connected']}")
    if db.get("counts"):
        click.echo(f"  Records:           {db['counts'].get('sources', 0)} sources, {db['counts'].get('documents', 0)} docs, {db['counts'].get('chunks', 0)} chunks")

    eng = report["engines"]
    click.echo("\nProcessing & Model Engines:")
    click.echo(f"  OCR Engine:        {eng['ocr_engine']} (Tesseract binary present: {eng['tesseract_binary_present']})")
    click.echo(f"  STT Engine:        {eng['stt_engine']}")
    click.echo(f"  TTS Engine:        {eng['tts_engine']}")

    conc = report["concurrency"]
    click.echo("\nConcurrency & Process Locks:")
    click.echo(f"  Heavy Worker Lock: {'LOCKED (' + str(conc['active_task']) + ')' if conc['lock_engaged'] else 'READY / UNLOCKED'}")
    click.echo("-" * 65)


@dev_group.command(name="bootstrap")
@click.option("--force", is_flag=True, default=False, help="Force re-seeding even if records exist.")
def dev_bootstrap(force: bool):
    """Bootstrap an anonymized mini public pilot corpus in SQLite in under 2 seconds."""
    from adam.bootstrap import bootstrap_mini_corpus
    from adam.db.session import get_session

    session = get_session()
    click.echo("Bootstrapping mini public pilot corpus for Uttarakhand records...")
    res = bootstrap_mini_corpus(session, force=force)
    session.close()

    click.secho(f"{res['message']} (took {res['duration_ms']}ms)", fg="green", bold=True)


@dev_group.command(name="cache-clean")
@click.option("--cap-mb", default=2048.0, type=float, show_default=True, help="Storage ceiling cap in MB.")
@click.option("--dry-run", is_flag=True, default=False, help="Report without deleting files.")
def dev_cache_clean(cap_mb: float, dry_run: bool):
    """Enforce disk cache ceiling by pruning temporary unpinned files."""
    from adam.dev import clean_cache

    click.echo(f"Cleaning storage cache against ceiling: {cap_mb} MB (Dry run: {dry_run})...")
    res = clean_cache(cap_mb=cap_mb, dry_run=dry_run)
    click.echo(
        f"Cache Size: {res['current_size_mb']} MB | Pruned: {res['pruned_files']} files | Freed: {res['freed_mb']} MB"
    )


@dev_group.command(name="profile")
@click.option("--name", default="macbook-8gb", type=click.Choice(["macbook-8gb", "dev-server", "gov-prod"]))
def dev_profile(name: str):
    """Display resource constraints and execution bounds for hardware environment profile."""
    from adam.agent.budget import MACBOOK_AIR_8GB_PROFILE, DEV_SERVER_PROFILE, GOV_PRODUCTION_PROFILE

    profiles = {
        "macbook-8gb": MACBOOK_AIR_8GB_PROFILE,
        "dev-server": DEV_SERVER_PROFILE,
        "gov-prod": GOV_PRODUCTION_PROFILE,
    }
    prof = profiles[name]
    click.secho(f"Profile: {prof.profile_type} — {prof.description}", bold=True)
    click.echo(f"  RAM Total:               {prof.ram_total_gb} GB")
    click.echo(f"  macOS Headroom:          {prof.macos_headroom_gb} GB")
    click.echo(f"  Max Context Window:      {prof.max_context_window} tokens")
    click.echo(f"  Max Active Requests:     {prof.max_active_requests}")
    click.echo(f"  Disk Cache Ceiling:      {prof.disk_cache_ceiling_gb} GB")
    click.echo(f"  Heavy Worker Exclusion:  {prof.enforce_heavy_worker_mutual_exclusion}")


@cli.group(name="worker")
def worker_group():
    """Background queue worker processes."""
    pass


@worker_group.command(name="ocr")
def worker_ocr():
    """Run native isolated OCR queue worker with mutual exclusion locking."""
    from adam.agent.coordinator import HeavyWorkerCoordinator, HeavyTaskType
    from adam.db.session import get_session
    from adam.extract.pipeline import DocumentExtractionPipeline
    from adam.storage.base import get_storage_backend

    coordinator = HeavyWorkerCoordinator()
    click.echo("Starting native OCR worker with heavy worker mutual exclusion...")

    with coordinator.acquire_worker(HeavyTaskType.OCR_PROCESSING, task_id="cli_ocr_worker"):
        session = get_session()
        storage = get_storage_backend()
        pipeline = DocumentExtractionPipeline(session, storage)
        click.echo("OCR Worker active. Processing pending document versions...")
        processed = pipeline.process_all()
        session.close()


@worker_group.command(name="run")
@click.option("--poll-interval", default=5.0, type=float, help="Polling interval in seconds.")
@click.option("--once", is_flag=True, default=False, help="Run single cycle and exit.")
def worker_run(poll_interval: float, once: bool):
    """Run unified durable background worker for OCR, ingestion, and embeddings (R5)."""
    from adam.worker.runner import UnifiedWorkerRunner

    runner = UnifiedWorkerRunner(poll_interval=poll_interval)
    if once:
        click.echo("Executing single worker processing cycle...")
        stats = runner.run_cycle()
        click.secho(f"Worker cycle finished: {stats}", fg="green", bold=True)
    else:
        click.echo(f"Starting unified background worker daemon (poll interval: {poll_interval}s)...")
        runner.run_forever()
