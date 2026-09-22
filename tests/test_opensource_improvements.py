"""Automated test suite verifying open-source architectural improvements.

Covers:
1. Subprocess sandbox process isolation and OS timeout enforcement.
2. Pydantic v2 tool argument validation and JSON schema generation.
3. PyMuPDF native markdown table formatting and layout integration.
4. LlamaCppServerRuntime standalone inference integration.
5. Prometheus / OpenMetrics telemetry endpoint format and metrics.
6. Embedded IngestionScheduler interval and cron schedule management.
"""

from __future__ import annotations

import os
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from adam.agent.sandbox import SecurePythonSandbox, SandboxExecutionResult
from adam.agent.tools import (
    ReadOnlyToolRegistry,
    SearchToolArgs,
    ExecutePythonSandboxToolArgs,
    ForbiddenToolError,
)
from adam.api.app import create_app
from adam.extract.pdf import PdfExtractor
from adam.ingest.scheduler import IngestionScheduler, ScheduledTask
from adam.model.registry import ModelArtifact
from adam.model.runtime import (
    LlamaCppServerRuntime,
    SingleModelLifecycleManager,
    TemperatureOutOfBoundsError,
)
from adam.observability.metrics import MetricsCollector
from adam.vocabularies import AgentToolName, LicenseStatus


# ── 1. Subprocess Sandbox Tests ──────────────────────────────────────────────

def test_sandbox_subprocess_calculation():
    """Verify sandboxed calculation succeeds in an isolated subprocess."""
    code = "basic_pay = 50000\nda_rate = 0.04\nbasic_pay + (basic_pay * da_rate)"
    res = SecurePythonSandbox.execute(code, prefer_subprocess=True)
    assert res.success is True
    assert res.value == 52000.0
    assert res.error is None
    assert res.execution_time_ms > 0


def test_sandbox_subprocess_infinite_loop_timeout():
    """Verify infinite loop is forcefully killed by process timeout."""
    code = "while True:\n    pass"
    res = SecurePythonSandbox.execute(code, timeout_seconds=0.5, prefer_subprocess=True)
    assert res.success is False
    assert res.value is None
    assert "timed out" in res.error.lower()


def test_sandbox_thread_fallback_on_request():
    """Verify in-process thread execution works when prefer_subprocess=False."""
    code = "import_test = 10 * 20\nimport_test"
    res = SecurePythonSandbox.execute(code, prefer_subprocess=False)
    assert res.success is True
    assert res.value == 200


def test_sandbox_ast_validation_rejects_imports():
    """Verify forbidden imports are rejected before subprocess execution."""
    code = "import os\nos.system('echo dangerous')"
    res = SecurePythonSandbox.execute(code)
    assert res.success is False
    assert "forbidden" in res.error.lower() or "prohibited" in res.error.lower()


# ── 2. Pydantic v2 Tool Validation Tests ─────────────────────────────────────

def test_tool_pydantic_argument_validation():
    """Verify tool execution validates arguments using Pydantic models."""
    mock_user = MagicMock()
    mock_session = MagicMock()

    # Missing required query for search
    with pytest.raises(ValueError) as exc:
        ReadOnlyToolRegistry.execute(AgentToolName.SEARCH.value, {}, mock_user, mock_session)
    assert "validation" in str(exc.value).lower() or "query" in str(exc.value).lower()


def test_tool_json_schemas_generation():
    """Verify get_tool_json_schemas generates valid OpenAPI/JSON function schemas."""
    schemas = ReadOnlyToolRegistry.get_tool_json_schemas(include_extended=True)
    assert len(schemas) == 11
    schema_names = [s["function"]["name"] for s in schemas]
    assert AgentToolName.SEARCH.value in schema_names
    assert AgentToolName.EXECUTE_PYTHON_SANDBOX.value in schema_names

    search_schema = next(s for s in schemas if s["function"]["name"] == AgentToolName.SEARCH.value)
    props = search_schema["function"]["parameters"]["properties"]
    assert "query" in props
    assert "department_id" in props


