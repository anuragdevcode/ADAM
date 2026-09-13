"""Tests for ADAM API voice transcription and synthesis endpoints (Phase 06)."""
import io
import struct

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def test_client():
    from adam.api.app import create_app
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def _minimal_wav_bytes() -> bytes:
    """Build a minimal valid 44-byte WAV header with no audio data."""
    # RIFF header
    data_size = 0
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,    # chunk size
        b"WAVE",
        b"fmt ",
        16,                # subchunk1 size (PCM)
        1,                 # audio format (PCM)
        1,                 # num channels (mono)
        22050,             # sample rate
        44100,             # byte rate (22050 * 1 * 2)
        2,                 # block align
        16,                # bits per sample
        b"data",
        data_size,
    )
    return header


# ── STT Engine Unit Tests ─────────────────────────────────────────────────────

def test_stt_null_engine_is_always_available():
    """NullSttEngine.is_available() must always return True."""
    from adam.api.voice.stt import NullSttEngine
    engine = NullSttEngine()
    assert engine.is_available() is True


def test_stt_null_engine_returns_empty_transcript():
    """NullSttEngine.transcribe() returns empty transcript with confidence 0.0."""
    from adam.api.voice.stt import NullSttEngine
    engine = NullSttEngine()
    result = engine.transcribe(b"\x00\x01\x02\x03", language_hint="hi")
    assert result.transcript == ""
    assert result.confidence == 0.0
    assert result.language == "hi"


def test_stt_engine_factory_returns_null_when_no_whisper():
    """get_stt_engine() must return NullSttEngine when faster_whisper is not importable."""
    from unittest.mock import patch
    with patch("importlib.util.find_spec", return_value=None):
        from adam.api.voice import stt as stt_module
        engine = stt_module.get_stt_engine()
        assert isinstance(engine, stt_module.NullSttEngine)


def test_stt_faster_whisper_engine_not_available_when_not_installed():
    """FasterWhisperEngine.is_available() returns False when faster_whisper not installed."""
    import importlib.util
    if importlib.util.find_spec("faster_whisper") is not None:
        pytest.skip("faster_whisper IS installed — skipping availability=False test")
    from adam.api.voice.stt import FasterWhisperEngine
    engine = FasterWhisperEngine()
    assert engine.is_available() is False


# ── TTS Engine Unit Tests ─────────────────────────────────────────────────────

def test_tts_null_engine_is_always_available():
    """NullTtsEngine.is_available() must always return True."""
    from adam.api.voice.tts import NullTtsEngine
    engine = NullTtsEngine()
    assert engine.is_available() is True


def test_tts_null_engine_returns_valid_wav_bytes():
    """NullTtsEngine.synthesize() returns at least 44 bytes with RIFF header."""
    from adam.api.voice.tts import NullTtsEngine
    engine = NullTtsEngine()
    wav = engine.synthesize("नमस्ते", language="hi")
    assert isinstance(wav, bytes)
    assert len(wav) >= 44
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"


def test_tts_engine_factory_returns_null_when_no_piper():
    """get_tts_engine() must return NullTtsEngine when piper binary is not on PATH."""
    import shutil
    if shutil.which("piper") is not None:
        pytest.skip("piper IS installed — skipping piper-absent test")
    from adam.api.voice.tts import get_tts_engine, NullTtsEngine
    engine = get_tts_engine()
    assert isinstance(engine, NullTtsEngine)


def test_tts_piper_engine_not_available_when_not_installed():
    """PiperTtsEngine.is_available() returns False when piper binary is absent."""
    import shutil
    if shutil.which("piper") is not None:
        pytest.skip("piper IS installed")
    from adam.api.voice.tts import PiperTtsEngine
    engine = PiperTtsEngine()
    assert engine.is_available() is False


# ── HTTP Endpoint Tests ───────────────────────────────────────────────────────

def test_transcribe_endpoint_reports_fast_whisper_unavailable(test_client):
    """STT must fail visibly rather than returning an empty fallback transcript."""
    from unittest.mock import patch
    from adam.api.voice.stt import NullSttEngine

    audio_bytes = _minimal_wav_bytes()
    with patch("adam.api.routers.voice.get_stt_engine", return_value=NullSttEngine()):
        resp = test_client.post(
            "/api/voice/transcribe",
            files={"file": ("test.wav", io.BytesIO(audio_bytes), "audio/wav")},
        )
    assert resp.status_code == 503
    assert "faster-whisper" in resp.json()["error"]["message"]


def test_transcribe_endpoint_requires_file_upload(test_client):
    """POST /api/voice/transcribe without a file must return 422."""
    resp = test_client.post("/api/voice/transcribe")
    assert resp.status_code == 422


def test_synthesize_endpoint_returns_wav_bytes(test_client):
    """POST /api/voice/synthesize returns audio/wav content."""
    resp = test_client.post(
        "/api/voice/synthesize",
        json={"text": "यह एक परीक्षण है।", "language": "hi"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    # Must be at least 44 bytes (WAV header)
    assert len(resp.content) >= 44
    assert resp.content[:4] == b"RIFF"


def test_synthesize_endpoint_english_text(test_client):
    """POST /api/voice/synthesize works for English text too."""
    resp = test_client.post(
        "/api/voice/synthesize",
        json={"text": "The Dearness Allowance rate is 46 percent.", "language": "en"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"


def test_synthesize_endpoint_missing_text_returns_422(test_client):
    """POST /api/voice/synthesize without text must return 422."""
    resp = test_client.post(
        "/api/voice/synthesize",
        json={"language": "hi"},
    )
    assert resp.status_code == 422
