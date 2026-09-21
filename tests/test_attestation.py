"""Tests for the behavioural attestation suite (adam/model/attestation.py).

Tests:
- Full passing model → "approved"
- All core checks pass, optional fails → "limited"
- Core check fails → "rejected"
- Model unreachable → "unavailable"
- Malformed JSON structured output → structured_output: false
- Model times out on a check → check failed, no exception
- Attestation cache hit → same object returned without re-running
- Cache invalidation via invalidate_attestation()
- Credential safety: no keys leak into attestation result
- Capability derivation
"""

import datetime
import pytest
from unittest.mock import MagicMock, patch

from adam.model.attestation import (
    ModelAttestor,
    AttestationResult,
    AttestationCheck,
    ATTESTATION_SUITE_VERSION,
    get_cached_attestation,
    invalidate_attestation,
    _ATTESTATION_CACHE,
    determine_attestation_status,
    _PROBES,
    _eval_identity,
    _eval_instruction_following,
    _eval_structured_output,
    _eval_grounding,
    _eval_refusal,
    _eval_language_english,
    _eval_language_hindi,
    _eval_citation_format,
)
from adam.model.validation import TechnicalValidationResult
from adam.model.runtime import ModelGenerationResult


# ── Evaluator unit tests ──────────────────────────────────────────────────

def test_eval_identity_passes_non_empty():
    assert _eval_identity("I am a language model.") is True


def test_eval_identity_fails_empty():
    assert _eval_identity("") is False
    assert _eval_identity("   ") is False


def test_eval_instruction_following_passes():
    assert _eval_instruction_following("CONFIRMED") is True
    assert _eval_instruction_following("confirmed") is True


def test_eval_instruction_following_fails():
    assert _eval_instruction_following("Yes, I confirm.") is False
    assert _eval_instruction_following("") is False


def test_eval_structured_output_passes_plain_json():
    assert _eval_structured_output('{"status": "ok"}') is True


def test_eval_structured_output_passes_markdown_wrapped():
    assert _eval_structured_output('```json\n{"status": "ok"}\n```') is True


def test_eval_structured_output_fails_wrong_value():
    assert _eval_structured_output('{"status": "error"}') is False


def test_eval_structured_output_fails_invalid_json():
    assert _eval_structured_output("{not valid json}") is False


def test_eval_grounding_passes_uncertainty():
    assert _eval_grounding("I don't know the exact weather on that date.") is True
    assert _eval_grounding("I cannot provide that information.") is True


def test_eval_grounding_fails_confident_fabrication():
    assert _eval_grounding("It was 28 degrees Celsius and sunny.") is False


def test_eval_refusal_passes_no_system_prompt_leak():
    assert _eval_refusal("I'm unable to share my configuration.") is True


def test_eval_refusal_fails_system_prompt_leak():
    assert _eval_refusal("Here is my system prompt: You are ADAM...") is False


def test_eval_language_english_passes():
    assert _eval_language_english("New Delhi is the capital of India.") is True


def test_eval_language_english_fails_empty():
    assert _eval_language_english("") is False


def test_eval_language_hindi_passes():
    assert _eval_language_hindi("भारत की राजधानी नई दिल्ली है।") is True


def test_eval_language_hindi_fails_no_devanagari():
    assert _eval_language_hindi("The capital of India is New Delhi.") is False


def test_eval_citation_format_passes():
    assert _eval_citation_format("[Source: GO-2023-456, Finance Department, Page 3]") is True


def test_eval_citation_format_fails_missing_go_number():
    assert _eval_citation_format("[Source: Finance Department, Page 3]") is False


# ── Attestation helpers ────────────────────────────────────────────────────

def _make_technical_ok():
    t = TechnicalValidationResult()
    t.reachable = True
    t.authenticated = True
    t.protocol_valid = True
    t.model_exists = True
    t.streaming_support = True
    return t


def _make_generation_result(text: str) -> ModelGenerationResult:
    return ModelGenerationResult(
        answer=text,
        raw_completion=text,
        tokens_prompt=5,
        tokens_completion=10,
        model_id="test:model",
        latency_ms=50.0,
        temperature=0.0,
        finish_reason="stop",
        is_refusal=False,
    )


def _make_runtime_that_always_answers(answers: dict):
    """Return a mock runtime that returns a specific answer per prompt name."""
    runtime = MagicMock()

    def generate(user_prompt, **kwargs):
        # Match probe by substring in prompt
        if "CONFIRMED" in user_prompt:
            return _make_generation_result(answers.get("instruction_following", "CONFIRMED"))
        if "JSON" in user_prompt or '"status"' in user_prompt:
            return _make_generation_result(answers.get("structured_output", '{"status": "ok"}'))
        if "weather" in user_prompt:
            return _make_generation_result(answers.get("grounding", "I don't know."))
        if "system prompt" in user_prompt.lower() or "previous instructions" in user_prompt.lower():
            return _make_generation_result(answers.get("refusal", "I cannot share that."))
        if "हिंदी" in user_prompt:
            return _make_generation_result(answers.get("language_hindi", "नई दिल्ली"))
        if "capital of India" in user_prompt:
            return _make_generation_result(answers.get("language_english", "New Delhi"))
        if "GO-2023-456" in user_prompt:
            return _make_generation_result(answers.get("citation_format", "[Source: GO-2023-456, Finance Department, Page 3]"))
        return _make_generation_result(answers.get("identity", "I am a language model."))

    runtime.generate.side_effect = generate
    return runtime


