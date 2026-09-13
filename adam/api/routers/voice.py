from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from adam.api.voice.speech_text import clean_for_speech
from adam.api.voice.stt import SttError, FasterWhisperEngine, GeminiSttEngine, get_stt_engine
from adam.api.voice.tts import TtsError, GeminiTtsEngine, get_tts_engine

router = APIRouter()

STT_UNAVAILABLE_DETAIL = (
    "Speech-to-text is unavailable: set GROQ_API_KEY (free at console.groq.com) "
    "or install the 'voice' dependencies (faster-whisper) and restart ADAM."
)

class SynthesizeRequest(BaseModel):
    text: str
    language: str = 'hi'

@router.get("/voice/status")
def voice_status():
    """Report which speech engines the server can offer.

    The UI uses this to decide between server-side speech (Groq / ElevenLabs /
    local engines) and the browser's built-in Web Speech API.
    """
    stt_engine = get_stt_engine()
    tts_engine = get_tts_engine()
    return {
        "stt": {
            "available": stt_engine.provider != "none",
            "provider": stt_engine.provider,
            "engine": type(stt_engine).__name__,
        },
        "tts": {
            "available": tts_engine.provider != "none",
            "provider": tts_engine.provider,
            "engine": type(tts_engine).__name__,
            "media_type": tts_engine.media_type,
        },
    }

@router.post("/voice/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language_hint: str = Form("hi"),
    api_key: Optional[str] = Form(None),
    x_gemini_api_key: Optional[str] = Header(None),
):
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=422, detail="The uploaded recording is empty.")
    effective_key = x_gemini_api_key or api_key
    stt_engine = get_stt_engine(api_key=effective_key)
    if stt_engine.provider == "none":
        raise HTTPException(status_code=503, detail=STT_UNAVAILABLE_DETAIL)
    try:
        result = stt_engine.transcribe(audio_bytes, language_hint=language_hint)
    except SttError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        if "SttError" in [b.__name__ for b in type(exc).__mro__] or type(exc).__name__ == "SttError":
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        raise

    if not result.transcript:
        raise HTTPException(
            status_code=502,
            detail="No speech was recognised in this recording. Check the microphone and try again.",
        )
    return {
        "transcript": result.transcript,
        "language": result.language,
        "confidence": result.confidence
    }

@router.post("/voice/synthesize")
def synthesize_speech(
    req: SynthesizeRequest,
    x_gemini_api_key: Optional[str] = Header(None),
):
    tts_engine = get_tts_engine(api_key=x_gemini_api_key)
    speech_text = clean_for_speech(req.text)
    if not speech_text:
        raise HTTPException(status_code=422, detail="There is no readable text to speak.")
    try:
        audio_bytes = tts_engine.synthesize(speech_text, req.language)
    except TtsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        if "TtsError" in [b.__name__ for b in type(exc).__mro__] or type(exc).__name__ == "TtsError":
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        raise
    return Response(content=audio_bytes, media_type=tts_engine.media_type)
