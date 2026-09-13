"""Comprehensive tests for Gemini cloud model runtime, Gemini voice STT/TTS, and API key security."""

import base64
import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from adam.api.app import create_app
from adam.model.gemini import GeminiModelRuntime
from adam.model.registry import GEMINI_3_6_FLASH, GEMINI_2_0_FLASH, GEMINI_1_5_FLASH, ModelRegistry
from adam.model.runtime import SingleModelLifecycleManager, TemperatureOutOfBoundsError
from adam.api.voice.stt import GeminiSttEngine, get_stt_engine
from adam.api.voice.tts import GeminiTtsEngine, get_tts_engine


@pytest.fixture()
def client():
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


# ── 1. Gemini Model Runtime & Temperature Constraints ────────────────────────

def test_gemini_runtime_init_and_temperature_bounds():
    """Verify GeminiModelRuntime adheres to Phase 04 temperature constraints [0.0, 0.2] and resolves aliases."""
    # Canonical gemini-3.6-flash
    runtime_36 = GeminiModelRuntime(GEMINI_3_6_FLASH, api_key="AIzaSyDummyKeyForTesting")
    assert runtime_36.is_available() is True
    assert runtime_36.model_name == "gemini-3.6-flash"

    # Legacy gemini-2.0-flash alias automatically maps to gemini-3.6-flash
    runtime_20 = GeminiModelRuntime(GEMINI_2_0_FLASH, api_key="AIzaSyDummyKeyForTesting")
    assert runtime_20.is_available() is True
    assert runtime_20.model_name == "gemini-3.6-flash"

    # Valid temperatures
    assert runtime_36.validate_temperature(0.0) == 0.0
    assert runtime_36.validate_temperature(0.15) == 0.15

    # Out of bounds temperatures
    with pytest.raises(TemperatureOutOfBoundsError):
        runtime_36.validate_temperature(0.7)

    with pytest.raises(TemperatureOutOfBoundsError):
        runtime_36.validate_temperature(-0.1)


def test_gemini_runtime_generation_mock():
    """Verify GeminiModelRuntime executes properly and parses candidate responses."""
    runtime = GeminiModelRuntime(GEMINI_3_6_FLASH, api_key="AIzaSyDummyKeyForTesting")

    mock_resp_data = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Under Government Order UK/FIN/2023/101, procurement limit is Rs. 50 Lakhs."}],
                    "role": "model",
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 35,
            "candidatesTokenCount": 18,
        },
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_resp_data

    with patch("httpx.Client.post", return_value=mock_resp):
        res = runtime.generate(user_prompt="What is the procurement limit?")
        assert "50 Lakhs" in res.answer
        assert res.model_id == "gemini-3.6-flash"
        assert res.tokens_prompt == 35
        assert res.tokens_completion == 18
        assert res.finish_reason == "stop"


def test_gemini_runtime_fallback_on_404():
    """Verify GeminiModelRuntime automatically falls back to gemini-1.5-flash when primary returns 404."""
    runtime = GeminiModelRuntime(GEMINI_3_6_FLASH, api_key="AIzaSyDummyKeyForTesting")

    resp_404 = MagicMock()
    resp_404.status_code = 404
    resp_404.text = json.dumps({"error": {"code": 404, "message": "Model not available"}})

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Fallback response from Gemini 1.5 Flash."}],
                    "role": "model",
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 10},
    }

    # First call returns 404, second call (fallback) returns 200
    with patch("httpx.Client.post", side_effect=[resp_404, resp_200]):
        res = runtime.generate(user_prompt="Hello")
        assert "Fallback response from Gemini 1.5 Flash." in res.answer
        assert runtime.model_name == "gemini-1.5-flash"



def test_gemini_runtime_redacts_api_key_on_error():
    """Verify the raw API key never leaks into exceptions or log messages on failure."""
    secret_key = "AIzaSySuperSecretSecretKey12345"
    runtime = GeminiModelRuntime(GEMINI_3_6_FLASH, api_key=secret_key)

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = f"API error for key={secret_key}: PermissionDenied"

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(RuntimeError) as exc_info:
            runtime.generate(user_prompt="Hello")
        
        err_str = str(exc_info.value)
        assert secret_key not in err_str
        assert "[REDACTED_GEMINI_KEY]" in err_str


# ── 2. Gemini STT & TTS Voice Engines ─────────────────────────────────────────

