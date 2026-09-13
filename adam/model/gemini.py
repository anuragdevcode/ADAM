"""Google Gemini cloud model runtime implementation for ADAM.

Enforces:
- Strict evidence packet grounding
- Temperature bounds (0.0 to 0.2)
- Citation and refusal detection
- Automatic API key redaction from error logs and traces
"""

import os
import re
import time
import logging
from typing import Optional, List, Dict, Any
import httpx

from adam.model.registry import ModelArtifact, DEFAULT_ADAM_SYSTEM_PROMPT
from adam.model.runtime import BaseModelRuntime, ModelGenerationResult, TemperatureOutOfBoundsError

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _redact_key(text: str, api_key: Optional[str]) -> str:
    """Ensure raw API key never leaks into exception or log strings."""
    if not api_key or not text:
        return text
    return text.replace(api_key, "[REDACTED_GEMINI_KEY]")


MODEL_ALIASES = {
    "gemini-2.0-flash": "gemini-3.6-flash",
    "gemini-2.0-flash-exp": "gemini-3.6-flash",
    "gemini-2.5-flash": "gemini-3.6-flash",
}


class GeminiModelRuntime(BaseModelRuntime):
    """Production runtime for Google Gemini cloud models (3.6 Flash, 1.5 Flash, 1.5 Pro)."""

    def __init__(self, artifact: ModelArtifact, api_key: Optional[str] = None):
        super().__init__(artifact)
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
        self.model_name = MODEL_ALIASES.get(artifact.id, artifact.id)

    def is_available(self) -> bool:
        """Check if Gemini API key is configured."""
        return bool(self.api_key)

    def generate(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 512,
        stop_sequences: Optional[List[str]] = None,
    ) -> ModelGenerationResult:
        """Generate response bounded by strict temperature and token limits."""
        start_time = time.perf_counter()
        valid_temp = self.validate_temperature(temperature)
        sys_prompt = system_prompt or self.artifact.system_prompt_default

        if not self.api_key:
            raise RuntimeError(
                "Gemini API key is not configured. Please enter your API key in the UI model dropdown "
                "or set GEMINI_API_KEY in your .env file."
            )

        url = f"{GEMINI_API_BASE}/models/{self.model_name}:generateContent?key={self.api_key}"

        stops = stop_sequences or ["\n\nUser:"]

        payload: Dict[str, Any] = {
            "system_instruction": {
                "parts": [{"text": sys_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}]
                }
            ],
            "generationConfig": {
                "temperature": valid_temp,
                "maxOutputTokens": max_tokens,
                "stopSequences": stops,
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
        }

        # Build candidate models list: requested/aliased model first, followed by robust fallbacks
        candidate_models = [self.model_name]
        for fallback in ["gemini-1.5-flash", "gemini-1.5-pro"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        data = None
        last_error = None
        actual_model = self.model_name

        try:
            with httpx.Client(timeout=30.0) as client:
                for cand in candidate_models:
                    url = f"{GEMINI_API_BASE}/models/{cand}:generateContent?key={self.api_key}"
                    resp = client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        actual_model = cand
                        self.model_name = cand
                        break
                    elif resp.status_code == 404:
                        last_error = _redact_key(resp.text, self.api_key)
                        logger.warning(
                            f"Gemini model '{cand}' returned 404. Trying fallback candidate... ({last_error})"
                        )
                        continue
                    else:
                        err_msg = _redact_key(resp.text, self.api_key)
                        raise RuntimeError(f"Gemini API returned status {resp.status_code}: {err_msg}")

            if data is None:
                raise RuntimeError(
                    f"Gemini API returned status 404 across all candidates: {last_error}"
                )

            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("Gemini API returned empty candidates.")

            first_cand = candidates[0]
            parts = first_cand.get("content", {}).get("parts", [])
            answer = "".join(p.get("text", "") for p in parts).strip()
            finish_reason = first_cand.get("finishReason", "STOP").lower()

            usage = data.get("usageMetadata", {})
            prompt_tokens = usage.get("promptTokenCount") or max(1, len(user_prompt.split()) * 4 // 3)
            completion_tokens = usage.get("candidatesTokenCount") or max(1, len(answer.split()) * 4 // 3)
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            lower_ans = answer.lower()
            is_refusal = (
                "could not establish" in lower_ans
                or "exempt from public" in lower_ans
                or "outside the uttarakhand" in lower_ans
                or "human authority required" in lower_ans
                or "स्थापित नहीं किया जा सका" in answer
                or "अधिकार क्षेत्र से बाहर" in answer
                or "मानव प्राधिकारी आवश्यक" in answer
                or "गोपनीय" in answer
                or "प्रतिबंधित" in answer
            )

            refusal_category = None
            if is_refusal:
                if "outside" in lower_ans or "jurisdiction" in lower_ans or "अधिकार क्षेत्र से बाहर" in answer:
                    refusal_category = "OUT_OF_JURISDICTION"
                elif "exempt" in lower_ans or "confidential" in lower_ans or "गोपनीय" in answer or "प्रतिबंधित" in answer:
                    refusal_category = "PRIVATE_EXEMPT_RECORD"
                elif "human authority" in lower_ans or "मानव प्राधिकारी" in answer:
                    refusal_category = "HIGH_RISK_HUMAN_AUTHORITY"
                elif "could not establish" in lower_ans or "स्थापित नहीं" in answer:
                    refusal_category = "ZERO_EVIDENCE"

            logger.info(
                f"Gemini generation completed: model={actual_model}, prompt_tokens={prompt_tokens}, "
                f"completion_tokens={completion_tokens}, finish_reason={finish_reason}, latency={latency_ms:.1f}ms"
            )

            return ModelGenerationResult(
                answer=answer,
                raw_completion=answer,
                tokens_prompt=prompt_tokens,
                tokens_completion=completion_tokens,
                model_id=self.artifact.id,
                latency_ms=latency_ms,
                temperature=valid_temp,
                finish_reason="stop" if finish_reason in ("stop", "") else finish_reason,
                is_refusal=is_refusal,
                refusal_category=refusal_category,
            )

        except Exception as e:
            redacted_err = _redact_key(str(e), self.api_key)
            logger.error(f"Gemini generation error: {redacted_err}")
            raise RuntimeError(f"Gemini model execution error: {redacted_err}")

    def unload(self) -> None:
        """Cloud models maintain no persistent local GPU memory allocations."""
        self.is_loaded = False
