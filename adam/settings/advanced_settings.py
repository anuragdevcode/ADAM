"""ADAM Advanced Settings — centralized, validated runtime configuration system.

Exposes every user-adjustable tunable discovered in the ADAM codebase as typed,
validated dataclasses with preset bundles (Precise / Balanced / Thorough / Custom).

Protected / internal values (SIGNING_SECRET, DATABASE_URL, session TTLs for
classified content, storage paths) are deliberately excluded from this module.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Preset names (governance-appropriate)
# ──────────────────────────────────────────────────────────────────────────────

class AdvancedSettingsPreset(str, Enum):
    """Named configuration presets balancing precision vs. thoroughness."""
    PRECISE = "PRECISE"       # Strictest grounding, fastest, shortest answers
    BALANCED = "BALANCED"     # Default ADAM behaviour — calibrated defaults
    THOROUGH = "THOROUGH"     # Broader search, longer answers, more evidence
    CUSTOM = "CUSTOM"         # User-controlled individual values


# ──────────────────────────────────────────────────────────────────────────────
# Settings dataclasses
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class GenerationSettings:
    """Inference / generation parameters propagated to harness profiles.

    Note on temperature_rag vs. temperature_conversational:
      Phase 04 mandates temperature ∈ [0.0, 0.2] for governed RAG. The state
      machine enforces this bound at runtime. Conversational temperature is
      passed directly to harness profile overrides and is NOT bounded by Phase 04.
    """
    # RAG / citation intent (Phase 04 bounded [0.0, 0.2])
    temperature_rag: float = 0.0          # default: 0.0 → harness resolves per family
    # Conversational / general intent (0.0–0.8 user-adjustable)
    temperature_conversational: float = 0.6
    # Maximum completion tokens
    max_tokens_rag: int = 1024
    max_tokens_conversational: int = 1536
    # Nucleus sampling
    top_p: float = 0.9
    # Top-k sampling
    top_k_sampling: int = 40
    # min-p (Qwen family)
    min_p: float = 0.05
    # Context window passed to Ollama num_ctx
    context_size: int = 8192
    # Max passages injected into RAG prompt
    max_rag_prompt_passages: int = 4
    # Qwen3 thinking mode
    thinking_enabled: bool = False
    thinking_budget: int = 1024

    def validate(self) -> List[str]:
        """Return list of validation errors (empty = valid)."""
        errors: List[str] = []
        if not 0.0 <= self.temperature_rag <= 0.2:
            errors.append(f"temperature_rag {self.temperature_rag} must be in [0.0, 0.2] (Phase 04)")
        if not 0.0 <= self.temperature_conversational <= 1.0:
            errors.append(f"temperature_conversational {self.temperature_conversational} must be in [0.0, 1.0]")
        if not 256 <= self.max_tokens_rag <= 4096:
            errors.append(f"max_tokens_rag {self.max_tokens_rag} must be in [256, 4096]")
        if not 256 <= self.max_tokens_conversational <= 4096:
            errors.append(f"max_tokens_conversational {self.max_tokens_conversational} must be in [256, 4096]")
        if not 0.1 <= self.top_p <= 1.0:
            errors.append(f"top_p {self.top_p} must be in [0.1, 1.0]")
        if not 10 <= self.top_k_sampling <= 100:
            errors.append(f"top_k_sampling {self.top_k_sampling} must be in [10, 100]")
        if not 0.0 <= self.min_p <= 0.2:
            errors.append(f"min_p {self.min_p} must be in [0.0, 0.2]")
        if not 2048 <= self.context_size <= 32768:
            errors.append(f"context_size {self.context_size} must be in [2048, 32768]")
        if not 2 <= self.max_rag_prompt_passages <= 8:
            errors.append(f"max_rag_prompt_passages {self.max_rag_prompt_passages} must be in [2, 8]")
        if not 256 <= self.thinking_budget <= 4096:
            errors.append(f"thinking_budget {self.thinking_budget} must be in [256, 4096]")
        return errors


@dataclass
class RetrievalSettings:
    """Hybrid retrieval pipeline parameters."""
    # Number of candidate passages passed from search to evidence builder
    top_k: int = 8
    # Whether the cross-encoder reranker runs after BM25+vector scoring
    enable_rerank: bool = True
    # Weighted combination: BM25 weight (vector = 1 - bm25_weight)
    bm25_weight: float = 0.65
    # Minimum cosine similarity for a vector candidate to survive
    vector_min_similarity: float = 0.55
    # Evidence packet minimum relevance score
    min_score_threshold: float = 0.05
    # Evidence packet passage count bounds
    min_passages: int = 3
    max_passages: int = 8

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not 3 <= self.top_k <= 20:
            errors.append(f"top_k {self.top_k} must be in [3, 20]")
        if not 0.1 <= self.bm25_weight <= 0.9:
            errors.append(f"bm25_weight {self.bm25_weight} must be in [0.1, 0.9]")
        if not 0.3 <= self.vector_min_similarity <= 0.95:
            errors.append(f"vector_min_similarity {self.vector_min_similarity} must be in [0.3, 0.95]")
        if not 0.01 <= self.min_score_threshold <= 0.3:
            errors.append(f"min_score_threshold {self.min_score_threshold} must be in [0.01, 0.3]")
        if not 1 <= self.min_passages <= 6:
            errors.append(f"min_passages {self.min_passages} must be in [1, 6]")
        if not 3 <= self.max_passages <= 12:
            errors.append(f"max_passages {self.max_passages} must be in [3, 12]")
        if self.min_passages > self.max_passages:
            errors.append("min_passages cannot exceed max_passages")
        return errors


@dataclass
class PerformanceSettings:
    """Hardware environment profile and concurrency settings."""
    # Logical environment: drives max_active_requests and mutual exclusion
    environment_profile: str = "MACBOOK_AIR_8GB"  # MACBOOK_AIR_8GB | DEV_SERVER | GOV_PRODUCTION
    # Response cache TTL in seconds (informational — cached responses reuse this)
    cache_ttl_seconds: int = 3600
    # Max in-memory LRU cache entries
    cache_max_entries: int = 500

    def validate(self) -> List[str]:
        errors: List[str] = []
        valid_profiles = {"MACBOOK_AIR_8GB", "DEV_SERVER", "GOV_PRODUCTION"}
        if self.environment_profile not in valid_profiles:
            errors.append(f"environment_profile must be one of {valid_profiles}")
        if not 60 <= self.cache_ttl_seconds <= 86400:
            errors.append(f"cache_ttl_seconds {self.cache_ttl_seconds} must be in [60, 86400]")
        if not 50 <= self.cache_max_entries <= 2000:
            errors.append(f"cache_max_entries {self.cache_max_entries} must be in [50, 2000]")
        return errors


@dataclass
class VoiceSettings:
    """Voice interface defaults."""
    # Default spoken language for STT and TTS
    default_voice_language: str = "hi"  # hi | en | hi-en
    # Whether TTS read-aloud is on by default
    tts_enabled_default: bool = False

    def validate(self) -> List[str]:
        errors: List[str] = []
        valid_langs = {"hi", "en", "hi-en"}
        if self.default_voice_language not in valid_langs:
            errors.append(f"default_voice_language must be one of {valid_langs}")
        return errors


@dataclass
class AdvancedSettingsBundle:
    """Top-level container for all advanced settings categories."""
    preset: AdvancedSettingsPreset = AdvancedSettingsPreset.BALANCED
    generation: GenerationSettings = field(default_factory=GenerationSettings)
    retrieval: RetrievalSettings = field(default_factory=RetrievalSettings)
    performance: PerformanceSettings = field(default_factory=PerformanceSettings)
    voice: VoiceSettings = field(default_factory=VoiceSettings)

    def validate(self) -> List[str]:
        """Validate all sub-settings and return combined error list."""
        errors: List[str] = []
        errors.extend(self.generation.validate())
        errors.extend(self.retrieval.validate())
        errors.extend(self.performance.validate())
        errors.extend(self.voice.validate())
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "preset": self.preset.value,
            "generation": asdict(self.generation),
            "retrieval": asdict(self.retrieval),
            "performance": asdict(self.performance),
            "voice": asdict(self.voice),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AdvancedSettingsBundle":
        preset_str = data.get("preset", "BALANCED")
        try:
            preset = AdvancedSettingsPreset(preset_str)
        except ValueError:
            preset = AdvancedSettingsPreset.BALANCED

        gen_data = data.get("generation", {})
        ret_data = data.get("retrieval", {})
        perf_data = data.get("performance", {})
        voice_data = data.get("voice", {})

        def _merge(defaults_obj, overrides: dict):
            """Merge overrides into a defaults dataclass, ignoring unknown keys."""
            d = asdict(defaults_obj)
            for k, v in overrides.items():
                if k in d:
                    d[k] = v
            return d

        gen_merged = _merge(GenerationSettings(), gen_data)
        ret_merged = _merge(RetrievalSettings(), ret_data)
        perf_merged = _merge(PerformanceSettings(), perf_data)
        voice_merged = _merge(VoiceSettings(), voice_data)

        return cls(
            preset=preset,
            generation=GenerationSettings(**gen_merged),
            retrieval=RetrievalSettings(**ret_merged),
            performance=PerformanceSettings(**perf_merged),
            voice=VoiceSettings(**voice_merged),
        )


# ──────────────────────────────────────────────────────────────────────────────
# Built-in preset bundles
# ──────────────────────────────────────────────────────────────────────────────

PRESET_BUNDLES: Dict[AdvancedSettingsPreset, AdvancedSettingsBundle] = {
    AdvancedSettingsPreset.PRECISE: AdvancedSettingsBundle(
        preset=AdvancedSettingsPreset.PRECISE,
        generation=GenerationSettings(
            temperature_rag=0.0,
            temperature_conversational=0.3,
            max_tokens_rag=512,
            max_tokens_conversational=768,
            top_p=0.85,
            top_k_sampling=20,
            min_p=0.05,
            context_size=4096,
            max_rag_prompt_passages=3,
            thinking_enabled=False,
            thinking_budget=512,
        ),
        retrieval=RetrievalSettings(
            top_k=3,
            enable_rerank=True,
            bm25_weight=0.75,
            vector_min_similarity=0.65,
            min_score_threshold=0.10,
            min_passages=2,
            max_passages=5,
        ),
        performance=PerformanceSettings(
            environment_profile="MACBOOK_AIR_8GB",
            cache_ttl_seconds=3600,
            cache_max_entries=500,
        ),
        voice=VoiceSettings(default_voice_language="hi", tts_enabled_default=False),
    ),
    AdvancedSettingsPreset.BALANCED: AdvancedSettingsBundle(
        preset=AdvancedSettingsPreset.BALANCED,
        generation=GenerationSettings(
            temperature_rag=0.0,
            temperature_conversational=0.6,
            max_tokens_rag=1024,
            max_tokens_conversational=1536,
            top_p=0.9,
            top_k_sampling=40,
            min_p=0.05,
            context_size=8192,
            max_rag_prompt_passages=4,
            thinking_enabled=False,
            thinking_budget=1024,
        ),
        retrieval=RetrievalSettings(
            top_k=8,
            enable_rerank=True,
            bm25_weight=0.65,
            vector_min_similarity=0.55,
            min_score_threshold=0.05,
            min_passages=3,
            max_passages=8,
        ),
        performance=PerformanceSettings(
            environment_profile="MACBOOK_AIR_8GB",
            cache_ttl_seconds=3600,
            cache_max_entries=500,
        ),
        voice=VoiceSettings(default_voice_language="hi", tts_enabled_default=False),
    ),
    AdvancedSettingsPreset.THOROUGH: AdvancedSettingsBundle(
        preset=AdvancedSettingsPreset.THOROUGH,
        generation=GenerationSettings(
            temperature_rag=0.15,
            temperature_conversational=0.7,
            max_tokens_rag=1536,
            max_tokens_conversational=2048,
            top_p=0.92,
            top_k_sampling=60,
            min_p=0.03,
            context_size=16384,
            max_rag_prompt_passages=6,
            thinking_enabled=False,
            thinking_budget=1024,
        ),
        retrieval=RetrievalSettings(
            top_k=15,
            enable_rerank=True,
            bm25_weight=0.55,
            vector_min_similarity=0.45,
            min_score_threshold=0.03,
            min_passages=4,
            max_passages=10,
        ),
        performance=PerformanceSettings(
            environment_profile="DEV_SERVER",
            cache_ttl_seconds=7200,
            cache_max_entries=1000,
        ),
        voice=VoiceSettings(default_voice_language="hi", tts_enabled_default=False),
    ),
    AdvancedSettingsPreset.CUSTOM: AdvancedSettingsBundle(
        preset=AdvancedSettingsPreset.CUSTOM,
    ),
}

DEFAULT_BUNDLE = PRESET_BUNDLES[AdvancedSettingsPreset.BALANCED]

# ──────────────────────────────────────────────────────────────────────────────
# Settings metadata — describes each field for the UI
# ──────────────────────────────────────────────────────────────────────────────

SETTINGS_METADATA: Dict[str, Dict[str, Any]] = {
    # Generation
    "generation.temperature_rag": {
        "label": "RAG Temperature",
        "description": "Sampling temperature for governed document Q&A (Phase 04 bounded to 0.0–0.2).",
        "type": "float", "min": 0.0, "max": 0.2, "step": 0.01,
        "impact": "accuracy", "default": 0.0,
    },
    "generation.temperature_conversational": {
        "label": "Conversational Creativity",
        "description": "Temperature for casual/general turns. Does not affect governed RAG citations.",
        "type": "float", "min": 0.0, "max": 0.8, "step": 0.05,
        "impact": "accuracy", "default": 0.6,
    },
    "generation.max_tokens_rag": {
        "label": "Max Answer Length (RAG)",
        "description": "Maximum completion tokens for citation-grounded answers.",
        "type": "int", "min": 256, "max": 4096, "step": 128,
        "impact": "speed", "default": 1024,
    },
    "generation.max_tokens_conversational": {
        "label": "Max Answer Length (Conversational)",
        "description": "Maximum completion tokens for conversational/greeting responses.",
        "type": "int", "min": 256, "max": 4096, "step": 128,
        "impact": "speed", "default": 1536,
    },
    "generation.top_p": {
        "label": "Nucleus Sampling (Top-P)",
        "description": "Probability mass threshold for nucleus sampling. Lower = more focused.",
        "type": "float", "min": 0.1, "max": 1.0, "step": 0.05,
        "impact": "accuracy", "default": 0.9,
    },
    "generation.top_k_sampling": {
        "label": "Top-K Sampling",
        "description": "Max token candidates per step. Lower = more deterministic outputs.",
        "type": "int", "min": 10, "max": 100, "step": 5,
        "impact": "accuracy", "default": 40,
    },
    "generation.min_p": {
        "label": "Min-P Threshold (Qwen)",
        "description": "Minimum probability relative to the top token. Filters low-quality candidates (Qwen family only).",
        "type": "float", "min": 0.0, "max": 0.2, "step": 0.01,
        "impact": "accuracy", "default": 0.05,
    },
    "generation.context_size": {
        "label": "Context Window (tokens)",
        "description": "Maximum context fed to the model. Larger = better multi-document reasoning but more RAM.",
        "type": "int", "min": 2048, "max": 32768, "step": 1024,
        "impact": "memory", "default": 8192,
    },
    "generation.max_rag_prompt_passages": {
        "label": "Passages in Prompt",
        "description": "How many evidence passages are injected into the model prompt. More = better coverage, longer prompt.",
        "type": "int", "min": 2, "max": 8, "step": 1,
        "impact": "memory", "default": 4,
    },
    "generation.thinking_enabled": {
        "label": "Extended Thinking (Qwen3)",
        "description": "Enable internal chain-of-thought scratchpad. Qwen3 reasoning variants only.",
        "type": "bool", "impact": "speed", "default": False,
    },
    "generation.thinking_budget": {
        "label": "Thinking Budget (tokens)",
        "description": "Token headroom reserved for internal reasoning when thinking is enabled.",
        "type": "int", "min": 256, "max": 4096, "step": 256,
        "impact": "speed", "default": 1024,
    },
    # Retrieval
    "retrieval.top_k": {
        "label": "Retrieval Candidates (Top-K)",
        "description": "Number of candidate passages fetched from the repository before reranking.",
        "type": "int", "min": 3, "max": 20, "step": 1,
        "impact": "speed", "default": 8,
    },
    "retrieval.enable_rerank": {
        "label": "Cross-Encoder Reranker",
        "description": "Apply a local cross-encoder to rerank retrieved passages by query alignment.",
        "type": "bool", "impact": "accuracy", "default": True,
    },
    "retrieval.bm25_weight": {
        "label": "BM25 / Keyword Weight",
        "description": "Proportion of the hybrid score from BM25 keyword matching (vector = 1 − BM25).",
        "type": "float", "min": 0.1, "max": 0.9, "step": 0.05,
        "impact": "accuracy", "default": 0.65,
    },
    "retrieval.vector_min_similarity": {
        "label": "Min Vector Similarity",
        "description": "Cosine similarity floor below which vector candidates are dropped.",
        "type": "float", "min": 0.3, "max": 0.95, "step": 0.05,
        "impact": "accuracy", "default": 0.55,
    },
    "retrieval.min_score_threshold": {
        "label": "Min Relevance Score",
        "description": "Minimum hybrid score for a passage to enter the evidence packet.",
        "type": "float", "min": 0.01, "max": 0.3, "step": 0.01,
        "impact": "accuracy", "default": 0.05,
    },
    "retrieval.min_passages": {
        "label": "Min Evidence Passages",
        "description": "Minimum passages required to proceed with a cited answer.",
        "type": "int", "min": 1, "max": 6, "step": 1,
        "impact": "accuracy", "default": 3,
    },
    "retrieval.max_passages": {
        "label": "Max Evidence Passages",
        "description": "Maximum passages included in the evidence packet sent to the model.",
        "type": "int", "min": 3, "max": 12, "step": 1,
        "impact": "memory", "default": 8,
    },
    # Performance
    "performance.environment_profile": {
        "label": "Hardware Environment",
        "description": "Controls concurrency limits and mutual exclusion policy. Match to your hardware.",
        "type": "enum",
        "options": [
            {"value": "MACBOOK_AIR_8GB", "label": "MacBook Air 8GB — single request, strict mutual exclusion"},
            {"value": "DEV_SERVER", "label": "Dev Server 8–16GB — 4 concurrent, relaxed mutual exclusion"},
            {"value": "GOV_PRODUCTION", "label": "Gov Production GPU — 16 concurrent"},
        ],
        "impact": "speed", "default": "MACBOOK_AIR_8GB",
    },
    "performance.cache_ttl_seconds": {
        "label": "Response Cache TTL",
        "description": "How long identical query responses stay cached (seconds).",
        "type": "int", "min": 60, "max": 86400, "step": 60,
        "impact": "speed", "default": 3600,
    },
    "performance.cache_max_entries": {
        "label": "Cache Max Entries",
        "description": "Maximum LRU cache entries before oldest responses are evicted.",
        "type": "int", "min": 50, "max": 2000, "step": 50,
        "impact": "memory", "default": 500,
    },
    # Voice
    "voice.default_voice_language": {
        "label": "Default Voice Language",
        "description": "Default language for speech-to-text and text-to-speech.",
        "type": "enum",
        "options": [
            {"value": "hi", "label": "Hindi (हिन्दी)"},
            {"value": "en", "label": "English"},
            {"value": "hi-en", "label": "Bilingual Hindi + English"},
        ],
        "impact": "accuracy", "default": "hi",
    },
    "voice.tts_enabled_default": {
        "label": "Auto-Read Answers Aloud",
        "description": "When enabled, ADAM automatically reads answers using text-to-speech.",
        "type": "bool", "impact": "accuracy", "default": False,
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Manager
# ──────────────────────────────────────────────────────────────────────────────

_SETTINGS_PURPOSE = "ADAM Advanced Settings — inference, retrieval, performance, and voice configuration"
_SETTINGS_PREF_KEY = "__adam_advanced_settings__"


class AdvancedSettingsManager:
    """Loads, validates, and persists the AdvancedSettingsBundle for a user.

    Uses the existing UserPreferenceManager for encrypted, opt-in storage.
    Falls back to the BALANCED preset defaults if no saved settings exist.
    """

    def __init__(self, db_session, user_id: str):
        from adam.memory.preferences import UserPreferenceManager
        self._pref_manager = UserPreferenceManager(db_session)
        self._user_id = user_id

    def load(self) -> AdvancedSettingsBundle:
        """Load saved settings or return BALANCED defaults."""
        try:
            raw = self._pref_manager.get_preference(self._user_id)
            if raw and _SETTINGS_PREF_KEY in raw:
                bundle = AdvancedSettingsBundle.from_dict(raw[_SETTINGS_PREF_KEY])
                errors = bundle.validate()
                if errors:
                    logger.warning("Loaded advanced settings have validation errors: %s — falling back to defaults", errors)
                    return AdvancedSettingsBundle.from_dict(DEFAULT_BUNDLE.to_dict())
                return bundle
        except Exception as exc:
            logger.warning("Could not load advanced settings: %s — using defaults", exc)
        return AdvancedSettingsBundle.from_dict(DEFAULT_BUNDLE.to_dict())

    def save(self, bundle: AdvancedSettingsBundle, opt_in: bool = True) -> None:
        """Validate and persist settings via UserPreferenceManager."""
        errors = bundle.validate()
        if errors:
            raise ValueError(f"Invalid advanced settings: {errors}")

        # Merge into any existing preferences (e.g. language pref from SettingsModal)
        try:
            existing = self._pref_manager.get_preference(self._user_id) or {}
        except Exception:
            existing = {}

        existing[_SETTINGS_PREF_KEY] = bundle.to_dict()

        self._pref_manager.set_preference(
            user_id=self._user_id,
            purpose=_SETTINGS_PURPOSE,
            preferences=existing,
            opt_in=opt_in,
        )

    def reset(self) -> AdvancedSettingsBundle:
        """Reset to BALANCED defaults and persist."""
        default = AdvancedSettingsBundle.from_dict(DEFAULT_BUNDLE.to_dict())
        self.save(default)
        return default

    @staticmethod
    def apply_preset(preset: AdvancedSettingsPreset) -> AdvancedSettingsBundle:
        """Return a fresh copy of the named preset bundle."""
        base = PRESET_BUNDLES.get(preset, DEFAULT_BUNDLE)
        return AdvancedSettingsBundle.from_dict(base.to_dict())