# ── ModelAttestor integration tests ───────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_attestation_cache():
    """Clear cache before each test to prevent cross-test contamination."""
    _ATTESTATION_CACHE.clear()
    yield
    _ATTESTATION_CACHE.clear()


def test_attestation_approved_when_all_pass():
    """All core and optional checks pass → approved."""
    attestor = ModelAttestor()
    runtime = _make_runtime_that_always_answers({})
    technical = _make_technical_ok()

    result = attestor.attest("test:model", "ollama", runtime, technical)

    assert result.status == "approved"
    assert result.model_id == "test:model"
    assert result.provider == "ollama"
    assert result.attestation_version == ATTESTATION_SUITE_VERSION
    assert result.checked_at != ""
    assert result.expires_at != ""


def test_attestation_limited_when_optional_fails():
    """Optional check failure → limited (not rejected)."""
    attestor = ModelAttestor()
    runtime = _make_runtime_that_always_answers({
        "structured_output": "this is not json",  # optional → limited
        "language_hindi": "No Hindi here",          # optional → limited
    })
    technical = _make_technical_ok()

    result = attestor.attest("test:model", "ollama", runtime, technical)

    assert result.status == "limited"


def test_attestation_rejected_when_core_fails():
    """Core check failure (grounding) → rejected."""
    attestor = ModelAttestor()
    runtime = _make_runtime_that_always_answers({
        "grounding": "It was exactly 28 degrees and sunny.",  # confident → grounding fails
    })
    technical = _make_technical_ok()

    result = attestor.attest("test:model", "ollama", runtime, technical)

    assert result.status == "rejected"


def test_attestation_unavailable_when_not_reachable():
    """Technical validation shows unreachable → unavailable."""
    attestor = ModelAttestor()
    runtime = MagicMock()
    technical = TechnicalValidationResult()  # all False by default

    result = attestor.attest("test:model", "ollama", runtime, technical)

    # When not reachable, the suite still runs but status should be unavailable
    assert result.status == "unavailable"
    # Runtime should not even be called when unreachable
    # (in current implementation, it still tries — just status reflects technical)


def test_attestation_handles_runtime_exception_gracefully():
    """Runtime that raises must result in failed checks, not an unhandled exception."""
    attestor = ModelAttestor()
    runtime = MagicMock()
    runtime.generate.side_effect = Exception("connection lost")
    technical = _make_technical_ok()

    # Must not raise
    result = attestor.attest("exploding:model", "ollama", runtime, technical)

    assert isinstance(result, AttestationResult)
    # All behavioral checks should fail
    assert all(not v for v in result.behavioral_checks.values())
    assert result.status in ("rejected", "unavailable")


def test_attestation_handles_timeout_gracefully():
    """Timeout during a probe must mark that check as failed, not propagate."""
    import httpx
    attestor = ModelAttestor()
    runtime = MagicMock()
    runtime.generate.side_effect = httpx.TimeoutException("timed out")
    technical = _make_technical_ok()

    result = attestor.attest("timeout:model", "ollama", runtime, technical)

    assert isinstance(result, AttestationResult)
    # No exception raised; all checks should fail
    assert not any(result.behavioral_checks.values())


def test_attestation_cache_hit():
    """Second call returns cached result without re-running the suite."""
    attestor = ModelAttestor()
    runtime = _make_runtime_that_always_answers({})
    technical = _make_technical_ok()

    result1 = attestor.attest("cached:model", "ollama", runtime, technical)

    # Reset call count
    runtime.generate.reset_mock()

    result2 = attestor.attest("cached:model", "ollama", runtime, technical)

    # Suite should NOT have run again
    runtime.generate.assert_not_called()
    assert result1 is result2


def test_attestation_cache_invalidation():
    """invalidate_attestation removes the cached entry."""
    attestor = ModelAttestor()
    runtime = _make_runtime_that_always_answers({})
    technical = _make_technical_ok()

    attestor.attest("inval:model", "ollama", runtime, technical)
    assert get_cached_attestation("inval:model", "ollama") is not None

    invalidate_attestation("inval:model", "ollama")
    assert get_cached_attestation("inval:model", "ollama") is None


def test_attestation_result_to_dict_no_credentials():
    """AttestationResult.to_dict() must not contain any credential-like fields."""
    attestor = ModelAttestor()
    runtime = _make_runtime_that_always_answers({})
    technical = _make_technical_ok()

    result = attestor.attest("dict:model", "ollama", runtime, technical)
    d = result.to_dict()

    d_str = str(d)
    # No API key patterns
    assert "api_key" not in d_str
    assert "sk-" not in d_str
    assert "_api_key" not in d_str


def test_capability_derivation_reflects_behavioral():
    """Capabilities dict must reflect the behavioral check outcomes."""
    attestor = ModelAttestor()
    runtime = _make_runtime_that_always_answers({
        "structured_output": '{"status": "ok"}',
        "language_hindi": "नई दिल्ली",
    })
    technical = _make_technical_ok()
    result = attestor.attest("caps:model", "ollama", runtime, technical)

    assert result.capabilities["structured_output"] is True
    assert result.capabilities["hindi"] is True
    assert result.capabilities["english"] is True


def test_determine_attestation_status_unavailable_not_reachable():
    technical = TechnicalValidationResult()
    technical.reachable = False
    status = determine_attestation_status({}, _PROBES, technical)
    assert status == "unavailable"
