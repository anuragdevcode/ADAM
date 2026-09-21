"""V1 Documents API with authorized streaming and stealth 404 access control."""

import io
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from adam.api.deps import get_db, get_user_context
from adam.api.services.acl_service import AclService
from adam.db.models import Document, DocumentVersion, DocumentPage, AccessGrant
from adam.rag.models import UserContext
from adam.storage.base import get_storage_backend
from adam.vocabularies import Classification, AccessAction

router = APIRouter(prefix="/v1", tags=["v1-documents"])


def can_access_document(user_ctx: UserContext, doc: Document, db: Session) -> bool:
    """Evaluate whether the given user context is authorized to view the document."""
    return AclService.can_access_document(user_ctx, doc, db)


@router.get("/documents/{doc_id}/versions/{version_id}/pages/{page_num}")
def get_original_page(
    doc_id: str,
    version_id: str,
    page_num: int,
    request: Request,
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
):
    """Stream original page representation only after authorization.

    Acceptance criterion: 401/403 responses reveal no document existence.
    If the document does not exist OR if the user lacks clearance/authorization,
    returns an identical 404 Not Found error to avoid leaking the existence of classified records.
    """
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("X-Trace-Id") or "trace_default"

    # 1. Lookup document
    doc = db.query(Document).filter(Document.id == doc_id).first()

    # Stealth check: If doc not found, raise 404
    if not doc:
        raise HTTPException(status_code=404, detail="Document or page not found")

    # Stealth check: If user lacks clearance, raise the EXACT SAME 404 to reveal zero existence
    if not can_access_document(user_ctx, doc, db):
        raise HTTPException(status_code=404, detail="Document or page not found")

    # 2. Lookup version
    ver = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.id == version_id, DocumentVersion.document_id == doc_id)
        .first()
    )
    if not ver:
        raise HTTPException(status_code=404, detail="Document or page not found")

    # 3. Lookup page
    page = (
        db.query(DocumentPage)
        .filter(DocumentPage.version_id == version_id, DocumentPage.page_number == page_num)
        .first()
    )
    if not page:
        raise HTTPException(status_code=404, detail="Document or page not found")

    storage = get_storage_backend()

    # If page image exists in storage, stream image bytes
    if page.image_key and storage.exists(page.image_key):
        img_bytes = storage.retrieve(page.image_key)
        return Response(
            content=img_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "private, no-cache, no-store, must-revalidate",
                "X-Trace-Id": trace_id,
            },
        )

    # Fallback to streaming raw page text or version content
    if page.clean_text:
        return Response(
            content=page.clean_text.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={
                "Cache-Control": "private, no-cache, no-store, must-revalidate",
                "X-Trace-Id": trace_id,
            },
        )

    # Check if raw version PDF is available in storage
    if ver.original_object_key and storage.exists(ver.original_object_key):
        pdf_bytes = storage.retrieve(ver.original_object_key)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Cache-Control": "private, no-cache, no-store, must-revalidate",
                "X-Trace-Id": trace_id,
            },
        )

    raise HTTPException(status_code=404, detail="Document or page not found")
