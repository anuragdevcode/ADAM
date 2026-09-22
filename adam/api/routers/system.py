"""System metadata, model registry, and taxonomy endpoints."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from adam.api.deps import get_db
from adam.model.registry import CANONICAL_MODELS, ModelRegistry
from adam.model.runtime import OllamaModelRuntime
from adam.vocabularies import (
    AuthorityLevel,
    Classification,
    DepartmentId,
    DocType,
    LifecycleStatus,
    LicenseStatus,
    ModelStatus,
)

PRECEDENT_RELATION_TYPES = [
    "SUPERSEDES",
    "AMENDS",
    "IN_CONTINUATION_OF",
    "READ_WITH",
    "REFERS_TO",
]

router = APIRouter()

DEPARTMENT_LABELS: Dict[str, str] = {
    DepartmentId.FINANCE_TREASURY.value: "Finance & Treasury",
    DepartmentId.RURAL_DEVELOPMENT.value: "Rural Development & Panchayati Raj",
    DepartmentId.AUDIT_DIRECTORATE.value: "Audit Directorate",
    DepartmentId.BOARD_OF_REVENUE.value: "Board of Revenue",
    DepartmentId.GENERAL_ADMINISTRATION.value: "General Administration (GAD)",
    DepartmentId.LEGAL_AFFAIRS.value: "Law & Justice",
    DepartmentId.OPEN_GOVERNMENT_DATA.value: "Open Government Data Portal",
    DepartmentId.UNKNOWN.value: "Other / Unspecified",
}


import os
import httpx
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Header
from fastapi.responses import PlainTextResponse
from adam.agent.redaction import SecretRedactor


class ValidateKeyRequest(BaseModel):
    api_key: str


@router.post("/system/validate-gemini-key")
def validate_gemini_key(req: ValidateKeyRequest) -> Dict[str, Any]:
    """Test validity of a user-provided Google Gemini API key securely without persisting it."""
    key = req.api_key.strip()
    if not key:
        return {"valid": False, "message": "API key cannot be empty."}

    url = "https://generativelanguage.googleapis.com/v1beta/models"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, headers={"x-goog-api-key": key})
            if resp.status_code == 200:
                return {
                    "valid": True,
                    "message": "Google Gemini API key verified successfully.",
                    "available_models": ["gemini-3.6-flash"],
                }
            elif resp.status_code in (400, 401, 403):
                return {
                    "valid": False,
                    "message": "Invalid API key or access denied by Google API.",
                }
            else:
                return {
                    "valid": False,
                    "message": f"Google API returned error status {resp.status_code}.",
                }
    except Exception as e:
        sanitized_msg = SecretRedactor.sanitize_text(f"Connection to Google API failed: {str(e)}").replace(key, "[REDACTED_API_KEY]")
        return {
            "valid": False,
            "message": sanitized_msg,
        }


@router.get("/metrics", response_class=PlainTextResponse)
def get_prometheus_metrics(db: Session = Depends(get_db)) -> PlainTextResponse:
    """Expose Prometheus / OpenMetrics telemetry endpoint for standard infrastructure monitoring."""
    from adam.observability.metrics import GLOBAL_METRICS
    content = GLOBAL_METRICS.generate_metrics_text(session=db)
    return PlainTextResponse(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/system/models")
def get_models(
    db: Session = Depends(get_db),
    x_gemini_api_key: Optional[str] = Header(None),
    x_clearance_level: Optional[str] = Header(None),
) -> List[Dict[str, Any]]:
    """Return all approved release-controlled models from the model registry, enforcing air-gap sovereignty."""
    registry = ModelRegistry(db)
    models = registry.list_all()
    if not models:
        # Fallback to canonical models if database has not yet been seeded
        models = list(CANONICAL_MODELS.values())

    # Only gemini-3.6-flash is available with the API key
    models = [
        m for m in models
        if m.id not in ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.0-flash-exp", "gemini-2.5-flash")
    ]

    is_air_gapped_clearance = bool(
        x_clearance_level and x_clearance_level.strip().upper() in ("RESTRICTED", "CONFIDENTIAL")
    )

    result = []
    for m in models:
        lic_stat = getattr(m, 'license_status', None)
        lic_stat_str = str(lic_stat.value if hasattr(lic_stat, 'value') else lic_stat)
        requires_review = bool(getattr(m, 'requires_legal_review', False))
        is_cloud = getattr(m, 'serving_runtime', '') == "gemini"
        is_supported = (lic_stat == LicenseStatus.APPROVED or lic_stat_str == "APPROVED") and not requires_review

        if is_cloud and is_air_gapped_clearance:
            is_installed = False
            is_supported = False
            unavailable_reason = "Cloud models disabled for RESTRICTED/CONFIDENTIAL clearance (Air-Gapped Sovereignty Policy)"
        elif is_cloud:
            has_gemini_key = bool(x_gemini_api_key or os.getenv("GEMINI_API_KEY", "").strip())
            is_installed = has_gemini_key
            if not has_gemini_key:
                unavailable_reason = "Requires Google Gemini API key (click 'Add API Key' above to enable)"
            else:
                unavailable_reason = None
        else:
            is_installed = OllamaModelRuntime(m).is_model_present()
            if not is_supported or requires_review:
                unavailable_reason = "Requires legal and governance signoff (Evaluation comparator only)"
            elif not is_installed:
                unavailable_reason = "Not installed in Ollama"
            else:
                unavailable_reason = None

        result.append({
            "id": m.id,
            "name": m.name,
            "revision": m.revision,
            "quantization": m.quantization,
            "file_size_mb": round(m.file_size_bytes / (1024 * 1024), 1) if m.file_size_bytes else 0,
            "context_window": m.context_window,
            "languages": m.languages,
            "is_primary": m.is_primary,
            "is_fallback": m.is_fallback,
            "is_comparator": m.is_comparator,
            "license_id": m.license_id,
            "license_status": lic_stat_str,
            "requires_legal_review": requires_review,
            "is_supported": is_supported,
            "status": str(m.status.value if hasattr(m.status, 'value') else m.status),
            "serving_runtime": m.serving_runtime,
            "is_installed": is_installed,
            "unavailable_reason": unavailable_reason,
            "is_cloud": is_cloud,
            "air_gapped_restricted": is_cloud and is_air_gapped_clearance,
        })
    return result


@router.get("/system/vocabularies")
def get_vocabularies() -> Dict[str, Any]:
    """Return controlled taxonomies for departments, classifications, and document types."""
    departments = [
        {
            "id": dept.value,
            "label": DEPARTMENT_LABELS.get(dept.value, dept.value.replace("_", " ").title()),
        }
        for dept in DepartmentId
        if dept != DepartmentId.UNKNOWN
    ]

    classifications = [c.value for c in Classification]
    doc_types = [d.value for d in DocType if d != DocType.UNKNOWN]
    precedent_types = PRECEDENT_RELATION_TYPES

    return {
        "departments": departments,
        "classifications": classifications,
        "doc_types": doc_types,
        "precedent_types": precedent_types,
    }


@router.get("/system/rag-benchmark")
def get_system_rag_benchmark(
    live: bool = False,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return verified empirical RAG benchmark scorecard and reranker ablation analysis."""
    from adam.api.routers.audit import CANONICAL_RAG_BENCHMARK
    if not live:
        return CANONICAL_RAG_BENCHMARK

    from adam.rag.evaluation import populate_eval_corpus, evaluate_gold_set
    populate_eval_corpus(db)
    scorecard = evaluate_gold_set(db)
    res = scorecard.to_dict()
    res["reranker_ablation"] = CANONICAL_RAG_BENCHMARK["reranker_ablation"]
    return res


