"""Tests for dynamic registry extension (adam/model/registry.py).

Verifies:
- Canonical models unchanged after dynamic registration
- Dynamic model appears in list_all() and list_dynamic()
- register_dynamic() never overwrites canonical models
- Duplicate discovery updates in-place (no duplicates)
- remove_dynamic() works correctly
- Backward compatibility: all existing ModelRegistry method signatures identical
- The new `source` and `attestation_status` fields have correct defaults
  (canonical models get "canonical" source, no attestation_status)
"""

import pytest
from adam.model.registry import (
    ModelRegistry,
    ModelArtifact,
    CANONICAL_MODELS,
    QWEN3_4B_INSTRUCT,
    QWEN3_1_7B_INSTRUCT,
    QWEN2_5_3B_INSTRUCT,
    GEMMA_3_4B_IT,
    LLAMA_3_2_3B_INSTRUCT,
)
from adam.vocabularies import LicenseStatus, ModelStatus


# ── Backward compatibility: canonical model defaults ────────────────────────

def test_canonical_models_have_source_canonical():
    """All canonical models must have source='canonical' by default."""
    for model_id, artifact in CANONICAL_MODELS.items():
        assert artifact.source == "canonical", (
            f"Canonical model {model_id} has source='{artifact.source}', expected 'canonical'"
        )


def test_canonical_models_have_no_attestation_status():
    """Canonical models should have attestation_status=None by default."""
    for model_id, artifact in CANONICAL_MODELS.items():
        assert artifact.attestation_status is None, (
            f"Canonical model {model_id} has unexpected attestation_status"
        )


def test_canonical_models_to_dict_includes_source():
    """to_dict() must include all new fields without breaking existing keys."""
    d = QWEN3_4B_INSTRUCT.to_dict()
    # Original required fields
    assert "id" in d
    assert "name" in d
    assert "license_status" in d
    assert "is_primary" in d
    # New additive fields
    assert "source" in d
    assert d["source"] == "canonical"
    assert "attestation_status" in d
    assert "capabilities" in d
    assert "display_group" in d


# ── ModelRegistry: existing methods unchanged ──────────────────────────────

def test_registry_get_primary_returns_qwen3():
    """get_primary() must return qwen3-4b-instruct-q4 (unchanged behaviour)."""
    registry = ModelRegistry()
    primary = registry.get_primary()
    assert primary.id == "qwen3-4b-instruct-q4"


def test_registry_get_fallback_returns_qwen3_1_7b():
    """get_fallback() must return qwen3-1.7b-instruct-q4 (unchanged behaviour)."""
    registry = ModelRegistry()
    fallback = registry.get_fallback()
    assert fallback.id == "qwen3-1.7b-instruct-q4"


def test_registry_list_all_includes_canonical():
    """list_all() must still contain all canonical models."""
    registry = ModelRegistry()
    ids = {m.id for m in registry.list_all()}
    for canonical_id in CANONICAL_MODELS:
        assert canonical_id in ids, f"Canonical model {canonical_id!r} missing from list_all()"


def test_registry_get_alias_resolution():
    """get() alias resolution for gemini and qwen variants remains intact."""
    registry = ModelRegistry()
    assert registry.get("gemini-2.0-flash") is not None
    assert registry.get("qwen2.5:3b") is not None


# ── register_dynamic() ────────────────────────────────────────────────────

def test_register_dynamic_adds_new_model():
    """A newly discovered model must appear in list_all() and list_dynamic()."""
    registry = ModelRegistry()
    original_count = len(registry.list_all())

    artifact = registry.register_dynamic(
        model_id="mistral:7b",
        display_name="Mistral 7B",
        provider="ollama",
        runtime="ollama",
        size_bytes=4_100_000_000,
        context_window=8192,
    )

    assert artifact.id == "mistral:7b"
    assert artifact.source == "discovered"
    assert artifact.display_group == "LOCAL"
    assert len(registry.list_all()) == original_count + 1
    assert any(m.id == "mistral:7b" for m in registry.list_dynamic())


def test_register_dynamic_does_not_overwrite_canonical():
    """register_dynamic() called with a canonical model ID must return the canonical artifact."""
    registry = ModelRegistry()
    canonical = QWEN3_4B_INSTRUCT

    result = registry.register_dynamic(
        model_id="qwen3-4b-instruct-q4",  # this is a canonical ID
        display_name="Should Be Ignored",
        provider="ollama",
        runtime="ollama",
    )

    assert result.name == canonical.name   # unchanged
    assert result.source == "canonical"    # still canonical
    assert result.is_primary is True       # canonical fields intact