# ── 3. PyMuPDF Table Extraction Tests ────────────────────────────────────────

def test_pdf_extractor_markdown_table_formatting():
    """Verify 2D table data is converted into clean GitHub Flavored Markdown."""
    headers = ["Department", "Allowance %", "Order Ref"]
    rows = [
        ["Finance", "4%", "UK/FIN/2024/101"],
        ["Personnel", "3%", "UK/GAD/2023/50"],
    ]
    md = PdfExtractor._format_markdown_table(headers, rows)
    assert "| Department | Allowance % | Order Ref |" in md
    assert "| --- | --- | --- |" in md
    assert "| Finance | 4% | UK/FIN/2024/101 |" in md


# ── 4. LlamaCppServerRuntime Tests ───────────────────────────────────────────

def test_llama_cpp_runtime_temperature_bounds():
    """Verify temperature bounds [0.0, 0.2] are strictly enforced."""
    art = ModelArtifact(
        id="qwen3-4b-instruct-q4",
        name="Qwen3 4B",
        revision="v1.0",
        quantization="Q4_K_M",
        model_format="GGUF",
        checksum_sha256="abc",
        file_size_bytes=1000,
        license_id="Apache-2.0",
        license_status=LicenseStatus.APPROVED,
        requires_legal_review=False,
        context_window=4096,
        languages=["en"],
        serving_runtime="llama_server",
        prompt_template="{prompt}",
    )
    rt = LlamaCppServerRuntime(art)

    with pytest.raises(TemperatureOutOfBoundsError):
        rt.generate(user_prompt="Hello", temperature=0.5)


def test_llama_cpp_runtime_offline_check():
    """Verify is_available() returns False when server is offline without raising."""
    art = ModelArtifact(
        id="qwen3-4b-instruct-q4",
        name="Qwen3 4B",
        revision="v1.0",
        quantization="Q4_K_M",
        model_format="GGUF",
        checksum_sha256="abc",
        file_size_bytes=1000,
        license_id="Apache-2.0",
        license_status=LicenseStatus.APPROVED,
        requires_legal_review=False,
        context_window=4096,
        languages=["en"],
        serving_runtime="llama_server",
        prompt_template="{prompt}",
    )
    rt = LlamaCppServerRuntime(art, host="http://127.0.0.1:59999")
    assert rt.is_available() is False


# ── 5. Prometheus / OpenMetrics Tests ─────────────────────────────────────────

def test_prometheus_metrics_endpoint():
    """Verify GET /api/metrics exposes standard OpenMetrics text exposition format."""
    app = create_app()
    client = TestClient(app)

    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]

    text = resp.text
    assert "adam_info" in text
    assert "adam_chat_requests_total" in text
    assert "adam_cache_entries_current" in text
    assert "adam_heavy_workers_active" in text


# ── 6. IngestionScheduler Tests ──────────────────────────────────────────────

def test_ingestion_scheduler_interval_and_cron():
    """Verify recurring interval and cron task registration and cancellation."""
    scheduler = IngestionScheduler()

    # Clear any previous tasks
    for t in scheduler.list_tasks():
        scheduler.cancel_task(t["task_id"])

    task_interval = scheduler.schedule_interval("src_ukrd_daily", interval_seconds=1800)
    assert task_interval.schedule_type == "interval"
    assert task_interval.next_run_at is not None

    task_cron = scheduler.schedule_cron("src_egazette_nightly", cron_expression="0 2 * * *")
    assert task_cron.schedule_type == "cron"
    assert task_cron.next_run_at is not None

    tasks = scheduler.list_tasks()
    assert len(tasks) == 2

    # Clean up
    scheduler.cancel_task(task_interval.task_id)
    scheduler.cancel_task(task_cron.task_id)
    assert len(scheduler.list_tasks()) == 0