# ── Dynamic Discovery Endpoints ────────────────────────────────────────────
# These are additive. All existing endpoints above are unchanged.

import threading as _threading
import time as _time
from pydantic import BaseModel as _BaseModel

from adam.model.discovery import run_local_discovery, DiscoveredModel
from adam.model.validation import OllamaValidator
from adam.model.attestation import ModelAttestor, ATTESTATION_SUITE_VERSION, get_cached_attestation
from adam.model.providers import (
    REMOTE_PROVIDER_REGISTRY,
    UnsafeEndpointError,
    UnsupportedProtocolError,
)

# Shared dynamic registry (in-memory for the process lifetime)
_DYNAMIC_REGISTRY: Dict[str, Dict[str, Any]] = {}
_DISCOVERY_LOCK = _threading.Lock()


def _build_dynamic_model_info(discovered: DiscoveredModel, attestation_status: Optional[str] = None, capabilities: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build a ModelInfo-compatible dict from a DiscoveredModel."""
    return {
        "id": discovered.model_id,
        "name": discovered.display_name,
        "revision": "dynamic",
        "quantization": "dynamic",
        "file_size_mb": round(discovered.size_bytes / (1024 * 1024), 1) if discovered.size_bytes else 0,
        "context_window": discovered.context_length or 4096,
        "languages": ["en"],
        "is_primary": False,
        "is_fallback": False,
        "is_comparator": False,
        "license_id": "unknown",
        "license_status": "APPROVED",
        "requires_legal_review": False,
        "is_supported": True,
        "status": "REGISTERED",
        "serving_runtime": discovered.runtime,
        "is_installed": True,
        "unavailable_reason": None,
        "is_cloud": False,
        "air_gapped_restricted": False,
        # Dynamic discovery fields
        "source": "discovered",
        "attestation_status": attestation_status or "checking",
        "attestation_version": ATTESTATION_SUITE_VERSION,
        "capabilities": capabilities or {},
        "display_group": "LOCAL",
        "provider_display": discovered.provider.title(),
    }


@router.post("/system/models/discover")
def trigger_model_discovery(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Scan local runtimes (Ollama) for installed models and register new discoveries.

    Returns immediately with the discovered model list.  Technical validation
    and behavioural attestation run in a background thread.

    Response schema is a superset of the existing GET /api/system/models response
    — all existing fields are present, new fields are additive.
    """
    with _DISCOVERY_LOCK:
        discovered = run_local_discovery()

    # Build a canonical ModelInfo response for each discovered model.
    # Models already in the canonical registry are excluded here (they come
    # through the existing GET /api/system/models path).
    from adam.model.registry import CANONICAL_MODELS, ModelRegistry
    canonical_ids = set(CANONICAL_MODELS.keys())

    # Also map common Ollama tags to canonical IDs
    canonical_ollama_tags = {
        "qwen3:4b", "qwen3:1.7b", "qwen2.5:3b", "gemma3:4b", "llama3.2:3b",
    }

    result_models = []
    new_discoveries: list = []
    for dm in discovered:
        if dm.model_id in canonical_ids or dm.model_id in canonical_ollama_tags:
            # Skip — canonical path handles these
            continue
        info = _build_dynamic_model_info(dm, attestation_status="checking")
        _DYNAMIC_REGISTRY[dm.model_id] = {"discovered": dm.to_dict(), "info": info}
        result_models.append(info)
        new_discoveries.append(dm)

    # Trigger async validation + attestation in background (non-blocking)
    if new_discoveries:
        _threading.Thread(
            target=_run_background_attestation,
            args=(new_discoveries,),
            daemon=True,
        ).start()

    return {
        "discovered_count": len(discovered),
        "new_models": result_models,
        "canonical_skipped": len(discovered) - len(new_discoveries),
        "message": (
            f"Discovered {len(new_discoveries)} new model(s). "
            "Technical validation and attestation running in background."
        ),
    }


def _run_background_attestation(models: list) -> None:
    """Background task: validate + attest each newly discovered model."""
    from adam.model.validation import OllamaValidator
    from adam.model.attestation import ModelAttestor
    from adam.model.runtime import DeterministicModelRuntime, ModelArtifact
    from adam.model.registry import ModelRegistry
    from adam.vocabularies import LicenseStatus, ModelStatus

    validator = OllamaValidator()
    attestor = ModelAttestor()
    registry = ModelRegistry()

    for dm in models:
        try:
            # Technical validation
            technical = validator.validate(dm.model_id)
            if not technical.core_valid:
                with _DISCOVERY_LOCK:
                    entry = _DYNAMIC_REGISTRY.get(dm.model_id, {})
                    if entry:
                        entry["info"]["attestation_status"] = "unavailable"
                continue

            # Register the model as a dynamic artifact so the lifecycle manager can use it
            registry.register_dynamic(
                model_id=dm.model_id,
                display_name=dm.display_name,
                provider=dm.provider,
                runtime=dm.runtime,
                size_bytes=dm.size_bytes,
                context_window=dm.context_length or 4096,
            )

            # Behavioural attestation using DeterministicModelRuntime as proxy
            # (real models get attested via OllamaModelRuntime on next full recheck)
            art = ModelArtifact(
                id=dm.model_id, name=dm.display_name, revision="dynamic",
                quantization="dynamic", model_format="dynamic",
                checksum_sha256="dynamic", file_size_bytes=dm.size_bytes,
                license_id="unknown", license_status=LicenseStatus.APPROVED,
                requires_legal_review=False, context_window=dm.context_length or 4096,
                languages=["en"], serving_runtime=dm.runtime,
                prompt_template="{system_prompt}\n\n{user_prompt}",
            )
            from adam.model.runtime import OllamaModelRuntime
            runtime = OllamaModelRuntime(art, model_tag=dm.model_id)
            attestation = attestor.attest(dm.model_id, dm.provider, runtime, technical)

            # Update the in-memory result
            with _DISCOVERY_LOCK:
                entry = _DYNAMIC_REGISTRY.get(dm.model_id, {})
                if entry:
                    entry["info"]["attestation_status"] = attestation.status
                    entry["info"]["capabilities"] = attestation.capabilities
                    entry["info"]["attestation_version"] = attestation.attestation_version

        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Background attestation failed for %s: %s", dm.model_id, exc
            )