def test_gemini_stt_engine_transcription():
    """Verify GeminiSttEngine sends multimodal audio and parses transcript."""
    stt = GeminiSttEngine(api_key="AIzaSyTestKey")
    assert stt.is_available() is True

    mock_resp_data = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "प्रिय महोदय, उत्तराखण्ड शासन का शासनादेश दिखाइए।"}],
                }
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_resp_data

    with patch("httpx.Client.post", return_value=mock_resp):
        dummy_audio = b"\x1a\x45\xdf\xa3" + b"\x00" * 64
        res = stt.transcribe(dummy_audio, language_hint="hi")
        assert "उत्तराखण्ड शासन" in res.transcript
        assert res.confidence == 0.95


def test_gemini_tts_engine_synthesis():
    """Verify GeminiTtsEngine receives audio data and returns valid WAV format."""
    tts = GeminiTtsEngine(api_key="AIzaSyTestKey")
    assert tts.is_available() is True

    raw_pcm = b"\x00\x01\x02\x03" * 20
    b64_pcm = base64.b64encode(raw_pcm).decode("utf-8")

    mock_resp_data = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": "audio/pcm",
                                "data": b64_pcm,
                            }
                        }
                    ]
                }
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_resp_data

    with patch("httpx.Client.post", return_value=mock_resp):
        audio_bytes = tts.synthesize("Dearness allowance is 50 percent.", language="en")
        assert len(audio_bytes) >= 44
        assert audio_bytes[:4] == b"RIFF"
        assert audio_bytes[8:12] == b"WAVE"


# ── 3. API Endpoints & Key Validation ─────────────────────────────────────────

def test_system_validate_gemini_key_endpoint_success(client):
    """Verify POST /api/system/validate-gemini-key validates active keys."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [{"name": "models/gemini-3.6-flash"}, {"name": "models/gemini-1.5-flash"}]
    }

    with patch("httpx.Client.get", return_value=mock_resp):
        resp = client.post("/api/system/validate-gemini-key", json={"api_key": "valid_test_key"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert "verified successfully" in data["message"]
        assert "gemini-3.6-flash" in data["available_models"]


def test_system_validate_gemini_key_endpoint_failure(client):
    """Verify POST /api/system/validate-gemini-key reports invalid keys without crashing."""
    mock_resp = MagicMock()
    mock_resp.status_code = 400

    with patch("httpx.Client.get", return_value=mock_resp):
        resp = client.post("/api/system/validate-gemini-key", json={"api_key": "bad_key"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "Invalid API key" in data["message"]


def test_system_models_shows_gemini_with_key(client):
    """Verify GET /api/system/models marks Gemini models installed when key header is present and only exposes gemini-3.6-flash."""
    resp = client.get("/api/system/models", headers={"X-Gemini-Api-Key": "test_header_key"})
    assert resp.status_code == 200
    models = resp.json()
    gemini_ids = [m["id"] for m in models if "gemini" in m["id"]]
    assert gemini_ids == ["gemini-3.6-flash"]
    gemini_m = next((m for m in models if m["id"] == "gemini-3.6-flash"), None)
    assert gemini_m is not None
    assert gemini_m["is_cloud"] is True
    assert gemini_m["is_installed"] is True
    assert gemini_m["is_supported"] is True


def test_system_models_marks_gemini_uninstalled_without_key(client):
    """Verify GET /api/system/models marks Gemini models needing key when absent."""
    with patch.dict("os.environ", {}, clear=True):
        resp = client.get("/api/system/models")
        assert resp.status_code == 200
        models = resp.json()
        gemini_m = next((m for m in models if m["id"] == "gemini-3.6-flash"), None)
        assert gemini_m is not None
        assert gemini_m["is_installed"] is False
        assert "Requires Google Gemini API key" in gemini_m["unavailable_reason"]


def test_chat_endpoint_with_gemini_model_and_header(client):
    """Verify POST /api/chat dispatches properly to Gemini model with key header."""
    mock_gen_result = MagicMock()
    mock_gen_result.answer = "Hello from Google Gemini in Uttarakhand Public Records!"
    mock_gen_result.tokens_prompt = 20
    mock_gen_result.tokens_completion = 10
    mock_gen_result.model_id = "gemini-3.6-flash"
    mock_gen_result.latency_ms = 150.0
    mock_gen_result.finish_reason = "stop"
    mock_gen_result.is_refusal = False
    mock_gen_result.refusal_category = None

    with patch.object(GeminiModelRuntime, "generate", return_value=mock_gen_result):
        resp = client.post(
            "/api/chat",
            json={"query": "Hello", "model_id": "gemini-3.6-flash"},
            headers={"X-Gemini-Api-Key": "test_key_123"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "gemini-3.6-flash" in resp.text
