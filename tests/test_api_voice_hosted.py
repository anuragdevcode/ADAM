"""Tests for hosted voice engines (Groq STT / ElevenLabs TTS), speech-text
cleanup and the /api/voice/status endpoint.  All HTTP calls are mocked."""
import io

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def test_client():
    from adam.api.app import create_app
    app = create_app()
    # A dedicated user id keeps these requests out of the anonymous
    # rate-limit bucket that the rest of the suite shares.
    return TestClient(
        app,
        raise_server_exceptions=False,
        headers={"X-User-Id": "voice-hosted-tests"},
    )


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"", text=""):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


# ── Groq STT ─────────────────────────────────────────────────────────────────

def test_groq_engine_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    from adam.api.voice.stt import GroqWhisperEngine
    assert GroqWhisperEngine().is_available() is False
    assert GroqWhisperEngine(api_key="gsk_test").is_available() is True


def test_groq_engine_transcribes_via_http(monkeypatch):
    from adam.api.voice import stt as stt_module
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _FakeResponse(
            payload={
                "text": "  महंगाई भत्ता 46 प्रतिशत है  ",
                "language": "hi",
                "segments": [{"avg_logprob": -0.2}, {"avg_logprob": -0.4}],
            }
        )

    monkeypatch.setattr(stt_module.httpx, "post", fake_post)
    engine = stt_module.GroqWhisperEngine(api_key="gsk_test")
    result = engine.transcribe(b"RIFF" + b"\x00" * 40, language_hint="hi-IN")

    assert result.transcript == "महंगाई भत्ता 46 प्रतिशत है"
    assert result.language == "hi"
    assert result.confidence == pytest.approx(0.7)
    assert captured["url"] == stt_module.GROQ_TRANSCRIPTIONS_URL
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer gsk_test"
    assert captured["kwargs"]["data"]["model"] == stt_module.GROQ_DEFAULT_STT_MODEL
    assert captured["kwargs"]["data"]["language"] == "hi"
    # WAV bytes are labelled .wav so the provider's extension check passes
    assert captured["kwargs"]["files"]["file"][0] == "recording.wav"


def test_groq_engine_raises_on_bad_key(monkeypatch):
    from adam.api.voice import stt as stt_module
    monkeypatch.setattr(
        stt_module.httpx, "post",
        lambda url, **kw: _FakeResponse(status_code=401, payload={"error": {"message": "Invalid API Key"}}),
    )
    with pytest.raises(stt_module.SttError, match="rejected the API key"):
        stt_module.GroqWhisperEngine(api_key="bad").transcribe(b"\x00" * 100)


