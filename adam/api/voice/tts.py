"""Pluggable TTS abstraction.

Engines, in the order ``get_tts_engine()`` prefers them when
``ADAM_TTS_PROVIDER`` is ``auto`` (the default):

1. ``ElevenLabsTtsEngine`` — hosted multilingual voices, free tier
   (``ELEVENLABS_API_KEY``); speaks Hindi and English naturally.
2. ``PiperTtsEngine``      — local ``piper`` binary when present on PATH.
3. ``NullTtsEngine``       — returns a silent WAV so the UI falls back to the
   browser's built-in speech synthesis.
"""

import logging
import os
import shutil
import struct
import subprocess
from abc import ABC, abstractmethod

import httpx

from adam.config import REQUEST_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
# "Rachel": a premade voice available on every ElevenLabs plan.
ELEVENLABS_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
# Flash v2.5 covers Hindi + English, is low-latency and costs half the credits
# of multilingual_v2, which stretches the free tier further.
ELEVENLABS_DEFAULT_MODEL_ID = "eleven_flash_v2_5"
ELEVENLABS_OUTPUT_FORMAT = "mp3_44100_128"
# ElevenLabs caps a single request; longer answers are split at sentence ends.
ELEVENLABS_MAX_CHARS = 2500


class TtsError(RuntimeError):
    """Raised when a configured engine fails to synthesize."""


class BaseTtsEngine(ABC):
    #: Short identifier surfaced by ``GET /api/voice/status``.
    provider = "none"
    #: MIME type of the bytes returned by ``synthesize``.
    media_type = "audio/wav"

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def synthesize(self, text: str, language: str = 'hi') -> bytes:
        pass


class NullTtsEngine(BaseTtsEngine):
    provider = "none"

    def is_available(self) -> bool:
        return True

    def synthesize(self, text: str, language: str = 'hi') -> bytes:
        # Minimal valid 44-byte WAV header for empty PCM
        header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF', 36, b'WAVE', b'fmt ', 16, 1, 1, 22050, 44100, 2, 16, b'data', 0
        )
        return header


class ElevenLabsTtsEngine(BaseTtsEngine):
    provider = "elevenlabs"
    media_type = "audio/mpeg"

    def __init__(self, api_key: str | None = None, voice_id: str | None = None, model_id: str | None = None):
        self.api_key = api_key if api_key is not None else os.getenv("ELEVENLABS_API_KEY", "")
        self.voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID", ELEVENLABS_DEFAULT_VOICE_ID)
        self.model_id = model_id or os.getenv("ELEVENLABS_MODEL_ID", ELEVENLABS_DEFAULT_MODEL_ID)

    def is_available(self) -> bool:
        return bool(self.api_key.strip())

    def synthesize(self, text: str, language: str = 'hi') -> bytes:
        if not self.is_available():
            raise TtsError("ELEVENLABS_API_KEY is not configured.")
        text = text.strip()
        if not text:
            raise TtsError("Nothing to speak.")
        chunks = _split_for_tts(text, ELEVENLABS_MAX_CHARS)
        audio = b""
        for chunk in chunks:
            audio += self._synthesize_chunk(chunk, language)
        return audio

    def _synthesize_chunk(self, text: str, language: str) -> bytes:
        body = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        # language_code is honoured by the flash/turbo v2.5 models only.
        lang = (language or "").split("-")[0].lower()
        if lang and lang != "auto" and "v2_5" in self.model_id:
            body["language_code"] = lang
        try:
            resp = httpx.post(
                ELEVENLABS_TTS_URL.format(voice_id=self.voice_id),
                params={"output_format": ELEVENLABS_OUTPUT_FORMAT},
                headers={"xi-api-key": self.api_key, "Accept": "audio/mpeg"},
                json=body,
                timeout=max(REQUEST_TIMEOUT_SECONDS, 60.0),
            )
        except httpx.HTTPError as exc:
            raise TtsError(f"Could not reach ElevenLabs text-to-speech: {exc}") from exc
        if resp.status_code != 200:
            raise TtsError(_describe_http_error("ElevenLabs", resp))
        if not resp.content:
            raise TtsError("ElevenLabs returned an empty audio response.")
        return resp.content


class PiperTtsEngine(BaseTtsEngine):
    provider = "piper"

    def is_available(self) -> bool:
        return shutil.which('piper') is not None

    def synthesize(self, text: str, language: str = 'hi') -> bytes:
        try:
            # Note: A real implementation would specify a model file
            process = subprocess.Popen(
                ['piper', '--output_raw'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            out, err = process.communicate(input=text.encode('utf-8'))
            return out
        except Exception as e:
            logger.error(f"Error synthesizing speech with piper: {e}")
            return NullTtsEngine().synthesize(text, language)


def _split_for_tts(text: str, limit: int) -> list[str]:
    """Split long text at sentence boundaries so each request stays under ``limit``."""
    if len(text) <= limit:
        return [text]
    import re

    sentences = re.split(r"(?<=[.!?।\n])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 > limit and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
        # A single run-on sentence longer than the limit is hard-cut.
        while len(current) > limit:
            chunks.append(current[:limit])
            current = current[limit:]
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _describe_http_error(provider: str, resp: httpx.Response) -> str:
    try:
        body = resp.json()
        detail = body.get("detail")
        if isinstance(detail, dict):
            message = detail.get("message") or detail.get("status") or str(detail)
        else:
            message = detail or body.get("error", {}).get("message") or resp.text
    except ValueError:
        message = resp.text
    if resp.status_code in (401, 403):
        return f"{provider} rejected the API key ({resp.status_code}). Check the key in .env."
    if resp.status_code == 429:
        return f"{provider} rate limit reached (429). Wait a moment and try again."
    return f"{provider} returned {resp.status_code}: {str(message)[:200]}"


def get_tts_engine() -> BaseTtsEngine:
    """Pick the TTS engine from ``ADAM_TTS_PROVIDER`` (auto|elevenlabs|piper|none)."""
    provider = os.getenv("ADAM_TTS_PROVIDER", "auto").strip().lower()
    eleven = ElevenLabsTtsEngine()
    piper = PiperTtsEngine()

    if provider == "elevenlabs":
        if eleven.is_available():
            return eleven
        logger.warning("ADAM_TTS_PROVIDER=elevenlabs but ELEVENLABS_API_KEY is empty; using browser fallback")
        return NullTtsEngine()
    if provider == "piper":
        if piper.is_available():
            return piper
        logger.warning("ADAM_TTS_PROVIDER=piper but the piper binary is not on PATH; using browser fallback")
        return NullTtsEngine()
    if provider == "none":
        return NullTtsEngine()

    if eleven.is_available():
        logger.info("Selected ElevenLabsTtsEngine for TTS")
        return eleven
    if piper.is_available():
        logger.info("Selected PiperTtsEngine for TTS")
        return piper
    logger.info("Selected NullTtsEngine for TTS")
    return NullTtsEngine()
