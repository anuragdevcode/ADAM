"""Unit tests for Phase 04 Model Registry, Pinned Checksums, SBOM, and Serving Runtime."""

import pytest
from adam.db.models import ModelArtifactRecord
from adam.model.registry import (
    ModelArtifact,
    ModelRegistry,
    QWEN3_4B_INSTRUCT,
    QWEN3_1_7B_INSTRUCT,
    GEMMA_3_4B_IT,
    LLAMA_3_2_3B_INSTRUCT,
    QWEN3_CHATML_TEMPLATE,
)
from adam.model.runtime import (
    BaseModelRuntime,
    DeterministicModelRuntime,
    SingleModelLifecycleManager,
    ConcurrentModelLoadError,
    TemperatureOutOfBoundsError,
)
from adam.vocabularies import LicenseStatus, ModelStatus


def test_canonical_models_specifications():
    """Verify that all canonical model specifications conform to Phase 04 requirements."""
    # 1. Primary Model: Qwen3-4B Instruct
    assert QWEN3_4B_INSTRUCT.id == "qwen3-4b-instruct-q4"
    assert QWEN3_4B_INSTRUCT.quantization == "Q4_K_M"
    assert QWEN3_4B_INSTRUCT.license_id == "Apache-2.0"
    assert QWEN3_4B_INSTRUCT.license_status == LicenseStatus.APPROVED
    assert QWEN3_4B_INSTRUCT.is_primary is True
    assert QWEN3_4B_INSTRUCT.is_fallback is False
    assert 2.5 * 1024**3 <= QWEN3_4B_INSTRUCT.file_size_bytes <= 3.5 * 1024**3
    assert "en" in QWEN3_4B_INSTRUCT.languages and "hi" in QWEN3_4B_INSTRUCT.languages
    assert "vendor" in QWEN3_4B_INSTRUCT.sbom

    # 2. Fallback Model: Qwen3-1.7B Instruct
    assert QWEN3_1_7B_INSTRUCT.id == "qwen3-1.7b-instruct-q4"
    assert QWEN3_1_7B_INSTRUCT.quantization == "Q4_K_M"
    assert QWEN3_1_7B_INSTRUCT.license_id == "Apache-2.0"
    assert QWEN3_1_7B_INSTRUCT.is_fallback is True
    assert QWEN3_1_7B_INSTRUCT.is_primary is False

    # 3. Evaluation Comparator: Gemma 3 4B
    assert GEMMA_3_4B_IT.id == "gemma-3-4b-it-q4"
    assert GEMMA_3_4B_IT.license_status == LicenseStatus.GATED_PENDING_REVIEW
    assert GEMMA_3_4B_IT.requires_legal_review is True
    assert GEMMA_3_4B_IT.is_comparator is True

    # 4. Comparator: Llama 3.2 3B
    assert LLAMA_3_2_3B_INSTRUCT.license_status == LicenseStatus.RESTRICTED
    assert LLAMA_3_2_3B_INSTRUCT.requires_legal_review is True


def test_model_registry_db_persistence(db_session):
    """Verify registration, retrieval, and DB seeding of release artifacts."""
    registry = ModelRegistry(db_session)
    count = registry.seed_defaults()
    assert count >= 4

    primary = registry.get_primary()
    assert primary.id == QWEN3_4B_INSTRUCT.id

    fallback = registry.get_fallback()
    assert fallback.id == QWEN3_1_7B_INSTRUCT.id
    assert fallback.file_size_bytes == QWEN3_1_7B_INSTRUCT.file_size_bytes
    assert primary.file_size_bytes == QWEN3_4B_INSTRUCT.file_size_bytes

    gemma = registry.get(GEMMA_3_4B_IT.id)
    assert gemma is not None
    assert gemma.is_comparator is True

    # Verify DB records exist
    records = db_session.query(ModelArtifactRecord).all()
    assert len(records) >= 4
    model_ids = {r.id for r in records}
    assert QWEN3_4B_INSTRUCT.id in model_ids
    assert GEMMA_3_4B_IT.id in model_ids

    gemma_rec = db_session.query(ModelArtifactRecord).filter_by(id=GEMMA_3_4B_IT.id).first()
    assert bool(gemma_rec.is_comparator) is True
    fallback_rec = db_session.query(ModelArtifactRecord).filter_by(id=QWEN3_1_7B_INSTRUCT.id).first()
    assert fallback_rec.file_size_bytes == QWEN3_1_7B_INSTRUCT.file_size_bytes


def test_checksum_verification():
    """Verify SHA-256 release checksum verification logic."""
    registry = ModelRegistry()
    test_bytes = b"pinned-model-weights-binary-representation"
    test_hash = registry.compute_sha256(test_bytes)

    custom_model = ModelArtifact(
        id="custom-test-model",
        name="Custom/Test-Model",
        revision="v1.0",
        quantization="Q4_K_M",
        model_format="GGUF",
        checksum_sha256=test_hash,
        file_size_bytes=1000,
        license_id="Apache-2.0",
        license_status=LicenseStatus.APPROVED,
        requires_legal_review=False,
        context_window=2048,
        languages=["en"],
        serving_runtime="llamacpp",
        prompt_template="{system_prompt}\n{user_prompt}",
    )
    registry.register_artifact(custom_model)

    assert registry.verify_checksum("custom-test-model", test_bytes) is True
    assert registry.verify_checksum("custom-test-model", b"tampered-bytes") is False


