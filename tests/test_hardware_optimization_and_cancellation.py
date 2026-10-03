"""Tests for Hardware Memory Auto-Detection, Safe Context Clamping, and Streaming Cancellation."""

import asyncio
import json
import os
import threading
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from adam.config import get_safe_context_window, get_system_ram_bytes
from adam.model.registry import (
    QWEN3_5_4B_INSTRUCT,
    QWEN3_4B_INSTRUCT,
    ModelArtifact,
)
from adam.model.runtime import (
    OllamaModelRuntime,
    DeterministicModelRuntime,
    GenerationCancelledError,
    ModelGenerationResult,
)
from adam.harness.parameters import ModelInferenceParameters
from adam.api.routers.chat import _CHAT_SEMAPHORE


# ── 1. Hardware Memory Auto-Detection Tests ────────────────────────────────────

def test_system_ram_detection():
    """Verify system RAM is detected as a positive byte count."""
    ram = get_system_ram_bytes()
    assert ram is not None
    assert ram > 1 * 1024**3  # At least 1GB


def test_system_ram_detection_fallback(monkeypatch):
    """When psutil and sysconf fail, fallback returns None or handles cleanly."""
    monkeypatch.setattr("os.sysconf", lambda name: -1)
    # psutil might or might not be imported; if mocked to fail:
    with patch.dict("sys.modules", {"psutil": None}):
        with patch("subprocess.check_output", side_effect=Exception("No sysctl")):
            with patch("pathlib.Path.exists", return_value=False):
                res = get_system_ram_bytes()
                assert res is None or isinstance(res, int)


# ── 2. Safe Context Window Clamping Tests ─────────────────────────────────────

def test_get_safe_context_window_8gb_tier(monkeypatch):
    """8GB host defaults to 4096 tokens, max 8192, and clamps 256k to safe 4096."""
    monkeypatch.delenv("ADAM_CONTEXT_WINDOW", raising=False)
    monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)
    # Simulate 8GB RAM
    monkeypatch.setattr("adam.config.get_system_ram_bytes", lambda: 8 * 1024**3)

    # Default with no requested context
    assert get_safe_context_window() == 4096
    assert get_safe_context_window(None) == 4096

    # Native 256k context requested on 8GB host must be safely clamped to default 4096
    assert get_safe_context_window(262_144) == 4096

    # Explicit 8192 within max safe cap
    assert get_safe_context_window(8192) == 8192

    # Request exceeding 8GB max safe cap (e.g. 10000) is clamped to max 8192
    assert get_safe_context_window(10000) == 8192


def test_get_safe_context_window_16gb_tier(monkeypatch):
    """16GB host defaults to 8192 tokens and clamps native 256k to 8192."""
    monkeypatch.delenv("ADAM_CONTEXT_WINDOW", raising=False)
    monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)
    monkeypatch.setattr("adam.config.get_system_ram_bytes", lambda: 16 * 1024**3)

    assert get_safe_context_window() == 8192
    assert get_safe_context_window(262_144) == 8192
    assert get_safe_context_window(16384) == 16384
    assert get_safe_context_window(20000) == 16384


def test_get_safe_context_window_high_ram_tier(monkeypatch):
    """64GB+ server allows larger context windows."""
    monkeypatch.delenv("ADAM_CONTEXT_WINDOW", raising=False)
    monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)
    monkeypatch.setattr("adam.config.get_system_ram_bytes", lambda: 64 * 1024**3)

    assert get_safe_context_window() == 32768
    assert get_safe_context_window(65536) == 65536


def test_get_safe_context_window_env_overrides(monkeypatch):
    """ADAM_CONTEXT_WINDOW or OLLAMA_NUM_CTX overrides hardware detection."""
    monkeypatch.setenv("ADAM_CONTEXT_WINDOW", "6144")
    assert get_safe_context_window(262_144) == 6144

    monkeypatch.delenv("ADAM_CONTEXT_WINDOW", raising=False)
    monkeypatch.setenv("OLLAMA_NUM_CTX", "2048")
    assert get_safe_context_window() == 2048


# ── 3. Model Registry Runtime Context Window Tests ────────────────────────────

def test_qwen3_5_runtime_context_window(monkeypatch):
    """Qwen 3.5 4B keeps native 256k context specification but has safe 4096 runtime default."""
    monkeypatch.delenv("ADAM_CONTEXT_WINDOW", raising=False)
    monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)
    monkeypatch.setattr("adam.config.get_system_ram_bytes", lambda: 8 * 1024**3)

    assert QWEN3_5_4B_INSTRUCT.context_window == 262_144
    assert QWEN3_5_4B_INSTRUCT.runtime_context_window == 4096
    assert QWEN3_5_4B_INSTRUCT.get_runtime_context_window() == 4096

    d = QWEN3_5_4B_INSTRUCT.to_dict()
    assert d["context_window"] == 262_144
    assert d["runtime_context_window"] == 4096


# ── 4. Ollama Runtime Options Optimization Tests ──────────────────────────────

