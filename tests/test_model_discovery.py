"""Tests for local runtime discovery (adam/model/discovery.py).

Tests:
- Ollama reachable → models discovered correctly
- Ollama unavailable → empty list (no exception)
- Multiple models listed
- Model with missing fields handled gracefully
- Display name sanitisation
- run_local_discovery() integration
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from adam.model.discovery import (
    OllamaLocalProvider,
    DiscoveredModel,
    run_local_discovery,
    _sanitise_display_name,
    _pretty_model_name,
)


# ── Display name helpers ───────────────────────────────────────────────────

def test_pretty_model_name_with_tag():
    assert _pretty_model_name("qwen3:4b") == "Qwen3 4B"


def test_pretty_model_name_without_variant():
    assert _pretty_model_name("llama3") == "Llama3"


def test_sanitise_display_name_strips_control_chars():
    raw = "Good Model\x00\x01\x1f"
    result = _sanitise_display_name(raw)
    assert "\x00" not in result
    assert "Good" in result


def test_sanitise_display_name_truncates():
    raw = "A" * 200
    result = _sanitise_display_name(raw)
    assert len(result) == 80


def test_sanitise_display_name_empty():
    assert _sanitise_display_name("") == "Unknown Model"


# ── OllamaLocalProvider ────────────────────────────────────────────────────

def _mock_ollama_tags_response(models=None):
    """Return a mock httpx response for GET /api/tags."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": models or [
            {
                "name": "qwen3:4b",
                "size": 2_500_000_000,
                "modified_at": "2024-01-01T00:00:00Z",
                "details": {"parameter_size": "4.0B", "context_length": 4096},
            }
        ]
    }
    return mock_resp


def test_ollama_detect_reachable():
    provider = OllamaLocalProvider()
    with patch.object(provider, "_get_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.get.return_value = _mock_ollama_tags_response()
        mock_client_factory.return_value = mock_client
        assert provider.detect() is True


def test_ollama_detect_unreachable():
    provider = OllamaLocalProvider()
    with patch.object(provider, "_get_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.get.side_effect = ConnectionRefusedError("Connection refused")
        mock_client_factory.return_value = mock_client
        assert provider.detect() is False


def test_ollama_list_models_returns_discovered_models():
    provider = OllamaLocalProvider()
    with patch.object(provider, "_get_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.get.return_value = _mock_ollama_tags_response([
            {"name": "mistral:7b", "size": 4_100_000_000, "details": {}},
            {"name": "phi3:mini", "size": 2_200_000_000, "details": {"parameter_size": "3.8B"}},
        ])
        mock_client_factory.return_value = mock_client
        models = provider.list_models()

    assert len(models) == 2
    assert all(isinstance(m, DiscoveredModel) for m in models)
    assert models[0].model_id == "mistral:7b"
    assert models[0].provider == "ollama"
    assert models[0].status == "DISCOVERED"
    assert models[0].source == "discovered"
    assert models[1].parameter_count == "3.8B"


def test_ollama_list_models_ollama_unavailable():
    """Unavailable Ollama should return empty list, never raise."""
    provider = OllamaLocalProvider()
    with patch.object(provider, "_get_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("server offline")
        mock_client_factory.return_value = mock_client
        models = provider.list_models()

    assert models == []


def test_ollama_list_models_http_error():
    """Non-200 status returns empty list."""
    provider = OllamaLocalProvider()
    with patch.object(provider, "_get_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client.get.return_value = mock_response
        mock_client_factory.return_value = mock_client
        models = provider.list_models()

    assert models == []


def test_ollama_list_models_skips_nameless_entries():
    """Entries with empty 'name' must be skipped silently."""
    provider = OllamaLocalProvider()
    with patch.object(provider, "_get_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.get.return_value = _mock_ollama_tags_response([
            {"name": "", "size": 100},
            {"name": "valid:model", "size": 200},
        ])
        mock_client_factory.return_value = mock_client
        models = provider.list_models()

    assert len(models) == 1
    assert models[0].model_id == "valid:model"


def test_ollama_list_models_multiple():
    """Multiple installed models all appear in results."""
    provider = OllamaLocalProvider()
    tags = [{"name": f"model{i}:latest", "size": 1_000_000_000} for i in range(5)]
    with patch.object(provider, "_get_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.get.return_value = _mock_ollama_tags_response(tags)
        mock_client_factory.return_value = mock_client
        models = provider.list_models()

    assert len(models) == 5
    for i, m in enumerate(models):
        assert m.model_id == f"model{i}:latest"


def test_ollama_health_check_available():
    provider = OllamaLocalProvider()
    with patch.object(provider, "_get_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.get.return_value = _mock_ollama_tags_response()
        mock_client_factory.return_value = mock_client
        health = provider.health_check()

    assert health["available"] is True
    assert health["runtime"] == "ollama"


def test_ollama_health_check_unavailable():
    provider = OllamaLocalProvider()
    with patch.object(provider, "_get_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("offline")
        mock_client_factory.return_value = mock_client
        health = provider.health_check()

    assert health["available"] is False
    assert "error" in health


# ── run_local_discovery() integration ─────────────────────────────────────

def test_run_local_discovery_deduplicates():
    """If the same model appears from two calls, it should appear only once."""
    with patch("adam.model.discovery._LOCAL_PROVIDERS", [OllamaLocalProvider]):
        with patch.object(OllamaLocalProvider, "detect", return_value=True):
            with patch.object(OllamaLocalProvider, "list_models", return_value=[
                DiscoveredModel(
                    model_id="dup:model",
                    display_name="Dup Model",
                    provider="ollama",
                    runtime="ollama",
                )
            ]):
                result = run_local_discovery()

    model_ids = [m.model_id for m in result]
    assert model_ids.count("dup:model") == 1


def test_run_local_discovery_skips_unavailable_providers():
    """Provider that raises during detect() should be skipped gracefully."""
    with patch("adam.model.discovery._LOCAL_PROVIDERS", [OllamaLocalProvider]):
        with patch.object(OllamaLocalProvider, "detect", side_effect=RuntimeError("crash")):
            result = run_local_discovery()
    assert result == []


def test_discovered_model_to_dict():
    dm = DiscoveredModel(
        model_id="test:model",
        display_name="Test Model",
        provider="ollama",
        runtime="ollama",
        size_bytes=1_024 * 1_024 * 1_024,
    )
    d = dm.to_dict()
    assert d["model_id"] == "test:model"
    assert d["size_mb"] == pytest.approx(1024.0)
    assert d["source"] == "discovered"
    assert d["status"] == "DISCOVERED"