def test_stt_factory_prefers_groq_when_key_present(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.delenv("ADAM_STT_PROVIDER", raising=False)
    from adam.api.voice import stt as stt_module
    assert stt_module.get_stt_engine().provider == "groq"

    monkeypatch.setenv("ADAM_STT_PROVIDER", "none")
    assert stt_module.get_stt_engine().provider == "none"


# ── ElevenLabs TTS ───────────────────────────────────────────────────────────

def test_elevenlabs_engine_synthesizes_via_http(monkeypatch):
    from adam.api.voice import tts as tts_module
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _FakeResponse(content=b"ID3fake-mp3-bytes")

    monkeypatch.setattr(tts_module.httpx, "post", fake_post)
    engine = tts_module.ElevenLabsTtsEngine(api_key="el_test", voice_id="voice123")
    audio = engine.synthesize("नमस्ते अधिकारी जी", language="hi")

    assert audio == b"ID3fake-mp3-bytes"
    assert engine.media_type == "audio/mpeg"
    assert captured["url"].endswith("/v1/text-to-speech/voice123")
    assert captured["kwargs"]["headers"]["xi-api-key"] == "el_test"
    assert captured["kwargs"]["params"]["output_format"] == tts_module.ELEVENLABS_OUTPUT_FORMAT
    assert captured["kwargs"]["json"]["text"] == "नमस्ते अधिकारी जी"
    assert captured["kwargs"]["json"]["language_code"] == "hi"


def test_elevenlabs_engine_splits_long_text(monkeypatch):
    from adam.api.voice import tts as tts_module
    calls = []

    def fake_post(url, **kw):
        calls.append(kw["json"]["text"])
        return _FakeResponse(content=b"x")

    monkeypatch.setattr(tts_module.httpx, "post", fake_post)
    long_text = "This is a sentence. " * 300  # ~6000 chars
    audio = tts_module.ElevenLabsTtsEngine(api_key="k").synthesize(long_text, "en")
    assert len(calls) >= 3
    assert all(len(c) <= tts_module.ELEVENLABS_MAX_CHARS for c in calls)
    assert audio == b"x" * len(calls)


def test_elevenlabs_engine_raises_on_quota(monkeypatch):
    from adam.api.voice import tts as tts_module
    monkeypatch.setattr(
        tts_module.httpx, "post",
        lambda url, **kw: _FakeResponse(status_code=429, payload={"detail": {"status": "quota_exceeded"}}),
    )
    with pytest.raises(tts_module.TtsError, match="rate limit"):
        tts_module.ElevenLabsTtsEngine(api_key="k").synthesize("hello", "en")


def test_tts_factory_prefers_elevenlabs_when_key_present(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el_test")
    monkeypatch.delenv("ADAM_TTS_PROVIDER", raising=False)
    from adam.api.voice import tts as tts_module
    assert tts_module.get_tts_engine().provider == "elevenlabs"

    monkeypatch.setenv("ADAM_TTS_PROVIDER", "none")
    assert tts_module.get_tts_engine().provider == "none"


# ── Speech text cleanup ──────────────────────────────────────────────────────

def test_clean_for_speech_strips_markdown_and_citations():
    from adam.api.voice.speech_text import clean_for_speech
    raw = (
        "## Answer\n\n"
        "The **DA rate** is *46%* effective 01-01-2024 [1][GO-2023-114].\n"
        "- Item one\n"
        "- Item two (Source: GO 12/2023)\n"
        "See [the order](https://example.com/go.pdf) or https://uk.gov.in/x.\n"
        "```\ncode block\n```\n"
    )
    spoken = clean_for_speech(raw)
    assert "**" not in spoken and "#" not in spoken and "```" not in spoken
    assert "[1]" not in spoken and "GO-2023-114" not in spoken
    assert "Source:" not in spoken
    assert "https://" not in spoken
    assert "The DA rate is 46% effective 01-01-2024." in spoken
    assert "See the order or" in spoken
    assert "code block" not in spoken


def test_clean_for_speech_keeps_hindi_prose():
    from adam.api.voice.speech_text import clean_for_speech
    assert clean_for_speech("यह एक **परीक्षण** है।") == "यह एक परीक्षण है।"
    assert clean_for_speech("") == ""


# ── Status & endpoint wiring ─────────────────────────────────────────────────

def test_voice_status_endpoint_reports_engines(test_client, monkeypatch):
    monkeypatch.setenv("ADAM_STT_PROVIDER", "none")
    monkeypatch.setenv("ADAM_TTS_PROVIDER", "none")
    resp = test_client.get("/api/voice/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stt"] == {"available": False, "provider": "none", "engine": "NullSttEngine"}
    assert body["tts"]["available"] is False
    assert body["tts"]["media_type"] == "audio/wav"


def test_voice_status_endpoint_with_hosted_keys(test_client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el_test")
    monkeypatch.delenv("ADAM_STT_PROVIDER", raising=False)
    monkeypatch.delenv("ADAM_TTS_PROVIDER", raising=False)
    body = test_client.get("/api/voice/status").json()
    assert body["stt"] == {"available": True, "provider": "groq", "engine": "GroqWhisperEngine"}
    assert body["tts"]["provider"] == "elevenlabs"
    assert body["tts"]["media_type"] == "audio/mpeg"


def test_transcribe_endpoint_uses_hosted_engine(test_client, monkeypatch):
    from adam.api.voice import stt as stt_module
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.delenv("ADAM_STT_PROVIDER", raising=False)
    monkeypatch.setattr(
        stt_module.httpx, "post",
        lambda url, **kw: _FakeResponse(payload={"text": "What is the DA rate?", "language": "en", "segments": []}),
    )
    resp = test_client.post(
        "/api/voice/transcribe",
        files={"file": ("rec.webm", io.BytesIO(b"\x1aE\xdf\xa3webm"), "audio/webm")},
        data={"language_hint": "en"},
    )
    assert resp.status_code == 200
    assert resp.json()["transcript"] == "What is the DA rate?"


def test_transcribe_endpoint_surfaces_provider_error(test_client, monkeypatch):
    from adam.api.voice import stt as stt_module
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.delenv("ADAM_STT_PROVIDER", raising=False)
    monkeypatch.setattr(
        stt_module.httpx, "post",
        lambda url, **kw: _FakeResponse(status_code=429, payload={"error": {"message": "slow down"}}),
    )
    resp = test_client.post(
        "/api/voice/transcribe",
        files={"file": ("rec.webm", io.BytesIO(b"\x00" * 64), "audio/webm")},
    )
    assert resp.status_code == 502
    assert "rate limit" in resp.json()["error"]["message"]


def test_transcribe_endpoint_rejects_empty_upload(test_client):
    resp = test_client.post(
        "/api/voice/transcribe",
        files={"file": ("rec.webm", io.BytesIO(b""), "audio/webm")},
    )
    assert resp.status_code == 422


def test_synthesize_endpoint_returns_mpeg_from_elevenlabs(test_client, monkeypatch):
    from adam.api.voice import tts as tts_module
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el_test")
    monkeypatch.delenv("ADAM_TTS_PROVIDER", raising=False)
    sent = {}

    def fake_post(url, **kw):
        sent["text"] = kw["json"]["text"]
        return _FakeResponse(content=b"ID3mp3")

    monkeypatch.setattr(tts_module.httpx, "post", fake_post)
    resp = test_client.post(
        "/api/voice/synthesize",
        json={"text": "The **rate** is 46% [1].", "language": "en"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert resp.content == b"ID3mp3"
    # Markdown and citation markers are never spoken
    assert sent["text"] == "The rate is 46%."


def test_synthesize_endpoint_rejects_markup_only_text(test_client):
    resp = test_client.post("/api/voice/synthesize", json={"text": "[1] [2] ---", "language": "en"})
    assert resp.status_code == 422