def test_ollama_runtime_generate_options_clamping(monkeypatch):
    """OllamaModelRuntime.generate must clamp num_ctx and optimize batch/thread/f16."""
    monkeypatch.delenv("ADAM_CONTEXT_WINDOW", raising=False)
    monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)
    monkeypatch.setattr("adam.config.get_system_ram_bytes", lambda: 8 * 1024**3)

    runtime = OllamaModelRuntime(QWEN3_5_4B_INSTRUCT)
    captured_payload = {}

    def mock_post(url, json=None, **kwargs):
        nonlocal captured_payload
        captured_payload = json
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": "Test answer from local model."},
            "prompt_eval_count": 12,
            "eval_count": 8,
        }
        return mock_resp

    mock_client = MagicMock()
    mock_client.post.side_effect = mock_post
    monkeypatch.setattr(runtime, "_get_client", lambda: mock_client)

    res = runtime.generate(user_prompt="Hello ADAM")
    assert res.answer == "Test answer from local model."

    opts = captured_payload.get("options", {})
    # Critical verification for 8GB Mac M2
    assert opts.get("num_ctx") == 4096  # Capped from 262_144 to 4,096!
    assert opts.get("num_batch") == 512
    assert opts.get("f16_kv") is True
    assert opts.get("num_thread") <= 6


def test_ollama_runtime_with_harness_parameters_clamping(monkeypatch):
    """When harness_parameters is provided, num_ctx is safely clamped for hardware."""
    monkeypatch.delenv("ADAM_CONTEXT_WINDOW", raising=False)
    monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)
    monkeypatch.setattr("adam.config.get_system_ram_bytes", lambda: 8 * 1024**3)

    runtime = OllamaModelRuntime(QWEN3_5_4B_INSTRUCT)
    captured_payload = {}

    def mock_post(url, json=None, **kwargs):
        nonlocal captured_payload
        captured_payload = json
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": "Harness answer."},
            "prompt_eval_count": 10,
            "eval_count": 5,
        }
        return mock_resp

    mock_client = MagicMock()
    mock_client.post.side_effect = mock_post
    monkeypatch.setattr(runtime, "_get_client", lambda: mock_client)

    # Pass harness parameters with unconstrained 256k context
    params = ModelInferenceParameters(context_size=262_144)
    res = runtime.generate(user_prompt="Test", harness_parameters=params)

    opts = captured_payload.get("options", {})
    assert opts.get("num_ctx") == 4096  # Clamped to safe 4096 on 8GB host
    assert opts.get("num_batch") == 512
    assert opts.get("f16_kv") is True
    assert opts.get("num_thread") <= 6


# ── 5. Backend Cancellation / Stop Query Support Tests ────────────────────────

def test_ollama_runtime_streaming_cancellation(monkeypatch):
    """When abort_event is set during streaming, OllamaModelRuntime raises GenerationCancelledError immediately."""
    runtime = OllamaModelRuntime(QWEN3_5_4B_INSTRUCT)
    abort_event = threading.Event()

    # Simulate streaming lines from Ollama
    lines = [
        json.dumps({"message": {"content": "First token "}}),
        json.dumps({"message": {"content": "second token "}}),
        json.dumps({"message": {"content": "third token "}}),
    ]

    class FakeStreamingResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

        def raise_for_status(self):
            pass

        def iter_lines(self):
            for l in lines:
                # Set abort before yielding second token
                if "second" in l:
                    abort_event.set()
                yield l

    mock_client = MagicMock()
    mock_client.stream.return_value = FakeStreamingResponse()
    monkeypatch.setattr(runtime, "_get_client", lambda: mock_client)

    tokens_received = []

    with pytest.raises(GenerationCancelledError) as exc_info:
        runtime.generate(
            user_prompt="Explain policy",
            token_callback=lambda t: tokens_received.append(t),
            abort_event=abort_event,
        )

    assert "cancelled" in str(exc_info.value).lower()
    # Only the first token was received before cancellation took effect
    assert tokens_received == ["First token "]


def test_deterministic_runtime_cancellation():
    """DeterministicModelRuntime cleanly raises GenerationCancelledError when abort_event is set."""
    runtime = DeterministicModelRuntime(QWEN3_4B_INSTRUCT)
    abort_event = threading.Event()
    abort_event.set()

    with pytest.raises(GenerationCancelledError):
        runtime.generate(user_prompt="What is DA?", abort_event=abort_event)


def test_chat_endpoint_releases_semaphore_on_abort():
    """Verify chat semaphore is released and capacity is restored upon request completion."""
    from adam.api.app import create_app
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    initial_semaphore_val = _CHAT_SEMAPHORE._value

    resp = client.post(
        "/api/chat",
        json={"query": "Test query for semaphore lifecycle"},
        headers={"X-User-Id": "officer_test", "X-User-Role": "OFFICER"},
    )
    assert resp.status_code == 200

    # Ensure semaphore was cleanly released in finally:
    assert _CHAT_SEMAPHORE._value == initial_semaphore_val


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_chat_endpoint_cancels_when_client_disconnected():
    """Verify that when request.is_disconnected() is true, generation aborts and semaphore is released."""
    from adam.api.routers.chat import chat_endpoint, ChatRequest
    from unittest.mock import AsyncMock, MagicMock
    from fastapi import Request

    initial_val = _CHAT_SEMAPHORE._value

    mock_request = AsyncMock(spec=Request)
    # Simulate client already disconnected when generator starts
    mock_request.is_disconnected.return_value = True

    req = ChatRequest(query="What is DA rate?")
    mock_db = MagicMock()
    mock_user_ctx = MagicMock()

    resp = await chat_endpoint(
        req=req,
        request=mock_request,
        db=mock_db,
        user_ctx=mock_user_ctx,
    )
    assert resp is not None

    chunks = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk)

    # Semaphore must be returned
    assert _CHAT_SEMAPHORE._value == initial_val

