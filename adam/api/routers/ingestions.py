"""Unified Ingestion Control Plane API endpoints for job lifecycle management and telemetry."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from adam.api.deps import get_db, get_user_context
from adam.db.models import IngestionJob, IngestionJobItem, Source
from adam.ingest.control_plane import GLOBAL_INGESTION_CONTROL_PLANE
from adam.rag.models import UserContext

router = APIRouter(prefix="/ingestion", tags=["ingestion-control-plane"])


class TriggerJobRequest(BaseModel):
    source_id: str = Field(..., description="Target registered source ID")
    job_type: str = Field(default="FULL", description="FULL or INCREMENTAL")
    max_items: Optional[int] = Field(default=None, description="Optional maximum items limit")


class JobActionResponse(BaseModel):
    job_id: str
    status: str
    message: str


@router.post("/jobs")
async def trigger_job(
    req: Optional[TriggerJobRequest] = None,
    source_id: Optional[str] = Form(None),
    job_type: Optional[str] = Form("FULL"),
    max_items: Optional[int] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> Dict[str, Any]:
    """Trigger an ingestion job (Full or Incremental, with optional uploaded files)."""
    target_source_id = (req.source_id if req else None) or source_id
    if not target_source_id:
        raise HTTPException(status_code=400, detail="source_id is required.")

    target_job_type = (req.job_type if req else None) or job_type or "FULL"
    target_max_items = (req.max_items if req else None) or max_items

    source = db.query(Source).filter(Source.id == target_source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source '{target_source_id}' not found.")

    # Read uploaded files if provided
    file_tuples: Optional[List[tuple[str, bytes]]] = None
    if files:
        file_tuples = []
        for f in files:
            content = await f.read()
            file_tuples.append((f.filename or "upload.pdf", content))

    job = GLOBAL_INGESTION_CONTROL_PLANE.start_job(
        source_id=target_source_id,
        job_type=target_job_type,
        files=file_tuples,
        max_items=target_max_items,
        user_id=user_ctx.user_id,
    )

    return {
        "job_id": job.id,
        "source_id": job.source_id,
        "status": job.status,
        "job_type": job.job_type,
        "current_stage": job.current_stage,
        "message": f"Ingestion job '{job.id}' enqueued successfully.",
    }


@router.get("/jobs")
def list_jobs(
    source_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List recent ingestion jobs with status and progress aggregates."""
    query = db.query(IngestionJob)
    if source_id:
        query = query.filter(IngestionJob.source_id == source_id)
    if status:
        query = query.filter(IngestionJob.status == status.upper())

    jobs = query.order_by(IngestionJob.started_at.desc()).limit(limit).all()

    result = []
    for j in jobs:
        source_name = j.source.name if j.source else "Unknown Source"
        result.append(
            {
                "id": j.id,
                "source_id": j.source_id,
                "source_name": source_name,
                "status": j.status,
                "job_type": j.job_type,
                "current_stage": j.current_stage,
                "count_found": j.count_found,
                "count_ingested": j.count_ingested,
                "count_skipped": j.count_skipped,
                "count_failed": j.count_failed,
                "progress_pct": j.progress_pct,
                "error_message": j.error_message,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
        )
    return result


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retrieve detailed state and metrics for a specific ingestion job."""
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Ingestion job '{job_id}' not found.")

    source_name = job.source.name if job.source else "Unknown Source"
    return {
        "id": job.id,
        "source_id": job.source_id,
        "source_name": source_name,
        "status": job.status,
        "job_type": job.job_type,
        "current_stage": job.current_stage,
        "count_found": job.count_found,
        "count_ingested": job.count_ingested,
        "count_skipped": job.count_skipped,
        "count_failed": job.count_failed,
        "progress_pct": job.progress_pct,
        "checkpoint": job.checkpoint_json or {},
        "failures": job.failures_json or [],
        "metrics": job.metrics_json or {},
        "error_message": job.error_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/jobs/{job_id}/items")
def get_job_items(
    job_id: str,
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Paginated items list for an ingestion job, preventing DOM and memory overload."""
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Ingestion job '{job_id}' not found.")

    query = db.query(IngestionJobItem).filter(IngestionJobItem.job_id == job_id)
    if status:
        query = query.filter(IngestionJobItem.status == status.upper())

    total = query.count()
    offset = (page - 1) * page_size
    items = query.order_by(IngestionJobItem.created_at.desc()).offset(offset).limit(page_size).all()

    items_data = []
    for item in items:
        items_data.append(
            {
                "id": item.id,
                "item_key": item.item_key,
                "title": item.title,
                "status": item.status,
                "sha256": item.sha256,
                "document_id": item.document_id,
                "version_id": item.version_id,
                "error_message": item.error_message,
                "retry_count": item.retry_count,
                "duration_ms": item.duration_ms,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
        )

    return {
        "job_id": job_id,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items_data,
    }


@router.post("/jobs/{job_id}/pause", response_model=JobActionResponse)
def pause_job(
    job_id: str,
    user_ctx: UserContext = Depends(get_user_context),
) -> JobActionResponse:
    """Request cooperative pause on an active job."""
    try:
        job = GLOBAL_INGESTION_CONTROL_PLANE.pause_job(job_id, user_id=user_ctx.user_id)
        return JobActionResponse(
            job_id=job.id,
            status=job.status,
            message="Pause requested. Job will enter PAUSED state after in-flight items finish.",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/jobs/{job_id}/resume", response_model=JobActionResponse)
def resume_job(
    job_id: str,
    user_ctx: UserContext = Depends(get_user_context),
) -> JobActionResponse:
    """Resume a PAUSED job from its compound cursor checkpoint."""
    try:
        job = GLOBAL_INGESTION_CONTROL_PLANE.resume_job(job_id, user_id=user_ctx.user_id)
        return JobActionResponse(
            job_id=job.id,
            status=job.status,
            message="Job resumed successfully from saved checkpoint.",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/jobs/{job_id}/stop", response_model=JobActionResponse)
def stop_job(
    job_id: str,
    user_ctx: UserContext = Depends(get_user_context),
) -> JobActionResponse:
    """Request cooperative cancellation of an active job."""
    try:
        job = GLOBAL_INGESTION_CONTROL_PLANE.stop_job(job_id, user_id=user_ctx.user_id)
        return JobActionResponse(
            job_id=job.id,
            status=job.status,
            message="Cancellation requested. In-flight items rolling back.",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/jobs/{job_id}/retry")
def retry_failed_items(
    job_id: str,
    user_ctx: UserContext = Depends(get_user_context),
) -> Dict[str, Any]:
    """Trigger a retry job that re-attempts only the failed items from a prior job."""
    try:
        retry_job = GLOBAL_INGESTION_CONTROL_PLANE.retry_job(job_id, user_id=user_ctx.user_id)
        return {
            "retry_job_id": retry_job.id,
            "parent_job_id": job_id,
            "status": retry_job.status,
            "items_to_retry": retry_job.count_found,
            "message": f"Retry job '{retry_job.id}' created for {retry_job.count_found} failed items.",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/jobs/{job_id}/stream")
async def stream_job_progress(job_id: str):
    """Stream real-time, throttled job progress via Server-Sent Events (SSE)."""
    return StreamingResponse(
        GLOBAL_INGESTION_CONTROL_PLANE.stream_job_telemetry(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
