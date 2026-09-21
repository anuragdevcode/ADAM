"""Data acquisition sources and connector governance endpoints."""

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from adam.api.deps import get_db, get_user_context
from adam.connectors.registry import ConnectorRegistry
from adam.db.models import Document, Source, IngestionJob
from adam.rag.models import UserContext
from adam.vocabularies import SourceStatus, Classification, RefreshCadence, DepartmentId

router = APIRouter()


class CreateSourceRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    department_id: str = Field(default="UNKNOWN")
    owner_name: str = Field(default="Administrative Officer")
    owner_contact: str = Field(default="admin@uk.gov.in")
    written_authority_ref: Optional[str] = Field(default="GOV-REF-AUTO")
    source_type: str = Field(default="WEBSITE")  # WEBSITE, DATABASE, FILE_UPLOAD, CUSTOM
    permitted_domains: Optional[List[str]] = Field(default_factory=list)
    permitted_path_prefixes: Optional[List[str]] = Field(default_factory=lambda: ["/"])
    config_json: Optional[Dict[str, Any]] = Field(default_factory=dict)
    access_classification: Optional[str] = Field(default=Classification.PUBLIC.value)
    refresh_cadence: Optional[str] = Field(default=RefreshCadence.WEEKLY.value)
    rate_limit_per_minute: Optional[int] = Field(default=30)


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Return all registered data sources, connectors, and crawl status."""
    sources = db.query(Source).order_by(Source.name.asc()).all()

    items = []
    for s in sources:
        doc_count = db.query(Document).filter(Document.source_id == s.id).count()
        domains = s.permitted_domains or []
        domain_str = ", ".join(domains) if isinstance(domains, list) else str(domains)

        active_job = (
            db.query(IngestionJob)
            .filter(
                IngestionJob.source_id == s.id,
                IngestionJob.status.in_(["QUEUED", "DISCOVERY", "PROCESSING", "DRAINING", "CANCELLING"]),
            )
            .order_by(IngestionJob.started_at.desc())
            .first()
        )

        items.append(
            {
                "id": s.id,
                "name": s.name,
                "department_id": s.department_id,
                "owner_name": s.owner_name,
                "owner_contact": s.owner_contact,
                "source_type": s.source_type or "WEBSITE",
                "permitted_domains": domains,
                "permitted_path_prefixes": s.permitted_path_prefixes or ["/"],
                "base_url": domain_str,
                "config_json": s.config_json or {},
                "status": s.status,
                "refresh_cadence": s.refresh_cadence,
                "access_classification": s.access_classification,
                "document_count": doc_count,
                "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
                "last_run_status": s.last_run_status,
                "active_job_id": active_job.id if active_job else None,
                "active_job_status": active_job.status if active_job else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
        )

    return items


@router.get("/sources/{source_id}")
def get_source(source_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retrieve detailed configuration for a specific data source."""
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    doc_count = db.query(Document).filter(Document.source_id == source.id).count()
    return {
        "id": source.id,
        "name": source.name,
        "department_id": source.department_id,
        "owner_name": source.owner_name,
        "owner_contact": source.owner_contact,
        "source_type": source.source_type or "WEBSITE",
        "permitted_domains": source.permitted_domains or [],
        "permitted_path_prefixes": source.permitted_path_prefixes or ["/"],
        "config_json": source.config_json or {},
        "status": source.status,
        "refresh_cadence": source.refresh_cadence,
        "access_classification": source.access_classification,
        "rate_limit_per_minute": source.rate_limit_per_minute,
        "document_count": doc_count,
        "last_run_at": source.last_run_at.isoformat() if source.last_run_at else None,
        "last_run_status": source.last_run_status,
        "created_at": source.created_at.isoformat() if source.created_at else None,
    }


@router.post("/sources")
def create_source(
    req: CreateSourceRequest,
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> Dict[str, Any]:
    """Onboard a new data source (Website, Database, File Batch, or Custom)."""
    source_id = f"src_{uuid.uuid4().hex[:12]}"
    source = Source(
        id=source_id,
        name=req.name.strip(),
        department_id=DepartmentId.validate_or_preserve(req.department_id),
        owner_name=req.owner_name.strip(),
        owner_contact=req.owner_contact.strip(),
        written_authority_ref=req.written_authority_ref or "GOV-AUTH-01",
        source_type=req.source_type.upper(),
        permitted_domains=req.permitted_domains or [],
        permitted_path_prefixes=req.permitted_path_prefixes or ["/"],
        config_json=req.config_json or {},
        access_classification=req.access_classification or Classification.PUBLIC.value,
        refresh_cadence=req.refresh_cadence or RefreshCadence.WEEKLY.value,
        rate_limit_per_minute=req.rate_limit_per_minute or 30,
        status=SourceStatus.APPROVED.value,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    return {
        "id": source.id,
        "name": source.name,
        "source_type": source.source_type,
        "status": source.status,
        "message": "Source onboarded and approved for ingestion.",
    }


@router.post("/sources/{source_id}/test-connection")
def test_source_connection(
    source_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Test reachability, credentials, or permissions for a source without initiating crawling."""
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    connector = ConnectorRegistry.resolve_connector(source)
    success, message = connector.test_connection(source)

    return {
        "source_id": source.id,
        "name": source.name,
        "source_type": source.source_type or "WEBSITE",
        "success": success,
        "message": message,
    }


@router.post("/sources/{source_id}/toggle-status")
def toggle_source_status(
    source_id: str,
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> Dict[str, Any]:
    """Toggle source status between APPROVED and PAUSED."""
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    new_status = (
        SourceStatus.PAUSED.value
        if source.status == SourceStatus.APPROVED.value
        else SourceStatus.APPROVED.value
    )
    source.status = new_status
    db.commit()

    return {
        "id": source.id,
        "name": source.name,
        "status": source.status,
        "message": f"Source status updated to {new_status}",
    }


@router.delete("/sources/{source_id}")
def delete_source(
    source_id: str,
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> Dict[str, Any]:
    """Soft-remove a data source while preserving document provenance and audit history."""
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    source.status = SourceStatus.REMOVED.value
    db.commit()

    return {
        "id": source.id,
        "status": source.status,
        "message": f"Source '{source.name}' soft-removed. Historical evidence preserved intact.",
    }
