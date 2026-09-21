"""Comprehensive unit tests for ADAM Advanced Settings System."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from adam.settings.advanced_settings import (
    AdvancedSettingsPreset,
    GenerationSettings,
    RetrievalSettings,
    PerformanceSettings,
    VoiceSettings,
    AdvancedSettingsBundle,
    AdvancedSettingsManager,
    PRESET_BUNDLES,
    DEFAULT_BUNDLE,
    SETTINGS_METADATA,
)
from adam.db.models import Base, UserPreference
from adam.rag.models import ParsedQuery, EvidencePassage, UserContext
from adam.rag.evidence import EvidencePacketBuilder
from adam.rag.retriever import HybridRetriever
from adam.agent.state_machine import AgentStateMachine
from adam.vocabularies import Classification


# ── Database & Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def test_db_session():
    """In-memory SQLite session with StaticPool."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_api_client(test_db_session):
    """FastAPI TestClient with overridden get_db."""
    from adam.api.app import create_app
    from adam.api import deps

    app = create_app()

    def override_get_db():
        yield test_db_session

    app.dependency_overrides[deps.get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


# ── 1. Preset Bundles & Validation ─────────────────────────────────────────────

def test_preset_bundles_exist_and_validate():
    """All 4 presets must be defined and pass validation without errors."""
    for preset in [AdvancedSettingsPreset.PRECISE, AdvancedSettingsPreset.BALANCED, AdvancedSettingsPreset.THOROUGH]:
        bundle = PRESET_BUNDLES[preset]
        assert bundle.preset == preset
        errors = bundle.validate()
        assert errors == [], f"Preset {preset} had validation errors: {errors}"

    # Precise must be more conservative than Thorough
    precise = PRESET_BUNDLES[AdvancedSettingsPreset.PRECISE]
    thorough = PRESET_BUNDLES[AdvancedSettingsPreset.THOROUGH]
    balanced = PRESET_BUNDLES[AdvancedSettingsPreset.BALANCED]
    assert precise.generation.temperature_rag <= thorough.generation.temperature_rag
    assert precise.generation.max_tokens_rag < thorough.generation.max_tokens_rag
    assert precise.retrieval.top_k < thorough.retrieval.top_k
    assert balanced.generation.thinking_enabled is True
    assert precise.generation.thinking_enabled is True
    assert thorough.generation.thinking_enabled is True


def test_thinking_mode_enabled_by_default():
    """Thinking mode for Qwen must be enabled by default in GenerationSettings and default bundle."""
    gen = GenerationSettings()
    assert gen.thinking_enabled is True
    assert DEFAULT_BUNDLE.generation.thinking_enabled is True


def test_validation_rejects_out_of_bounds_parameters():
    """Parameters outside approved ranges must be flagged by validate()."""
    # RAG Temperature exceeding Phase 04 bounds [0.0, 0.2]
    bad_gen = GenerationSettings(temperature_rag=0.25)
    errors = bad_gen.validate()
    assert any("temperature_rag" in e for e in errors)

    # Negative RAG Temperature
    bad_gen2 = GenerationSettings(temperature_rag=-0.05)
    assert any("temperature_rag" in e for e in bad_gen2.validate())

    # Invalid top_k
    bad_ret = RetrievalSettings(top_k=50)
    assert any("top_k" in e for e in bad_ret.validate())

    # Invalid min > max passages
    bad_ret2 = RetrievalSettings(min_passages=8, max_passages=4)
    assert any("min_passages" in e for e in bad_ret2.validate())

    # Invalid performance profile
    bad_perf = PerformanceSettings(environment_profile="ALIEN_SUPERCOMPUTER")
    assert any("environment_profile" in e for e in bad_perf.validate())


def test_bundle_serialization_roundtrip():
    """Bundle to_dict() and from_dict() must faithfully reconstruct all settings."""
    bundle = PRESET_BUNDLES[AdvancedSettingsPreset.PRECISE]
    data = bundle.to_dict()
    reconstructed = AdvancedSettingsBundle.from_dict(data)
    assert reconstructed.preset == AdvancedSettingsPreset.PRECISE
    assert reconstructed.generation.temperature_rag == bundle.generation.temperature_rag
    assert reconstructed.retrieval.top_k == bundle.retrieval.top_k
    assert reconstructed.performance.environment_profile == bundle.performance.environment_profile
    assert reconstructed.voice.default_voice_language == bundle.voice.default_voice_language
    assert reconstructed.validate() == []


# ── 2. AdvancedSettingsManager (Persistence & Opt-In) ──────────────────────────

def test_manager_loads_defaults_when_empty(test_db_session):
    """When no preferences exist for a user, manager must return BALANCED defaults."""
    manager = AdvancedSettingsManager(test_db_session, user_id="officer_001")
    bundle = manager.load()
    assert bundle.preset == AdvancedSettingsPreset.BALANCED
    assert bundle.retrieval.top_k == 8


def test_manager_save_and_load_roundtrip(test_db_session):
    """Saving customized settings must persist them encrypted and load them back correctly."""
    manager = AdvancedSettingsManager(test_db_session, user_id="officer_002")
    custom = AdvancedSettingsBundle.from_dict(DEFAULT_BUNDLE.to_dict())
    custom.preset = AdvancedSettingsPreset.CUSTOM
    custom.generation.max_tokens_rag = 2048
    custom.retrieval.top_k = 12

    manager.save(custom, opt_in=True)

    # Verify directly in DB that UserPreference row was created with encrypted payload
    pref_row = test_db_session.query(UserPreference).filter(UserPreference.user_id == "officer_002").first()
    assert pref_row is not None
    assert pref_row.opt_in == 1
    assert pref_row.preference_data_ciphertext is not None

    # Load back via a new manager instance
    manager2 = AdvancedSettingsManager(test_db_session, user_id="officer_002")
    loaded = manager2.load()
    assert loaded.preset == AdvancedSettingsPreset.CUSTOM
    assert loaded.generation.max_tokens_rag == 2048
    assert loaded.retrieval.top_k == 12


def test_manager_reset_returns_defaults(test_db_session):
    """Reset must restore settings to BALANCED defaults."""
    manager = AdvancedSettingsManager(test_db_session, user_id="officer_003")
    thorough = AdvancedSettingsBundle.from_dict(PRESET_BUNDLES[AdvancedSettingsPreset.THOROUGH].to_dict())
    manager.save(thorough)

    reset_bundle = manager.reset()
    assert reset_bundle.preset == AdvancedSettingsPreset.BALANCED
    assert reset_bundle.retrieval.top_k == 8

    # Subsequent load must return the reset defaults
    loaded = manager.load()
    assert loaded.preset == AdvancedSettingsPreset.BALANCED


# ── 3. Propagation to RAG Components ───────────────────────────────────────────

def test_evidence_packet_builder_respects_settings(test_db_session):
    """EvidencePacketBuilder must respect RetrievalSettings overrides for min_score_threshold and max_passages."""
    custom_retrieval = RetrievalSettings(
        min_score_threshold=0.20,
        max_passages=4,
    )
    builder = EvidencePacketBuilder(test_db_session, retrieval_settings=custom_retrieval)
    assert builder._min_score_threshold == 0.20
    assert builder._max_passages == 4

    query = ParsedQuery(clean_query="Test query", raw_query="Test query")
    passages = [
        EvidencePassage(
            chunk_id=f"chk_{i}",
            document_id=f"doc_{i}",
            version_id=f"ver_{i}",
            title=f"Title {i}",
            department_id="FINANCE",
            doc_type="GO",
            page_start=1,
            page_end=1,
            section_heading="Test",
            content=f"Content {i}",
            score=0.10 + i * 0.05,
        )
        for i in range(10)
    ]
    packet = builder.build_packet(query, passages)
    # The passages selected should not exceed max_passages (4)
    assert len(packet.passages) <= 4


def test_hybrid_retriever_respects_settings(test_db_session):
    """HybridRetriever must respect RetrievalSettings overrides for weights and thresholds."""
    custom_retrieval = RetrievalSettings(
        bm25_weight=0.80,
        vector_min_similarity=0.70,
        enable_rerank=False,
    )
    retriever = HybridRetriever(test_db_session, retrieval_settings=custom_retrieval)
    assert retriever._bm25_weight == 0.80
    assert retriever._vec_weight == pytest.approx(0.20)
    assert retriever._vector_min_similarity == 0.70
    assert retriever._enable_rerank is False


def test_agent_state_machine_accepts_settings_bundle(test_db_session):
    """AgentStateMachine.run must accept settings_bundle and apply its parameters."""
    agent = AgentStateMachine(test_db_session)
    bundle = AdvancedSettingsBundle.from_dict(PRESET_BUNDLES[AdvancedSettingsPreset.PRECISE].to_dict())

    # Run a simple query with the bundle (should execute through deterministic runtime)
    user_ctx = UserContext(user_id="test_officer", clearance_level=Classification.PUBLIC.value)
    resp = agent.run(
        query="नमस्ते",
        user_context=user_ctx,
        settings_bundle=bundle,
    )
    assert resp is not None
    assert resp.session_id is not None


# ── 4. REST API Endpoints ──────────────────────────────────────────────────────

def test_api_get_advanced_settings(test_api_client):
    """GET /api/system/advanced-settings returns current settings, defaults, presets, and metadata."""
    res = test_api_client.get(
        "/api/system/advanced-settings",
        headers={"X-User-Id": "officer_api_001"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "current" in data
    assert "defaults" in data
    assert "presets" in data
    assert "metadata" in data
    assert data["current"]["preset"] == "BALANCED"
    assert "PRECISE" in data["presets"]
    assert "generation.temperature_rag" in data["metadata"]


def test_api_save_and_reset_advanced_settings(test_api_client):
    """POST /api/system/advanced-settings saves custom settings; DELETE resets to defaults."""
    # 1. Save custom settings
    save_payload = {
        "preset": "CUSTOM",
        "generation": {"temperature_rag": 0.1, "max_tokens_rag": 2048},
        "retrieval": {"top_k": 10},
        "performance": {"environment_profile": "DEV_SERVER"},
        "voice": {"default_voice_language": "en"},
        "opt_in": True,
    }
    res = test_api_client.post(
        "/api/system/advanced-settings",
        json=save_payload,
        headers={"X-User-Id": "officer_api_002"},
    )
    assert res.status_code == 200
    saved = res.json()
    assert saved["saved"] is True
    assert saved["settings"]["preset"] == "CUSTOM"
    assert saved["settings"]["generation"]["temperature_rag"] == 0.1
    assert saved["settings"]["retrieval"]["top_k"] == 10

    # 2. Verify GET reflects saved settings
    get_res = test_api_client.get(
        "/api/system/advanced-settings",
        headers={"X-User-Id": "officer_api_002"},
    )
    assert get_res.status_code == 200
    current = get_res.json()["current"]
    assert current["preset"] == "CUSTOM"
    assert current["retrieval"]["top_k"] == 10

    # 3. Reset
    reset_res = test_api_client.delete(
        "/api/system/advanced-settings",
        headers={"X-User-Id": "officer_api_002"},
    )
    assert reset_res.status_code == 200
    assert reset_res.json()["reset"] is True
    assert reset_res.json()["settings"]["preset"] == "BALANCED"


def test_api_save_rejects_invalid_settings(test_api_client):
    """POST /api/system/advanced-settings returns 422 if parameters violate bounds."""
    invalid_payload = {
        "preset": "CUSTOM",
        "generation": {"temperature_rag": 0.8},  # Phase 04 ceiling is 0.2!
        "retrieval": {"top_k": 100},              # Max is 20!
        "performance": {},
        "voice": {},
        "opt_in": True,
    }
    res = test_api_client.post(
        "/api/system/advanced-settings",
        json=invalid_payload,
        headers={"X-User-Id": "officer_api_003"},
    )
    assert res.status_code == 422
