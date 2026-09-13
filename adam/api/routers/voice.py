from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from adam.api.voice.stt import FasterWhisperEngine, GeminiSttEngine, get_stt_engine
from adam.api.voice.tts import get_tts_engine

router = APIRouter()

class SynthesizeRequest(BaseModel):
    text: str
    language: str = 'hi'

@router.post("/voice/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language_hint: str = Form("hi"),
    api_key: Optional[str] = Form(None),
    x_gemini_api_key: Optional[str] = Header(None),
):
    audio_bytes = await file.read()
    if len(audio_bytes) < 500:
        raise HTTPException(
            status_code=400,
            detail="Audio recording was too short or empty. Please hold the button while speaking.",
        )
    effective_key = x_gemini_api_key or api_key
    stt_engine = get_stt_engine(api_key=effective_key)
    if not isinstance(stt_engine, (FasterWhisperEngine, GeminiSttEngine)):
        raise HTTPException(
            status_code=503,
            detail="Speech-to-text is unavailable: configure a Gemini API key or install 'faster-whisper'.",
        )
    result = stt_engine.transcribe(audio_bytes, language_hint=language_hint)
    if not result.transcript:
        engine_name = "Gemini" if isinstance(stt_engine, GeminiSttEngine) else "Fast Whisper"
        raise HTTPException(
            status_code=502,
            detail=f"{engine_name} could not transcribe this recording. Check the microphone recording and try again.",
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
    wav_bytes = tts_engine.synthesize(req.text, req.language)
    return Response(content=wav_bytes, media_type='audio/wav')
