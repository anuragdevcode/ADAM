"""Pluggable TTS abstraction."""

import logging
import shutil
import struct
import subprocess
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)

class BaseTtsEngine(ABC):
    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def synthesize(self, text: str, language: str = 'hi') -> bytes:
        pass

class NullTtsEngine(BaseTtsEngine):
    def is_available(self) -> bool:
        return True

    def synthesize(self, text: str, language: str = 'hi') -> bytes:
        # Minimal valid 44-byte WAV header for empty PCM
        header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF', 36, b'WAVE', b'fmt ', 16, 1, 1, 22050, 44100, 2, 16, b'data', 0
        )
        return header

class PiperTtsEngine(BaseTtsEngine):
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

class GeminiTtsEngine(BaseTtsEngine):
    """Voice synthesis powered by Google Gemini API audio modality."""

    def __init__(self, api_key: Optional[str] = None):
        import os
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()

    def is_available(self) -> bool:
        return bool(self.api_key)

    def synthesize(self, text: str, language: str = 'hi') -> bytes:
        if not self.api_key or not text:
            return NullTtsEngine().synthesize(text, language)
        try:
            import base64
            import httpx

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={self.api_key}"
            voice_name = "Puck" if language == "en" else "Kore"

            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": f"Read the following text aloud clearly and naturally: {text}"
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": voice_name
                            }
                        }
                    }
                }
            }

            candidate_models = ["gemini-3.6-flash", "gemini-1.5-flash"]
            with httpx.Client(timeout=25.0) as client:
                for cand in candidate_models:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{cand}:generateContent?key={self.api_key}"
                    resp = client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            for p in parts:
                                inline = p.get("inlineData", {})
                                if inline.get("mimeType", "").startswith("audio/") and inline.get("data"):
                                    audio_raw = base64.b64decode(inline["data"])
                                    if audio_raw.startswith(b"RIFF"):
                                        return audio_raw
                                    rate = 24000
                                    channels = 1
                                    bits = 16
                                    byte_rate = rate * channels * (bits // 8)
                                    block_align = channels * (bits // 8)
                                    wav_header = struct.pack(
                                        '<4sI4s4sIHHIIHH4sI',
                                        b'RIFF', 36 + len(audio_raw), b'WAVE', b'fmt ', 16, 1, channels, rate, byte_rate, block_align, bits, b'data', len(audio_raw)
                                    )
                                    return wav_header + audio_raw
                    elif resp.status_code == 404:
                        logger.warning(f"Gemini TTS model {cand} returned 404, trying fallback...")
                        continue
                    else:
                        break
            logger.warning(f"Gemini TTS synthesis status {resp.status_code}, using fallback.")
            return PiperTtsEngine().synthesize(text, language) if PiperTtsEngine().is_available() else NullTtsEngine().synthesize(text, language)
        except Exception as e:
            logger.error(f"Gemini TTS synthesis error: {e}")
            return NullTtsEngine().synthesize(text, language)


def get_tts_engine(api_key: Optional[str] = None) -> BaseTtsEngine:
    engine_gemini = GeminiTtsEngine(api_key=api_key)
    if engine_gemini.is_available():
        logger.info("Selected GeminiTtsEngine for TTS")
        return engine_gemini
    engine_piper = PiperTtsEngine()
    if engine_piper.is_available():
        logger.info("Selected PiperTtsEngine for TTS")
        return engine_piper
    logger.info("Selected NullTtsEngine for TTS")
    return NullTtsEngine()
