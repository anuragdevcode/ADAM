"""Pluggable STT abstraction."""

import importlib.util
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class SttResult:
    transcript: str
    language: str
    confidence: float

class BaseSttEngine(ABC):
    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def transcribe(self, audio_bytes: bytes, language_hint: str = 'hi') -> SttResult:
        pass

class FasterWhisperEngine(BaseSttEngine):
    def is_available(self) -> bool:
        return importlib.util.find_spec('faster_whisper') is not None

    def transcribe(self, audio_bytes: bytes, language_hint: str = 'hi') -> SttResult:
        try:
            from faster_whisper import WhisperModel
            import io
            
            # Write bytes to file-like object
            audio_io = io.BytesIO(audio_bytes)
            
            # Lazy load model
            model = WhisperModel("small", device="cpu", compute_type="int8")
            segments, info = model.transcribe(audio_io, language=language_hint)
            
            transcript = " ".join([segment.text for segment in segments])
            language = info.language
            
            return SttResult(
                transcript=transcript.strip(),
                language=language,
                confidence=0.8  # Default confidence fallback
            )
        except ImportError:
            logger.error("faster_whisper is not installed")
            return SttResult(transcript="", language=language_hint, confidence=0.0)
        except Exception as e:
            logger.error(f"Error during transcription: {e}")
            return SttResult(transcript="", language=language_hint, confidence=0.0)

class NullSttEngine(BaseSttEngine):
    def is_available(self) -> bool:
        return True

    def transcribe(self, audio_bytes: bytes, language_hint: str = 'hi') -> SttResult:
        return SttResult(transcript='', language='hi', confidence=0.0)


class GeminiSttEngine(BaseSttEngine):
    """Multimodal cloud speech-to-text powered by Google Gemini 2.0 / 1.5 Flash."""

    def __init__(self, api_key: Optional[str] = None):
        import os
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()

    def is_available(self) -> bool:
        return bool(self.api_key)

    def transcribe(self, audio_bytes: bytes, language_hint: str = 'hi') -> SttResult:
        if not self.api_key:
            return SttResult(transcript="", language=language_hint, confidence=0.0)
        try:
            import base64
            import httpx

            b64_data = base64.b64encode(audio_bytes).decode("utf-8")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={self.api_key}"

            mime_type = "audio/webm"
            if audio_bytes[:4] == b"RIFF":
                mime_type = "audio/wav"
            elif audio_bytes[:3] == b"ID3" or audio_bytes[:2] == b"\xff\xfb":
                mime_type = "audio/mp3"

            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": (
                                    "Transcribe the spoken audio verbatim. Accurately capture Hindi, English, or bilingual Hindi-English speech. "
                                    "Output ONLY the transcribed words with no introduction, explanation, formatting, or quotation marks."
                                )
                            },
                            {
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": b64_data,
                                }
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": 256,
                }
            }

            candidate_models = ["gemini-3.6-flash", "gemini-1.5-flash"]
            with httpx.Client(timeout=20.0) as client:
                for cand in candidate_models:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{cand}:generateContent?key={self.api_key}"
                    resp = client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            text = "".join(p.get("text", "") for p in parts).strip()
                            return SttResult(transcript=text, language=language_hint, confidence=0.95)
                    elif resp.status_code == 404:
                        logger.warning(f"Gemini STT model {cand} returned 404, trying fallback...")
                        continue
                    else:
                        break
                logger.error(f"Gemini STT API error status {resp.status_code}")
                return SttResult(transcript="", language=language_hint, confidence=0.0)
        except Exception as e:
            logger.error(f"Gemini STT error: {e}")
            return SttResult(transcript="", language=language_hint, confidence=0.0)


def get_stt_engine(api_key: Optional[str] = None) -> BaseSttEngine:
    engine_gemini = GeminiSttEngine(api_key=api_key)
    if engine_gemini.is_available():
        logger.info("Selected GeminiSttEngine for STT")
        return engine_gemini
    engine_fw = FasterWhisperEngine()
    if engine_fw.is_available():
        logger.info("Selected FasterWhisperEngine for STT")
        return engine_fw
    logger.info("Selected NullSttEngine for STT")
    return NullSttEngine()
