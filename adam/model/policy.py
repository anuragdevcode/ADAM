"""Air-gapped data sovereignty and clearance policy enforcement for model runtimes.

Policy rules:
- Under RESTRICTED or CONFIDENTIAL classification clearance, all queries, evidence,
  and reasoning must remain strictly on-premise / within the air-gapped boundary.
- Cloud / third-party model runtimes (e.g. Google Gemini, external hosted APIs) are
  STRICTLY PROHIBITED for RESTRICTED or CONFIDENTIAL queries to prevent external data exfiltration.
- Only local on-device runtimes (Ollama or deterministic fallback) are permitted
  for classified government workflows.
"""

from typing import Optional, Tuple
from adam.vocabularies import Classification


class AirGappedSovereigntyViolationError(PermissionError):
    """Raised when a cloud model runtime is requested for RESTRICTED or CONFIDENTIAL queries."""
    pass


AIR_GAPPED_CLEARANCE_LEVELS = {
    Classification.RESTRICTED.value,
    Classification.CONFIDENTIAL.value,
}


def is_cloud_model(
    model_id: Optional[str] = None,
    backend: Optional[str] = None,
    serving_runtime: Optional[str] = None,
) -> bool:
    """Return True if the specified model, backend, or runtime connects to an external cloud provider."""
    if backend and backend.strip().lower() in ("gemini", "cloud", "openai", "anthropic", "hosted"):
        return True
    if serving_runtime and serving_runtime.strip().lower() in ("gemini", "cloud", "hosted"):
        return True
    if model_id:
        m_lower = model_id.strip().lower()
        if "gemini" in m_lower or "cloud" in m_lower:
            return True
    return False


def validate_air_gapped_model_policy(
    model_id: Optional[str],
    clearance_level: Optional[str],
    backend: Optional[str] = None,
    serving_runtime: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Validate that cloud models are never invoked for RESTRICTED or CONFIDENTIAL clearance.

    Returns:
        (allowed: bool, reason: Optional[str])
    """
    eff_clearance = clearance_level.strip().upper() if clearance_level else Classification.PUBLIC.value

    is_cloud = is_cloud_model(model_id=model_id, backend=backend, serving_runtime=serving_runtime)

    if is_cloud and eff_clearance in AIR_GAPPED_CLEARANCE_LEVELS:
        reason = (
            f"Air-Gapped Data Sovereignty Policy: Cloud model '{model_id or backend or 'gemini'}' is strictly "
            f"prohibited for {eff_clearance} clearance. Local on-premise execution (Ollama) or "
            "deterministic runtime is required to guarantee zero external data transmission."
        )
        return False, reason

    return True, None


def enforce_air_gapped_model_policy(
    model_id: Optional[str],
    clearance_level: Optional[str],
    backend: Optional[str] = None,
    serving_runtime: Optional[str] = None,
) -> None:
    """Raise AirGappedSovereigntyViolationError if a cloud model is used for RESTRICTED/CONFIDENTIAL clearance."""
    allowed, reason = validate_air_gapped_model_policy(
        model_id=model_id,
        clearance_level=clearance_level,
        backend=backend,
        serving_runtime=serving_runtime,
    )
    if not allowed:
        raise AirGappedSovereigntyViolationError(reason)
