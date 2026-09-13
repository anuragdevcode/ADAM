"""Pluggable STT abstraction.

Engines, in the order ``get_stt_engine()`` prefers them when
``ADAM_STT_PROVIDER`` is ``auto`` (the default):

1. ``GroqWhisperEngine``  — hosted Whisper on Groq's free tier (``GROQ_API_KEY``).
2. ``FasterWhisperEngine`` — local CPU Whisper (``pip install adam[voice]``).
3. ``NullSttEngine``       — nothing configured; the API reports STT unavailable
   and the UI falls back to the browser's own speech recognition.
"""

import importlib.util
import logging
import os
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from adam.config import REQUEST_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

GROQ_TRANSCRIPTIONS_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_DEFAULT_STT_MODEL = "whisper-large-v3-turbo"


class SttError(RuntimeError):
    """Raised when a configured engine fails to transcribe."""


@dataclass
class SttResult:
    transcript: str
    language: str
    confidence: float


class BaseSttEngine(ABC):
    #: Short identifier surfaced by ``GET /api/voice/status``.
    provider = "none"

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def transcribe(self, audio_bytes: bytes, language_hint: str = 'hi') -> SttResult:
        pass


class GroqWhisperEngine(BaseSttEngine):
    """Whisper large-v3 hosted by Groq (OpenAI-compatible transcription API)."""

    provider = "groq"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key if api_key is not None else os.getenv("GROQ_API_KEY", "")
        self.model = model or os.getenv("GROQ_STT_MODEL", GROQ_DEFAULT_STT_MODEL)

    def is_available(self) -> bool:
        return bool(self.api_key.strip())

    def transcribe(self, audio_bytes: bytes, language_hint: str = 'hi') -> SttResult:
        if not self.is_available():
            raise SttError("GROQ_API_KEY is not configured.")
        # Groq validates the extension, so pick one matching what browsers record.
        filename = "recording.webm"
        if audio_bytes[:4] == b"RIFF":
            filename = "recording.wav"
        elif audio_bytes[4:8] == b"ftyp":
            filename = "recording.mp4"
        data = {"model": self.model, "response_format": "verbose_json"}
        # Whisper auto-detects when no language is given; only pin a real code.
        if language_hint and language_hint.lower() not in ("auto", ""):
            data["language"] = language_hint.split("-")[0].lower()
        try:
            resp = httpx.post(
                GROQ_TRANSCRIPTIONS_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"file": (filename, audio_bytes)},
                data=data,
                timeout=max(REQUEST_TIMEOUT_SECONDS, 60.0),
            )
        except httpx.HTTPError as exc:
            raise SttError(f"Could not reach Groq speech-to-text: {exc}") from exc
        if resp.status_code != 200:
            raise SttError(_describe_http_error("Groq", resp))
        payload = resp.json()
        transcript = (payload.get("text") or "").strip()
        language = payload.get("language") or (data.get("language") or language_hint)
        segments = payload.get("segments") or []
        return SttResult(
            transcript=transcript,
            language=language,
            confidence=_confidence_from_segments(segments),
        )


class FasterWhisperEngine(BaseSttEngine):
    provider = "faster_whisper"

    _model = None
    _model_lock = threading.Lock()

    def is_available(self) -> bool:
        return importlib.util.find_spec('faster_whisper') is not None

    @classmethod
    def _get_model(cls):
        # Loading the weights takes seconds; keep one instance for the process.
        if cls._model is None:
            with cls._model_lock:
                if cls._model is None:
                    from faster_whisper import WhisperModel
                    size = os.getenv("FASTER_WHISPER_MODEL", "small")
                    cls._model = WhisperModel(size, device="cpu", compute_type="int8")
        return cls._model

    def transcribe(self, audio_bytes: bytes, language_hint: str = 'hi') -> SttResult:
        try:
            import io

            audio_io = io.BytesIO(audio_bytes)
            model = self._get_model()
            language = None if language_hint in ("auto", "") else language_hint.split("-")[0]
            segments, info = model.transcribe(audio_io, language=language)

            transcript = " ".join([segment.text for segment in segments])

            return SttResult(
                transcript=transcript.strip(),
                language=info.language,
                confidence=0.8  # Default confidence fallback
            )
        except ImportError:
            logger.error("faster_whisper is not installed")
            return SttResult(transcript="", language=language_hint, confidence=0.0)
        except Exception as e:
            logger.error(f"Error during transcription: {e}")
            return SttResult(transcript="", language=language_hint, confidence=0.0)


class NullSttEngine(BaseSttEngine):
    provider = "none"

    def is_available(self) -> bool:
        return True

    def transcribe(self, audio_bytes: bytes, language_hint: str = 'hi') -> SttResult:
        return SttResult(transcript='', language='hi', confidence=0.0)


def _confidence_from_segments(segments) -> float:
    """Map Whisper's avg_logprob (≈ -1 … 0) onto 0 … 1."""
    logprobs = [s.get("avg_logprob") for s in segments if isinstance(s, dict) and s.get("avg_logprob") is not None]
    if not logprobs:
        return 0.8
    mean = sum(logprobs) / len(logprobs)
    return round(min(1.0, max(0.0, 1.0 + mean)), 3)


def _describe_http_error(provider: str, resp: httpx.Response) -> str:
    try:
        body = resp.json()
        message = body.get("error", {}).get("message") or body.get("detail") or resp.text
    except ValueError:
        message = resp.text
    if resp.status_code in (401, 403):
        return f"{provider} rejected the API key ({resp.status_code}). Check the key in .env."
    if resp.status_code == 429:
        return f"{provider} rate limit reached (429). Wait a moment and try again."
    return f"{provider} returned {resp.status_code}: {str(message)[:200]}"


def get_stt_engine() -> BaseSttEngine:
    """Pick the STT engine from ``ADAM_STT_PROVIDER`` (auto|groq|faster_whisper|none)."""
    provider = os.getenv("ADAM_STT_PROVIDER", "auto").strip().lower()
    groq = GroqWhisperEngine()
    local = FasterWhisperEngine()

    if provider == "groq":
        if groq.is_available():
            return groq
        logger.warning("ADAM_STT_PROVIDER=groq but GROQ_API_KEY is empty; STT disabled")
        return NullSttEngine()
    if provider == "faster_whisper":
        if local.is_available():
            return local
        logger.warning("ADAM_STT_PROVIDER=faster_whisper but faster_whisper is not installed; STT disabled")
        return NullSttEngine()
    if provider == "none":
        return NullSttEngine()

    if groq.is_available():
        logger.info("Selected GroqWhisperEngine for STT")
        return groq
    if local.is_available():
        logger.info("Selected FasterWhisperEngine for STT")
        return local
    logger.info("Selected NullSttEngine for STT")
    return NullSttEngine()
