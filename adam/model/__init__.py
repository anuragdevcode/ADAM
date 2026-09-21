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
# Dynamic discovery / validation / attestation — lazy-imported to keep startup fast.
# Consumers should import directly from the submodule if needed at module level.
from adam.model.discovery import DiscoveredModel, run_local_discovery
from adam.model.providers import (
    SSRFGuard,
    UnsafeEndpointError,
    ProtocolDetector,
    RemoteProviderConfig,
    RemoteProviderRegistry,
    REMOTE_PROVIDER_REGISTRY,
)
from adam.model.validation import TechnicalValidationResult, OllamaValidator, RemoteApiValidator
from adam.model.attestation import (
    AttestationResult,
    AttestationCheck,
    ModelAttestor,
    ATTESTATION_SUITE_VERSION,
    get_cached_attestation,
    invalidate_attestation,
)

__all__ = [
    # Core registry & artifacts
    "ModelArtifact",
    "ModelRegistry",
    "QWEN3_4B_INSTRUCT",
    "QWEN3_1_7B_INSTRUCT",
    "QWEN2_5_3B_INSTRUCT",
    "GEMMA_3_4B_IT",
    "LLAMA_3_2_3B_INSTRUCT",
    # Runtime & concurrency
    "BaseModelRuntime",
    "DeterministicModelRuntime",
    "OllamaModelRuntime",
    "SingleModelLifecycleManager",
    "ModelGenerationResult",
    "ConcurrentModelLoadError",
    # Governance
    "ModelGovernance",
    "ModelPromotionEvaluation",
    # Acceptance test suite
    "UNANSWERABLE_TEST_CASES",
    "HIGH_RISK_TEST_CASES",
    "HINDI_LINGUISTIC_TEST_CASES",
    "UnanswerableTestCase",
    "HighRiskTestCase",
    "HindiLinguisticTestCase",
    # Air-gapped policy
    "AirGappedSovereigntyViolationError",
    "AIR_GAPPED_CLEARANCE_LEVELS",
    "is_cloud_model",
    "validate_air_gapped_model_policy",
    "enforce_air_gapped_model_policy",
    # Dynamic discovery
    "DiscoveredModel",
    "run_local_discovery",
    # SSRF & provider management
    "SSRFGuard",
    "UnsafeEndpointError",
    "ProtocolDetector",
    "RemoteProviderConfig",
    "RemoteProviderRegistry",
    "REMOTE_PROVIDER_REGISTRY",
    # Validation
    "TechnicalValidationResult",
    "OllamaValidator",
    "RemoteApiValidator",
    # Attestation
    "AttestationResult",
    "AttestationCheck",
    "ModelAttestor",
    "ATTESTATION_SUITE_VERSION",
    "get_cached_attestation",
    "invalidate_attestation",
]
