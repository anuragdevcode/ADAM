"""Human-in-the-loop QA and page review queue endpoints."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from adam.api.deps import get_db, get_user_context, require_roles
from adam.db.models import AuditEvent, Document, DocumentPage, DocumentVersion, ReviewAnnotation
from adam.rag.models import UserContext
from adam.vocabularies import ReviewStatus

router = APIRouter()


class PageCorrectionRequest(BaseModel):
    corrected_text: str
    reviewer: Optional[str] = "officer"


@router.get("/review/pages")
def list_review_pages(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_roles("ADMIN", "OFFICER", "REVIEWER")),
) -> List[Dict[str, Any]]:
    """List document pages requiring human QA or reviewer verification."""
    query = (
        db.query(DocumentPage)
        .join(DocumentVersion, DocumentPage.version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
    )

    if status and status != "ALL":
        query = query.filter(DocumentPage.review_status == status)
    else:
        # Default to flagged and pending
        query = query.filter(
            DocumentPage.review_status.in_([ReviewStatus.FLAGGED.value, ReviewStatus.PENDING.value, ReviewStatus.CORRECTED.value])
        )

    pages = query.order_by(DocumentPage.created_at.desc()).limit(100).all()

    items = []
    for p in pages:
        ver = p.version
        doc = ver.document if ver else None
        items.append(
            {
                "id": p.id,
                "version_id": p.version_id,
                "document_id": doc.id if doc else None,
                "document_title": doc.title if doc else "Unknown",
                "go_number": ver.go_number if ver else None,
                "page_number": p.page_number,
                "word_count": p.word_count,
                "is_scanned": bool(p.is_scanned),
                "text_confidence": round(p.text_confidence, 2) if p.text_confidence else None,
                "review_status": p.review_status,
                "clean_text": p.clean_text,
                "ocr_text": p.ocr_text,
                "selected_text": p.selected_text or p.clean_text or p.ocr_text,
            }
        )

    return items


@router.post("/review/pages/{page_id}/approve")
def approve_page(
    page_id: str,
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_roles("ADMIN", "OFFICER", "REVIEWER")),
) -> Dict[str, Any]:
    """Approve a flagged or pending page into the authoritative corpus."""
    page = db.query(DocumentPage).filter(DocumentPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    page.review_status = ReviewStatus.REVIEWED.value
    audit = AuditEvent(
        entity_type="DOCUMENT_PAGE",
        entity_id=page.id,
        action="PAGE_APPROVE",
        actor=user_ctx.user_id,
        details_json={"page_number": page.page_number},
        timestamp=datetime.now(timezone.utc),
    )
    db.add(audit)
    db.commit()

    return {"success": True, "page_id": page.id, "review_status": page.review_status}


@router.post("/review/pages/{page_id}/correct")
def correct_page(
    page_id: str,
    req: PageCorrectionRequest,
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_roles("ADMIN", "OFFICER", "REVIEWER")),
) -> Dict[str, Any]:
    """Submit a reviewer correction without mutating original raw/born-digital transcripts."""
    page = db.query(DocumentPage).filter(DocumentPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    now = datetime.now(timezone.utc)
    annotation = ReviewAnnotation(
        page_id=page.id,
        annotation_type="TEXT_CORRECTION",
        corrected_text=req.corrected_text,
        reviewer=req.reviewer or user_ctx.user_id,
        created_at=now,
    )
    db.add(annotation)

    page.review_status = ReviewStatus.CORRECTED.value
    page.selected_text = req.corrected_text

    audit = AuditEvent(
        entity_type="DOCUMENT_PAGE",
        entity_id=page.id,
        action="PAGE_CORRECT",
        actor=user_ctx.user_id,
        details_json={"page_number": page.page_number, "annotation_id": annotation.id},
        timestamp=now,
    )
    db.add(audit)
    db.commit()

    return {"success": True, "page_id": page.id, "review_status": page.review_status, "annotation_id": annotation.id}