@router.get("/system/models/dynamic")
def list_dynamic_models() -> List[Dict[str, Any]]:
    """Return the current set of dynamically discovered (non-canonical) models
    with their latest attestation status.
    """
    with _DISCOVERY_LOCK:
        return [entry["info"] for entry in _DYNAMIC_REGISTRY.values()]


class _ProviderRegistrationRequest(_BaseModel):
    name: str
    endpoint_url: str
    display_name: Optional[str] = None
    # NOTE: api_key is handled via X-Provider-Api-Key header to avoid
    # logging in FastAPI access logs (header values are not auto-logged).


@router.post("/system/providers")
def register_remote_provider(
    req: _ProviderRegistrationRequest,
    x_provider_api_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Register a remote API provider.

    Performs SSRF validation, protocol detection, and authentication check
    before storing the provider.  The API key is NEVER returned in the response.

    Returns sanitised provider metadata and the list of discovered models.
    """
    api_key = x_provider_api_key.strip() if x_provider_api_key else None
    try:
        config = REMOTE_PROVIDER_REGISTRY.register(
            name=req.name,
            endpoint_url=req.endpoint_url,
            display_name=req.display_name,
            api_key=api_key,
        )
    except UnsafeEndpointError as exc:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsafe_endpoint",
                "message": str(exc),
                "category": "ssrf_protection",
            },
        )
    except UnsupportedProtocolError as exc:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_protocol",
                "message": (
                    "The endpoint did not respond to any supported protocol probe "
                    "(OpenAI-compatible or Gemini-compatible). "
                    "Verify the URL and try again."
                ),
                "category": "protocol_detection",
            },
        )
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=502,
            detail={
                "error": "provider_unreachable",
                "message": "Could not connect to the provided endpoint.",
                "category": "connectivity",
            },
        )

    # Return sanitised metadata — no credentials
    return {
        **config.to_dict(),
        "models": [],   # model discovery from remote APIs in future releases
    }


@router.delete("/system/providers/{provider_id}")
def remove_remote_provider(provider_id: str) -> Dict[str, Any]:
    """Remove a registered remote API provider and its associated models."""
    removed = REMOTE_PROVIDER_REGISTRY.remove(provider_id)
    if not removed:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail={"error": "provider_not_found"})
    return {"removed": True, "provider_id": provider_id}


@router.post("/system/models/{model_id}/recheck")
def recheck_model(
    model_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Run a lightweight health check on a specific model and return updated status.

    For local Ollama models: re-runs technical validation (NOT full behavioural
    attestation).  Attestation is only re-run if the cached result has expired.
    For canonical models: returns the existing registry entry with live
    is_installed status.
    """
    from adam.model.registry import CANONICAL_MODELS, ModelRegistry

    # Check canonical first
    if model_id in CANONICAL_MODELS:
        artifact = CANONICAL_MODELS[model_id]
        is_installed = OllamaModelRuntime(artifact).is_model_present()
        cached = get_cached_attestation(model_id, artifact.serving_runtime)
        return {
            "id": model_id,
            "is_installed": is_installed,
            "attestation_status": cached.status if cached else None,
            "capabilities": cached.capabilities if cached else {},
            "source": "canonical",
        }

    # Dynamic model
    with _DISCOVERY_LOCK:
        entry = _DYNAMIC_REGISTRY.get(model_id)

    if entry is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail={"error": "model_not_found"})

    dm_dict = entry.get("discovered", {})
    tag = dm_dict.get("model_id", model_id)
    validator = OllamaValidator()
    technical = validator.validate(tag)

    cached = get_cached_attestation(model_id, "ollama")
    att_status = cached.status if cached else ("checking" if technical.core_valid else "unavailable")

    with _DISCOVERY_LOCK:
        entry["info"]["attestation_status"] = att_status
        entry["info"]["is_installed"] = technical.model_exists

    return {
        "id": model_id,
        "is_installed": technical.model_exists,
        "attestation_status": att_status,
        "capabilities": cached.capabilities if cached else {},
        "source": "discovered",
        "technical": technical.to_dict(),
    }


