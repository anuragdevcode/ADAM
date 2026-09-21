"""Doc-drift safeguard tests.

Ensures that documentation in README.md and adam/config.py never drifts out of sync
with code definitions in adam.vocabularies (AgentState, AgentToolName),
adam.observability.events (OperationalEventType), and database configurations.
"""

from pathlib import Path
import inspect
from adam.config import BASE_DIR
from adam.vocabularies import AgentState, AgentToolName
from adam.observability.events import OperationalEventType


def _get_readme_text() -> str:
    readme_path = BASE_DIR / "README.md"
    assert readme_path.is_file(), "README.md must exist in the root repository directory"
    return readme_path.read_text(encoding="utf-8")


def _get_config_text() -> str:
    config_path = BASE_DIR / "adam" / "config.py"
    assert config_path.is_file(), "adam/config.py must exist"
    return config_path.read_text(encoding="utf-8")


# ── 1. AgentState Alignment ──────────────────────────────────────────────────

def test_readme_documents_all_agent_states():
    """All AgentState enum values must be explicitly documented in README.md."""
    readme = _get_readme_text()

    missing = []
    for state in AgentState:
        # Check both enum attribute name and string value
        if state.value not in readme and state.name not in readme:
            missing.append(state.value)

    assert not missing, (
        f"Doc drift detected! The following AgentState enum values are missing from README.md: {missing}. "
        "Update README.md to document these states."
    )


def test_state_machine_source_uses_valid_agent_states():
    """All state transitions in AgentStateMachine must strictly match AgentState."""
    from adam.agent.state_machine import AgentStateMachine

    src = inspect.getsource(AgentStateMachine)
    valid_states = {s.name for s in AgentState} | {s.value for s in AgentState}

    # Verify that the state machine references the canonical states
    for state in AgentState:
        assert f"AgentState.{state.name}" in src or f"AgentState.{state.value}" in src, (
            f"AgentStateMachine source does not reference canonical state AgentState.{state.name}"
        )


# ── 2. Whitelisted Tools Alignment ──────────────────────────────────────────

def test_readme_documents_all_whitelisted_tools():
    """All whitelisted agent tools (AgentToolName) must be documented in README.md."""
    readme = _get_readme_text()

    missing = []
    for tool in AgentToolName:
        if tool.value not in readme:
            missing.append(tool.value)

    assert not missing, (
        f"Doc drift detected! The following AgentToolName tools are missing from README.md: {missing}."
    )


# ── 3. Operational Event Taxonomy Alignment ──────────────────────────────────

def test_readme_documents_all_operational_events():
    """All OperationalEventType events must be documented in README.md taxonomy table."""
    readme = _get_readme_text()

    missing = []
    for event_type in OperationalEventType:
        if event_type.value not in readme:
            missing.append(event_type.value)

    assert not missing, (
        f"Doc drift detected! The following OperationalEventType events are missing from README.md: {missing}. "
        "Update the operational transparency taxonomy table in README.md."
    )


# ── 4. SQLite vs PostgreSQL Database Ambiguity Safeguard ─────────────────────

def test_database_environments_explicitly_documented_in_readme():
    """README.md must explicitly distinguish SQLite (native dev/test) from PostgreSQL (Docker/production)."""
    readme = _get_readme_text().lower()

    # Must mention SQLite for native/local development or test
    assert "sqlite" in readme, "README.md must explicitly mention SQLite"
    assert "native" in readme or "local development" in readme

    # Must mention PostgreSQL / pgvector for Docker / production
    assert "postgresql" in readme or "postgres" in readme, "README.md must explicitly mention PostgreSQL"
    assert "pgvector" in readme, "README.md must explicitly mention pgvector"
    assert "database_url" in readme, "README.md must document DATABASE_URL configuration"


def test_database_environments_explicitly_documented_in_config():
    """adam/config.py must explicitly document SQLite and PostgreSQL canonical roles."""
    config_text = _get_config_text()

    assert "SQLite" in config_text, "adam/config.py must document SQLite"
    assert "PostgreSQL" in config_text or "postgres" in config_text.lower(), "adam/config.py must document PostgreSQL"
    assert "DATABASE_URL" in config_text, "adam/config.py must document DATABASE_URL"
    assert "Native Local Development" in config_text or "native" in config_text.lower()
    assert "Docker Compose" in config_text or "docker" in config_text.lower()


# ── 5. Empirical RAG Benchmark Safeguard ─────────────────────────────────────

def test_readme_documents_empirical_gold_set_benchmarks():
    """README.md must document verified empirical metrics matching evaluate_gold_set."""
    readme = _get_readme_text()

    # Must document 215 queries evaluated
    assert "215" in readme, "README.md must document the 215 gold set questions evaluated"

    # Must document 97.33% citation precision
    assert "97.33%" in readme, "README.md must document 97.33% citation page precision"

    # Must document 100% recall@10
    assert "100.00%" in readme or "100.0%" in readme, "README.md must document 100% recall@10"

    # Must document 0 leaks
    assert "0 leaks" in readme, "README.md must document 0 cross-tenant/ACL leaks"

    # Must document department and language parity
    assert "Hindi" in readme and "English" in readme
    assert "Finance & Treasury" in readme
    assert "Rural Development" in readme


def test_readme_documents_rrf_vs_reranker_ablation():
    """README.md must document RRF hybrid vs FlashRank / reranker assessment."""
    readme = _get_readme_text()

    assert "FlashRank" in readme, "README.md must address FlashRank / dedicated reranker comparison"
    assert "Reciprocal Rank Fusion" in readme or "RRF" in readme, "README.md must document RRF hybrid"
    assert "6.1 ms" in readme or "6.1" in readme, "README.md must document RRF retrieval latency"


def test_benchmark_api_matches_canonical():
    """Verify that both /api/audit/benchmark and /api/system/rag-benchmark serve verified metrics."""
    from fastapi.testclient import TestClient
    from adam.api.app import app
    from adam.api.routers.audit import CANONICAL_RAG_BENCHMARK

    client = TestClient(app)

    r1 = client.get("/api/audit/benchmark")
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1["total_queries"] == 215
    assert data1["citation_page_precision"] == 0.9733
    assert data1["recall_at_10"] == 1.0
    assert data1["gate_passed"] is True

    r2 = client.get("/api/system/rag-benchmark")
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["total_queries"] == 215
    assert "reranker_ablation" in data2

