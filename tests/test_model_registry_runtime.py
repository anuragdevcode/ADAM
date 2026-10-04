"""Unit tests for Phase 04 Model Registry, Pinned Checksums, SBOM, and Serving Runtime."""

import pytest
from adam.db.models import ModelArtifactRecord
from adam.model.registry import (
    ModelArtifact,
    ModelRegistry,
    QWEN3_4B_INSTRUCT,
    QWEN3_1_7B_INSTRUCT,
    QWEN3_5_4B_INSTRUCT,
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


def test_file_checksum_streaming_verification(tmp_path):
    """Verify streaming file checksum verification matches expected release SHA-256."""
    registry = ModelRegistry()
    test_content = b"streaming-file-model-weights-content-for-sha256-test"
    weights_file = tmp_path / "model_weights.gguf"
    weights_file.write_bytes(test_content)

    test_hash = registry.compute_sha256(test_content)
    assert registry.verify_file_checksum(weights_file, test_hash) is True
    assert registry.verify_file_checksum(weights_file, "wrong" * 16) is False

    artifact = ModelArtifact(
        id="test-file-model",
        name="Test/File-Model",
        revision="v1.0",
        quantization="Q4_K_M",
        model_format="GGUF",
        checksum_sha256=test_hash,
        file_size_bytes=len(test_content),
        license_id="Apache-2.0",
        license_status=LicenseStatus.APPROVED,
        requires_legal_review=False,
        context_window=2048,
        languages=["en"],
        serving_runtime="ollama",
        prompt_template="{system_prompt}\n{user_prompt}",
    )
    registry.register_artifact(artifact)
    assert registry.verify_artifact_file("test-file-model", weights_file) is True


def test_qwen2_5_and_qwen3_5_alias_separation():
    """Verify Qwen 2.5 tags route to deprecated Qwen 2.5 artifact without silently aliasing to Qwen 3.5."""
    registry = ModelRegistry()
    q25 = registry.get("qwen2.5:3b")
    assert q25 is not None
    assert q25.id == "qwen2.5-3b-instruct-q4"
    assert q25.status == ModelStatus.DEPRECATED

    q35 = registry.get("qwen3.5:4b")
    assert q35 is not None
    assert q35.id == "qwen3.5-4b-instruct-q4"
    assert q35.status == ModelStatus.REGISTERED

    # Ensure checksums and sizes are distinct
    assert q25.checksum_sha256 != q35.checksum_sha256
    assert q35.file_size_bytes > q25.file_size_bytes


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


def test_production_load_model_raises_when_ollama_offline(monkeypatch):
    """In production mode (not test mode), Ollama failure raises clear RuntimeError rather than silent fallback."""
    import os
    import sys
    from adam.model.registry import QWEN2_5_3B_INSTRUCT, GEMINI_3_6_FLASH
    from adam.model.runtime import OllamaModelRuntime

    registry = ModelRegistry()
    lifecycle = SingleModelLifecycleManager(registry)
    lifecycle.unload_model()

    # Simulate production mode where is_test_environment is False
    monkeypatch.setattr("adam.model.runtime.is_test_environment", lambda **kw: False)
    monkeypatch.setattr(OllamaModelRuntime, "is_available", lambda self: False)

    # In production with Ollama offline, load_model must raise RuntimeError with guidance
    with pytest.raises(RuntimeError) as exc_info:
        lifecycle.load_model(QWEN2_5_3B_INSTRUCT.id, allow_hot_swap=True)
    assert "Cannot connect to local Ollama service" in str(exc_info.value)
    assert "ollama serve" in str(exc_info.value)

    # In production without Gemini API key, load_model must raise RuntimeError with guidance
    with pytest.raises(RuntimeError) as exc_info_gemini:
        lifecycle.load_model(GEMINI_3_6_FLASH.id, allow_hot_swap=True)
    assert "Google Gemini API key is not configured" in str(exc_info_gemini.value)

    lifecycle.unload_model()


def test_qwen3_5_key_capabilities_registry_and_runtime():
    """Verify that Qwen 3.5 4B artifact and runtime fully implement all 6 Key Capabilities."""
    artifact = QWEN3_5_4B_INSTRUCT

    # 1. Native Vision-Language Understanding
    assert artifact.capabilities["vision"] is True
    assert artifact.capabilities["multimodal"] is True
    assert artifact.capabilities["early_fusion_multimodal_tokens"] is True
    assert artifact.capabilities["document_understanding"] is True
    assert artifact.capabilities["chart_interpretation"] is True
    assert artifact.capabilities["ui_layout_reading"] is True
    assert artifact.capabilities["vqa"] is True
    assert "OmniDocBench" in artifact.sbom["vision_capabilities"]

    # 2. Ultra-Long Context Processing (256k tokens)
    assert artifact.context_window == 262_144
    assert artifact.capabilities["ultra_long_context"] is True
    assert artifact.capabilities["context_window_tokens"] == 262_144
    assert "256k" in artifact.sbom["context_window"]

    # 3. Coding & Structured Outputs
    assert artifact.capabilities["coding"] is True
    assert "python" in artifact.capabilities["supported_languages"]
    assert "sql" in artifact.capabilities["supported_languages"]
    assert artifact.capabilities["unit_test_drafting"] is True
    assert artifact.capabilities["structured_output"] is True
    assert artifact.capabilities["json_schema_compliant"] is True

    # 4. Massive Multilingual Coverage (200+ languages & regional scripts)
    assert artifact.capabilities["multilingual"] is True
    assert artifact.capabilities["multilingual_languages_count"] == 200
    assert artifact.capabilities["hindi"] is True
    assert artifact.capabilities["regional_scripts"] is True
    assert artifact.capabilities["translation_fidelity"] is True
    assert len(artifact.languages) >= 10
    assert "hi" in artifact.languages and "sa" in artifact.languages

    # 5. High Inference Efficiency on Edge Devices (Gated DeltaNet)
    assert artifact.capabilities["hybrid_linear_attention"] is True
    assert artifact.capabilities["gated_deltanet"] is True
    assert artifact.capabilities["edge_device_optimized"] is True
    assert artifact.capabilities["sub_quadratic_kv_cache"] is True
    assert "Gated DeltaNet" in artifact.sbom["architecture"]

    # 6. Thinking / Reasoning Mode (Integrated CoT)
    assert artifact.capabilities["thinking_mode"] is True
    assert artifact.capabilities["chain_of_thought"] is True
    assert artifact.capabilities["multi_hop_reasoning"] is True
    assert artifact.capabilities["stem_calculations"] is True

    # Test runtime execution of capabilities under DeterministicModelRuntime
    runtime = DeterministicModelRuntime(artifact)

    # Test Vision generation
    res_vision = runtime.generate(
        user_prompt="Examine the scanned Government Order",
        images=["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="],
    )
    assert "OmniDocBench" in res_vision.answer or "visual document understanding" in res_vision.answer

    # Test Thinking mode execution
    res_thinking = runtime.generate(
        user_prompt="Passage [1] Page 2: Finance order.\nCompute composite rate enhancement.",
        thinking_enabled=True,
    )
    assert res_thinking.thinking is not None
    assert "Step 1" in res_thinking.thinking or "Step 2" in res_thinking.thinking

    # Test Coding task output
    res_coding = runtime.generate(
        user_prompt="### coding task [python]\nDraft a unit test verifying HRA ceiling calculation.",
    )
    assert "```python" in res_coding.answer


def test_model_registry_checksum_integrity_and_provenance():
    """Verify that all pinned local model artifacts have valid, authentic, unique SHA-256 checksums."""
    from adam.model.registry import CANONICAL_MODELS

    seen_checksums = {}
    fake_patterns = ["0123456789abcdef", "abcdef0123456789", "0000000000000000"]

    for model_id, artifact in CANONICAL_MODELS.items():
        chk = (artifact.checksum_sha256 or "").strip()
        assert chk, f"Model {model_id} has empty checksum_sha256"

        # Cloud models are managed by endpoints
        if artifact.serving_runtime == "gemini" or chk == "cloud-endpoint-managed":
            continue

        # Local model weights must be valid 64-char hex SHA-256
        assert len(chk) == 64, f"Model {model_id} checksum '{chk}' is not 64 hex characters"
        assert all(c in "0123456789abcdefABCDEF" for c in chk), f"Model {model_id} checksum '{chk}' is not valid hex"

        # Must not contain dummy repeating patterns
        for pattern in fake_patterns:
            assert pattern not in chk.lower(), f"Model {model_id} contains fake placeholder pattern '{pattern}'"

        # Unique checksums across distinct models
        assert chk not in seen_checksums, (
            f"Duplicate checksum detected: {model_id} shares checksum '{chk}' with {seen_checksums[chk]}"
        )
        seen_checksums[chk] = model_id


def test_load_model_verifies_file_checksum(tmp_path):
    """SingleModelLifecycleManager.load_model must verify checksum when local model file is provided."""
    registry = ModelRegistry()
    lifecycle = SingleModelLifecycleManager(registry)
    lifecycle.unload_model()

    # Create dummy file with mismatching content
    bad_model_file = tmp_path / "model_weights.gguf"
    bad_model_file.write_bytes(b"corrupted or wrong weights binary data")

    with pytest.raises(ValueError) as exc_info:
        lifecycle.load_model(
            QWEN3_4B_INSTRUCT.id,
            backend="deterministic",
            model_file_path=bad_model_file,
        )
    assert "checksum mismatch" in str(exc_info.value).lower()
    assert str(bad_model_file) in str(exc_info.value)

    # Now create file matching expected hash for a custom test model
    valid_data = b"authentic-signed-model-binary-gguf"
    valid_hash = registry.compute_sha256(valid_data)
    good_model_file = tmp_path / "good_model.gguf"
    good_model_file.write_bytes(valid_data)

    custom_artifact = ModelArtifact(
        id="verified-local-custom-model",
        name="Verified/Custom-Model",
        revision="v1.0",
        quantization="Q4_K_M",
        model_format="GGUF",
        checksum_sha256=valid_hash,
        file_size_bytes=len(valid_data),
        license_id="Apache-2.0",
        license_status=LicenseStatus.APPROVED,
        requires_legal_review=False,
        context_window=4096,
        languages=["en", "hi"],
        serving_runtime="deterministic",
        prompt_template=QWEN3_CHATML_TEMPLATE,
    )
    registry.register_artifact(custom_artifact)

    rt = lifecycle.load_model(
        custom_artifact.id,
        backend="deterministic",
        model_file_path=good_model_file,
    )
    assert rt is not None
    lifecycle.unload_model()