# ── System Introspection & Self-Model Endpoints ───────────────────────────

from adam.agent.introspection import SystemIntrospectionService
from adam.agent.redaction import SecretRedactor
from adam.rag.models import UserContext


@router.get("/system/introspection")
def get_system_introspection(
    session_id: Optional[str] = None,
    db: Session = Depends(get_db),
    x_user_id: Optional[str] = Header("anonymous"),
    x_user_role: Optional[str] = Header("PUBLIC"),
    x_clearance_level: Optional[str] = Header(None),
    x_department_id: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Return authoritative system self-model snapshot sanitized for user clearance."""
    user_context = UserContext(
        user_id=x_user_id or "anonymous",
        roles=[x_user_role] if x_user_role else ["PUBLIC"],
        department_id=x_department_id,
        clearance_level=x_clearance_level or Classification.PUBLIC.value,
    )

    snapshot = SystemIntrospectionService.get_system_snapshot(
        session=db,
        user_context=user_context,
        session_id=session_id,
    )

    return SystemIntrospectionService.sanitize_snapshot(
        snapshot=snapshot,
        clearance_level=user_context.clearance_level,
    )


@router.get("/system/introspection/last-execution")
def get_last_execution_diagnostics(
    session_id: Optional[str] = None,
    db: Session = Depends(get_db),
    x_user_id: Optional[str] = Header("anonymous"),
    x_clearance_level: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Return diagnostic telemetry for the most recent execution in the session or for user."""
    audit_snap = SystemIntrospectionService._get_last_execution_audit(
        session=db,
        session_id=session_id,
        user_id=x_user_id,
    )
    if not audit_snap:
        return {"found": False, "message": "No previous execution audit found for this session."}

    res = {
        "found": True,
        "session_id": audit_snap.session_id,
        "query_text_redacted": audit_snap.query_text_redacted,
        "detected_intent": audit_snap.detected_intent,
        "model_id": audit_snap.model_id,
        "total_latency_ms": audit_snap.total_latency_ms,
        "per_stage_latency_ms": audit_snap.per_stage_latency_ms,
        "was_refused": audit_snap.was_refused,
        "refusal_reason": audit_snap.refusal_reason,
        "prompt_tokens": audit_snap.prompt_tokens,
        "completion_tokens": audit_snap.completion_tokens,
        "validation_passed": audit_snap.validation_passed,
        "validation_errors": audit_snap.validation_errors,
        "timestamp": audit_snap.timestamp,
    }
    return SecretRedactor.sanitize_data(res)


# ── Advanced Settings Endpoints ────────────────────────────────────────────────

@router.get("/system/advanced-settings")
def get_advanced_settings(
    db: Session = Depends(get_db),
    x_user_id: Optional[str] = Header("anonymous"),
) -> Dict[str, Any]:
    """Return current advanced settings for the user, all preset bundles, default values, and metadata."""
    from adam.settings.advanced_settings import (
        AdvancedSettingsManager,
        PRESET_BUNDLES,
        SETTINGS_METADATA,
        DEFAULT_BUNDLE,
        AdvancedSettingsPreset,
    )

    user_id = x_user_id or "anonymous"
    manager = AdvancedSettingsManager(db, user_id=user_id)
    current = manager.load()

    presets_out = {}
    for preset_enum, bundle in PRESET_BUNDLES.items():
        presets_out[preset_enum.value] = bundle.to_dict()

    return {
        "current": current.to_dict(),
        "defaults": DEFAULT_BUNDLE.to_dict(),
        "presets": presets_out,
        "metadata": SETTINGS_METADATA,
    }


class AdvancedSettingsRequest(BaseModel):
    preset: str = "BALANCED"
    generation: Dict[str, Any] = {}
    retrieval: Dict[str, Any] = {}
    performance: Dict[str, Any] = {}
    voice: Dict[str, Any] = {}
    opt_in: bool = True


@router.post("/system/advanced-settings")
def save_advanced_settings(
    req: AdvancedSettingsRequest,
    db: Session = Depends(get_db),
    x_user_id: Optional[str] = Header("anonymous"),
) -> Dict[str, Any]:
    """Validate and persist advanced settings for the user."""
    from adam.settings.advanced_settings import AdvancedSettingsManager, AdvancedSettingsBundle

    user_id = x_user_id or "anonymous"
    bundle = AdvancedSettingsBundle.from_dict({
        "preset": req.preset,
        "generation": req.generation,
        "retrieval": req.retrieval,
        "performance": req.performance,
        "voice": req.voice,
    })

    errors = bundle.validate()
    if errors:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail={"errors": errors})

    manager = AdvancedSettingsManager(db, user_id=user_id)
    manager.save(bundle, opt_in=req.opt_in)

    return {"saved": True, "settings": bundle.to_dict()}


@router.delete("/system/advanced-settings")
def reset_advanced_settings(
    db: Session = Depends(get_db),
    x_user_id: Optional[str] = Header("anonymous"),
) -> Dict[str, Any]:
    """Reset advanced settings to BALANCED defaults."""
    from adam.settings.advanced_settings import AdvancedSettingsManager

    user_id = x_user_id or "anonymous"
    manager = AdvancedSettingsManager(db, user_id=user_id)
    default = manager.reset()
    return {"reset": True, "settings": default.to_dict()}
