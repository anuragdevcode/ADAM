"""ADAM CLI package.

This package provides the `cli` Click group used as the entry point
(`adam = "adam.cli:cli"` in pyproject.toml). Sub-modules are organized
by functional domain to keep individual files under ~300 lines (H5).

Sub-modules (prefixed with underscore to indicate internal):
  _source          – source onboarding, approval, governance
  _ingest          – ingestion run, live crawl
  _inventory       – manifest export/verify
  _extract         – extraction, quality-report, processing-runs
  _review          – human-review queue: list/approve/correct
  _precedents      – precedent/supersession inspection
  _itda            – ITDA batch ingestion
  _rag             – RAG chunk, backfill-embeddings, query, evaluate
  _model           – model registry: seed/list/info/promote/benchmark
  _agent           – governed agent query, audit, test-guardrails
  _memory          – session memory, preferences, re-encryption
  _serve_dev_worker – serve, dev, worker sub-commands
  _eval_legacy     – legacy `adam eval` command (synthetic gold set)
  _backup          – backup create/verify/restore/drill
  _audit           – audit chain verify
  _user            – user create/list
  _db              – alembic db upgrade/downgrade/current
  _eval            – Phase 3 held-out eval group (heldout/redteam/bakeoff)
"""

import click


@click.group()
def cli() -> None:
    """ADAM: Uttarakhand Public Records Acquisition, Governance & Processing System."""


# ── Import and register all sub-groups ──────────────────────────────────────
# Each sub-module defines its group/command bound to `cli` via `@cli.group` or
# `@cli.command` decorators. Importing them triggers the registration.

from adam.cli import (  # noqa: E402, F401
    _source,
    _ingest,
    _inventory,
    _extract,
    _review,
    _precedents,
    _itda,
    _rag,
    _model,
    _agent,
    _memory,
    _serve_dev_worker,
    _eval_legacy,
    _backup,
    _audit,
    _user,
    _db,
    _eval,
)

__all__ = ["cli"]