def test_single_model_concurrent_load_enforcement():
    """Enforce: 'Do not load multiple LLMs concurrently.'"""
    registry = ModelRegistry()
    lifecycle = SingleModelLifecycleManager(registry)
    lifecycle.unload_model()  # Ensure clean starting state

    # 1. Load primary model
    runtime1 = lifecycle.load_model(QWEN3_4B_INSTRUCT.id)
    assert lifecycle.is_loaded is True
    assert lifecycle.active_model_id == QWEN3_4B_INSTRUCT.id

    # 2. Attempting to load another model without hot swap raises ConcurrentModelLoadError
    with pytest.raises(ConcurrentModelLoadError) as exc_info:
        lifecycle.load_model(QWEN3_1_7B_INSTRUCT.id, allow_hot_swap=False)
    assert "Concurrent LLM loading is strictly prohibited" in str(exc_info.value)

    # 3. Loading with hot swap safely unloads previous model first
    runtime2 = lifecycle.load_model(QWEN3_1_7B_INSTRUCT.id, allow_hot_swap=True)
    assert lifecycle.active_model_id == QWEN3_1_7B_INSTRUCT.id
    assert runtime1.is_loaded is False
    assert runtime2.is_loaded is True

    # 4. Clean unload
    lifecycle.unload_model()
    assert lifecycle.is_loaded is False
    assert lifecycle.active_model_id is None


def test_temperature_and_token_bounds():
    """Verify temperature enforcement [0.0, 0.2] and token limit clamping."""
    runtime = DeterministicModelRuntime(QWEN3_4B_INSTRUCT)

    # Valid temperatures within bounds
    assert runtime.validate_temperature(0.0) == 0.0
    assert runtime.validate_temperature(0.15) == 0.15
    assert runtime.validate_temperature(0.20) == 0.20

    # Temperatures exceeding bounds raise TemperatureOutOfBoundsError
    with pytest.raises(TemperatureOutOfBoundsError):
        runtime.validate_temperature(0.25)

    with pytest.raises(TemperatureOutOfBoundsError):
        runtime.validate_temperature(-0.05)

    with pytest.raises(TemperatureOutOfBoundsError):
        runtime.validate_temperature(1.0)

    # Output schema verification
    result = runtime.generate(
        user_prompt="### Evidence Passage [Page 1]:\nOfficial order UK/2024/01 details.",
        temperature=0.1,
        max_tokens=64,
    )
    assert result.applied_schema == "ADAM_GOVERNANCE_V1"
    assert result.temperature == 0.1
    assert result.model_id == QWEN3_4B_INSTRUCT.id
    assert result.tokens_completion <= 64


def test_ollama_runtime_bilingual_refusals_and_eviction(monkeypatch):
    """Verify OllamaModelRuntime handles English/Hindi refusals and evicts memory via keep_alive: 0."""
    from adam.model.runtime import OllamaModelRuntime
    import httpx

    calls = []

    def mock_post(self, url, **kwargs):
        calls.append((url, kwargs.get("json", {})))
        if "/api/chat" in url:
            messages = kwargs.get("json", {}).get("messages", [])
            user_msg = messages[-1]["content"] if messages else ""
            if "hindi_refusal" in user_msg:
                content = "अनुमोदित रिपॉजिटरी से यह स्थापित नहीं किया जा सका।"
            elif "outside" in user_msg:
                content = "This request falls outside the Uttarakhand public records jurisdiction."
            else:
                content = "Based on official records, the basic pay verification is complete."

            return httpx.Response(
                status_code=200,
                json={
                    "message": {"content": content},
                    "prompt_eval_count": 50,
                    "eval_count": 25,
                },
                request=httpx.Request("POST", url),
            )
        elif "/api/generate" in url:
            # Memory eviction call
            return httpx.Response(status_code=200, json={}, request=httpx.Request("POST", url))
        return httpx.Response(status_code=404, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    runtime = OllamaModelRuntime(QWEN3_4B_INSTRUCT)

    # 1. English refusal test
    res_en = runtime.generate(user_prompt="outside boundary request")
    assert res_en.is_refusal is True
    assert res_en.refusal_category == "OUT_OF_JURISDICTION"

    # 2. Hindi refusal test
    res_hi = runtime.generate(user_prompt="hindi_refusal query")
    assert res_hi.is_refusal is True
    assert res_hi.refusal_category == "ZERO_EVIDENCE"

    # 3. Successful non-refusal test
    res_ok = runtime.generate(user_prompt="normal query")
    assert res_ok.is_refusal is False
    assert res_ok.refusal_category is None

    # 4. Memory eviction on unload
    runtime.unload()
    assert any(url == "/api/generate" and payload.get("keep_alive") == 0 for url, payload in calls)


def test_lifecycle_backend_switching_and_serving_runtime_resolution(monkeypatch):
    """Verify SingleModelLifecycleManager resolves serving_runtime and switches backends cleanly."""
    from adam.model.registry import QWEN2_5_3B_INSTRUCT
    from adam.model.runtime import OllamaModelRuntime

    registry = ModelRegistry()
    lifecycle = SingleModelLifecycleManager(registry)
    lifecycle.unload_model()

    # Mock Ollama availability
    monkeypatch.setattr(OllamaModelRuntime, "is_available", lambda self: True)
    monkeypatch.setattr(OllamaModelRuntime, "is_model_present", lambda self: True)

    # 1. Automatic resolution from artifact.serving_runtime='ollama'
    rt_ollama = lifecycle.load_model(QWEN2_5_3B_INSTRUCT.id)
    assert isinstance(rt_ollama, OllamaModelRuntime)

    # 2. Explicit switch to deterministic
    rt_det = lifecycle.load_model(QWEN2_5_3B_INSTRUCT.id, backend="deterministic")
    assert isinstance(rt_det, DeterministicModelRuntime)

    # 3. Hot swap back to ollama
    rt_ollama2 = lifecycle.load_model(QWEN2_5_3B_INSTRUCT.id, backend="ollama")
    assert isinstance(rt_ollama2, OllamaModelRuntime)

    lifecycle.unload_model()
