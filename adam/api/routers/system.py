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


class ValidateKeyRequest(BaseModel):
    api_key: str


@router.post("/system/validate-gemini-key")
def validate_gemini_key(req: ValidateKeyRequest) -> Dict[str, Any]:
    """Test validity of a user-provided Google Gemini API key securely without persisting it."""
    key = req.api_key.strip()
    if not key:
        return {"valid": False, "message": "API key cannot be empty."}

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
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
        return {
            "valid": False,
            "message": f"Connection to Google API failed: {str(e)}",
        }


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

