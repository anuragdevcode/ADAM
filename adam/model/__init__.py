"""Model architecture, registry, runtime serving, and governance promotion module."""

from adam.model.registry import (
    ModelArtifact,
    ModelRegistry,
    QWEN3_4B_INSTRUCT,
    QWEN3_1_7B_INSTRUCT,
    QWEN2_5_3B_INSTRUCT,
    GEMMA_3_4B_IT,
    LLAMA_3_2_3B_INSTRUCT,
)
from adam.model.runtime import (
    BaseModelRuntime,
    DeterministicModelRuntime,
    OllamaModelRuntime,
    SingleModelLifecycleManager,
    ModelGenerationResult,
    ConcurrentModelLoadError,
)
from adam.model.governance import (
    ModelGovernance,
    ModelPromotionEvaluation,
)
from adam.model.unanswerable_suite import (
    UNANSWERABLE_TEST_CASES,
    HIGH_RISK_TEST_CASES,
    HINDI_LINGUISTIC_TEST_CASES,
    UnanswerableTestCase,
    HighRiskTestCase,
    HindiLinguisticTestCase,
)
from adam.model.policy import (
    AirGappedSovereigntyViolationError,
    AIR_GAPPED_CLEARANCE_LEVELS,
    is_cloud_model,
    validate_air_gapped_model_policy,
    enforce_air_gapped_model_policy,
)

__all__ = [
    "ModelArtifact",
    "ModelRegistry",
    "QWEN3_4B_INSTRUCT",
    "QWEN3_1_7B_INSTRUCT",
    "QWEN2_5_3B_INSTRUCT",
    "GEMMA_3_4B_IT",
    "LLAMA_3_2_3B_INSTRUCT",
    "BaseModelRuntime",
    "DeterministicModelRuntime",
    "OllamaModelRuntime",
    "SingleModelLifecycleManager",
    "ModelGenerationResult",
    "ConcurrentModelLoadError",
    "ModelGovernance",
    "ModelPromotionEvaluation",
    "UNANSWERABLE_TEST_CASES",
    "HIGH_RISK_TEST_CASES",
    "HINDI_LINGUISTIC_TEST_CASES",
    "UnanswerableTestCase",
    "HighRiskTestCase",
    "HindiLinguisticTestCase",
    "AirGappedSovereigntyViolationError",
    "AIR_GAPPED_CLEARANCE_LEVELS",
    "is_cloud_model",
    "validate_air_gapped_model_policy",
    "enforce_air_gapped_model_policy",
]