def test_register_dynamic_idempotent_on_rediscovery():
    """Calling register_dynamic() twice for same model updates in-place without duplicates."""
    registry = ModelRegistry()
    registry.register_dynamic(
        model_id="phi3:mini",
        display_name="Phi-3 Mini",
        provider="ollama",
        runtime="ollama",
    )

    dynamic_before = len(registry.list_dynamic())

    # Second call — same model with new attestation data
    registry.register_dynamic(
        model_id="phi3:mini",
        display_name="Phi-3 Mini",
        provider="ollama",
        runtime="ollama",
        attestation_status="approved",
    )

    dynamic_after = len(registry.list_dynamic())
    assert dynamic_before == dynamic_after  # no new entry

    artifact = registry.get("phi3:mini")
    assert artifact is not None
    assert artifact.attestation_status == "approved"


def test_register_dynamic_with_attestation_data():
    """register_dynamic() stores attestation_status and capabilities correctly."""
    registry = ModelRegistry()
    artifact = registry.register_dynamic(
        model_id="zephyr:7b",
        display_name="Zephyr 7B",
        provider="ollama",
        runtime="ollama",
        attestation_status="limited",
        attestation_version="1",
        capabilities={"streaming": True, "hindi": False, "structured_output": True},
        display_group="LOCAL",
        provider_display="Ollama",
    )

    assert artifact.attestation_status == "limited"
    assert artifact.capabilities["streaming"] is True
    assert artifact.capabilities["hindi"] is False
    assert artifact.provider_display == "Ollama"


# ── remove_dynamic() ──────────────────────────────────────────────────────

def test_remove_dynamic_works():
    """remove_dynamic() removes a previously registered dynamic model."""
    registry = ModelRegistry()
    registry.register_dynamic(
        model_id="to_remove:model",
        display_name="To Remove",
        provider="ollama",
        runtime="ollama",
    )

    assert registry.remove_dynamic("to_remove:model") is True
    assert registry.get("to_remove:model") is None
    assert not any(m.id == "to_remove:model" for m in registry.list_dynamic())


def test_remove_dynamic_refuses_canonical():
    """remove_dynamic() must never remove a canonical model."""
    registry = ModelRegistry()
    result = registry.remove_dynamic("qwen3-4b-instruct-q4")
    assert result is False
    assert registry.get("qwen3-4b-instruct-q4") is not None


def test_remove_dynamic_nonexistent_returns_false():
    registry = ModelRegistry()
    assert registry.remove_dynamic("nonexistent:model") is False


# ── list_dynamic() ────────────────────────────────────────────────────────

def test_list_dynamic_excludes_canonical():
    """list_dynamic() must contain only discovered models, never canonical ones."""
    registry = ModelRegistry()
    registry.register_dynamic(
        model_id="dynamic:only",
        display_name="Dynamic Only",
        provider="ollama",
        runtime="ollama",
    )

    dynamic = registry.list_dynamic()
    canonical_ids = set(CANONICAL_MODELS.keys())
    for m in dynamic:
        assert m.id not in canonical_ids, f"Canonical model {m.id!r} appeared in list_dynamic()"


def test_list_dynamic_empty_by_default():
    """Fresh registry has no dynamic models."""
    registry = ModelRegistry()
    # Only canonical models exist; list_dynamic should be empty
    assert registry.list_dynamic() == []


# ── ModelArtifact dataclass backward compatibility ─────────────────────────

def test_model_artifact_default_source():
    """Creating a ModelArtifact without source defaults to 'canonical'."""
    art = ModelArtifact(
        id="test-model",
        name="Test",
        revision="1.0",
        quantization="Q4",
        model_format="gguf",
        checksum_sha256="abc123",
        file_size_bytes=1_000_000,
        license_id="Apache-2.0",
        license_status=LicenseStatus.APPROVED,
        requires_legal_review=False,
        context_window=4096,
        languages=["en"],
        serving_runtime="ollama",
        prompt_template="{user_prompt}",
    )
    assert art.source == "canonical"
    assert art.attestation_status is None
    assert art.capabilities == {}
