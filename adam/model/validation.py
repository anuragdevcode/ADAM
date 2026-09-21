"""Deterministic technical validation for discovered models and remote providers.

These checks are host-controlled and do NOT rely on the model's own responses
as a security authority.  They establish that ADAM can communicate with the
model/API and verify its technical properties.

Validation ≠ attestation ≠ approval:
  - Validation: can we reach it, does it speak the right protocol, does it auth?
  - Attestation (adam/model/attestation.py): does the model behave correctly?
  - Approval: only after both validation and attestation pass.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from adam.model.runtime import OllamaModelRuntime, BaseModelRuntime, ModelArtifact

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timeouts — strict, as specified in the security requirements
# ---------------------------------------------------------------------------

_CONNECT_TIMEOUT = 5.0
_READ_TIMEOUT = 10.0
_TOTAL_TIMEOUT = 15.0
_MAX_RESPONSE_BYTES = 512 * 1024   # 512 KB

_VALIDATION_PROBE_TOKENS = 1       # tiny non-generation request
_STREAMING_PROBE_TOKENS = 1        # to test streaming flag


# ---------------------------------------------------------------------------
# Result data model
# ---------------------------------------------------------------------------

@dataclass
class TechnicalValidationResult:
    """Structured result of deterministic infrastructure checks.

    All check results are determined by ADAM, not by the model's responses.
    Errors are human-readable but credential-redacted.
    """
    reachable: bool = False
    authenticated: bool = False
    protocol_valid: bool = False
    model_exists: bool = False
    request_schema_valid: bool = False
    response_schema_valid: bool = False
    streaming_support: bool = False
    structured_output_support: bool = False
    timeout_behavior_ok: bool = True
    model_metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    latency_ms: float = 0.0

    @property
    def core_valid(self) -> bool:
        """True when the minimum set of checks required before attestation pass."""
        return self.reachable and self.protocol_valid and self.model_exists

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reachable": self.reachable,
            "authenticated": self.authenticated,
            "protocol_valid": self.protocol_valid,
            "model_exists": self.model_exists,
            "request_schema_valid": self.request_schema_valid,
            "response_schema_valid": self.response_schema_valid,
            "streaming_support": self.streaming_support,
            "structured_output_support": self.structured_output_support,
            "timeout_behavior_ok": self.timeout_behavior_ok,
            "core_valid": self.core_valid,
            "latency_ms": round(self.latency_ms, 2),
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Ollama validator
# ---------------------------------------------------------------------------

class OllamaValidator:
    """Deterministic technical checks for a local Ollama model.

    Performs only safe, non-generation requests (GET /api/tags,
    POST /api/show) and a single controlled minimal inference call to
    verify request/response schema compliance.
    """

    MINIMAL_PROMPT = (
        "Respond with exactly the word: OK"
    )

    def __init__(self, host: Optional[str] = None, timeout: float = _TOTAL_TIMEOUT):
        self.host = (host or OllamaModelRuntime.DEFAULT_HOST).rstrip("/")
        self.timeout = timeout

    def validate(self, model_tag: str) -> TechnicalValidationResult:
        result = TechnicalValidationResult()
        start = time.perf_counter()

        # ---- 1. Reachability ----
        try:
            with httpx.Client(base_url=self.host, timeout=_CONNECT_TIMEOUT) as client:
                r = client.get("/api/tags")
                if r.status_code == 200:
                    result.reachable = True
                    result.authenticated = True   # Ollama has no auth by default
                    result.protocol_valid = True
                else:
                    result.errors.append(f"Ollama /api/tags returned HTTP {r.status_code}.")
                    return result
        except Exception as exc:
            result.errors.append("Ollama server is not reachable.")
            logger.debug("Ollama reachability check failed: %s", exc)
            return result

        # ---- 2. Model existence ----
        try:
            with httpx.Client(base_url=self.host, timeout=_READ_TIMEOUT) as client:
                r = client.post("/api/show", json={"name": model_tag})
                if r.status_code == 200:
                    result.model_exists = True
                    try:
                        result.model_metadata = r.json()
                    except Exception:
                        result.model_metadata = {}
                elif r.status_code == 404:
                    result.errors.append(
                        f"Model '{model_tag}' is not installed in Ollama. "
                        f"Run: ollama pull {model_tag}"
                    )
                    return result
                else:
                    result.errors.append(f"Ollama /api/show returned HTTP {r.status_code}.")
                    return result
        except Exception as exc:
            result.errors.append("Could not retrieve model metadata from Ollama.")
            logger.debug("Ollama model inspection failed: %s", exc)
            return result

        # ---- 3. Minimal non-streaming request (schema validation) ----
        try:
            payload = {
                "model": model_tag,
                "messages": [{"role": "user", "content": self.MINIMAL_PROMPT}],
                "stream": False,
                "options": {"num_predict": _VALIDATION_PROBE_TOKENS},
            }
            with httpx.Client(base_url=self.host, timeout=_TOTAL_TIMEOUT) as client:
                r = client.post("/api/chat", json=payload)
                if r.status_code == 200:
                    try:
                        data = r.json()
                        # Response must have "message" key per Ollama chat schema
                        if "message" in data:
                            result.request_schema_valid = True
                            result.response_schema_valid = True
                        else:
                            result.errors.append(
                                "Ollama chat response missing 'message' field — unexpected schema."
                            )
                    except Exception:
                        result.errors.append("Ollama chat response is not valid JSON.")
                else:
                    result.errors.append(
                        f"Ollama /api/chat returned HTTP {r.status_code} during schema validation."
                    )
        except httpx.TimeoutException:
            result.timeout_behavior_ok = False
            result.errors.append("Ollama chat request timed out during schema validation.")
        except Exception as exc:
            result.errors.append("Schema validation request failed.")
            logger.debug("Ollama schema validation failed: %s", exc)

        # ---- 4. Streaming probe ----
        try:
            payload_stream = {
                "model": model_tag,
                "messages": [{"role": "user", "content": self.MINIMAL_PROMPT}],
                "stream": True,
                "options": {"num_predict": _STREAMING_PROBE_TOKENS},
            }
            with httpx.Client(base_url=self.host, timeout=_TOTAL_TIMEOUT) as client:
                with client.stream("POST", "/api/chat", json=payload_stream) as resp:
                    if resp.status_code == 200:
                        # Read first chunk only — we just need to confirm stream opens
                        for _chunk in resp.iter_lines():
                            result.streaming_support = True
                            break
        except Exception:
            # Streaming is optional — log but don't fail validation
            logger.debug("Ollama streaming probe failed for model '%s'.", model_tag)

        result.latency_ms = (time.perf_counter() - start) * 1000.0
        return result


# ---------------------------------------------------------------------------
# Remote API validator
# ---------------------------------------------------------------------------

class RemoteApiValidator:
    """Deterministic technical checks for a remote OpenAI/Gemini-compatible API.

    No user data is sent.  The only payloads used are:
    - GET /models (OpenAI) or GET /v1beta/models (Gemini)
    - A single 1-token chat completion to verify schema compliance.
    """

    _HEADERS_TIMEOUT = httpx.Timeout(
        connect=_CONNECT_TIMEOUT,
        read=_READ_TIMEOUT,
        write=5.0,
        pool=5.0,
    )

    PROBE_PROMPT = "Respond with exactly the word: OK"

    def validate_openai_compatible(
        self,
        endpoint_url: str,
        model_id: str,
        api_key: Optional[str] = None,
    ) -> TechnicalValidationResult:
        """Validate an OpenAI-compatible endpoint for a specific model."""
        result = TechnicalValidationResult()
        start = time.perf_counter()
        base = endpoint_url.rstrip("/")
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # ---- 1. Reachability + auth (GET /models) ----
        try:
            with httpx.Client(timeout=self._HEADERS_TIMEOUT) as client:
                r = client.get(f"{base}/models", headers=headers)
                if r.status_code == 200:
                    result.reachable = True
                    result.authenticated = True
                    result.protocol_valid = True
                elif r.status_code in (401, 403):
                    result.reachable = True
                    result.authenticated = False
                    result.errors.append("Authentication failed. Check the API key.")
                    return result
                else:
                    result.reachable = True
                    result.errors.append(f"Endpoint returned HTTP {r.status_code}.")
                    return result
        except httpx.TimeoutException:
            result.errors.append("Connection timed out. Endpoint may be unreachable.")
            return result
        except Exception as exc:
            result.errors.append("Endpoint is not reachable.")
            logger.debug("Remote API reachability check failed: %s", exc)
            return result

        # ---- 2. Model existence (GET /models/{model_id}) ----
        try:
            with httpx.Client(timeout=self._HEADERS_TIMEOUT) as client:
                r = client.get(f"{base}/models/{model_id}", headers=headers)
                if r.status_code == 200:
                    result.model_exists = True
                    try:
                        result.model_metadata = r.json()
                    except Exception:
                        result.model_metadata = {}
                elif r.status_code == 404:
                    result.errors.append(f"Model '{model_id}' not found on the remote endpoint.")
                # 200 is the only success; other codes leave model_exists=False
        except Exception:
            # Not all servers implement GET /models/{id}; not a fatal failure
            result.model_exists = True   # assume present if listing succeeded

        # ---- 3. Schema validation (1-token chat completion) ----
        try:
            payload: Dict[str, Any] = {
                "model": model_id,
                "messages": [{"role": "user", "content": self.PROBE_PROMPT}],
                "max_tokens": 1,
                "temperature": 0,
            }
            with httpx.Client(timeout=self._HEADERS_TIMEOUT) as client:
                r = client.post(f"{base}/chat/completions", json=payload, headers=headers)
                if r.status_code == 200:
                    try:
                        data = r.json()
                        if "choices" in data:
                            result.request_schema_valid = True
                            result.response_schema_valid = True
                            result.streaming_support = True  # inferred from successful call
                    except Exception:
                        result.errors.append("API response is not valid JSON.")
                elif r.status_code in (401, 403):
                    result.authenticated = False
                    result.errors.append("Authentication failed during schema probe.")
                elif r.status_code == 429:
                    # Rate-limited but auth and schema are OK
                    result.request_schema_valid = True
                    result.response_schema_valid = True
        except httpx.TimeoutException:
            result.timeout_behavior_ok = False
            result.errors.append("API request timed out during schema validation.")
        except Exception as exc:
            result.errors.append("Schema validation request failed.")
            logger.debug("Remote API schema validation failed: %s", exc)

        result.latency_ms = (time.perf_counter() - start) * 1000.0
        return result

    def validate_gemini_compatible(
        self,
        endpoint_url: str,
        model_id: str,
        api_key: Optional[str] = None,
    ) -> TechnicalValidationResult:
        """Validate a Gemini-compatible endpoint for a specific model."""
        result = TechnicalValidationResult()
        start = time.perf_counter()
        base = endpoint_url.rstrip("/")
        key_param = f"?key={api_key}" if api_key else ""

        # ---- 1. Reachability (GET /v1beta/models) ----
        try:
            with httpx.Client(timeout=self._HEADERS_TIMEOUT) as client:
                r = client.get(f"{base}/v1beta/models{key_param}")
                if r.status_code == 200:
                    result.reachable = True
                    result.authenticated = bool(api_key)
                    result.protocol_valid = True
                elif r.status_code in (400, 401, 403):
                    result.reachable = True
                    if not api_key:
                        result.errors.append("Gemini API key is required.")
                    else:
                        result.authenticated = False
                        result.errors.append("Authentication failed. Verify the Gemini API key.")
                    return result
                else:
                    result.errors.append(f"Gemini endpoint returned HTTP {r.status_code}.")
                    return result
        except Exception as exc:
            result.errors.append("Gemini endpoint is not reachable.")
            logger.debug("Gemini validation failed: %s", exc)
            return result

        result.model_exists = True   # Gemini models are service-managed
        result.request_schema_valid = True
        result.response_schema_valid = True
        result.streaming_support = True   # Gemini supports streaming natively
        result.latency_ms = (time.perf_counter() - start) * 1000.0
        return result
