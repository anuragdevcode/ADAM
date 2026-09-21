"""Document repository browsing, inspection, and PDF upload endpoints."""

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from adam.api.deps import get_db, get_user_context
from adam.db.models import (
    Document,
    DocumentAttribute,
    DocumentPage,
    DocumentVersion,
    PrecedentReference,
    Source,
)
from adam.api.services.acl_service import AclService
from adam.ingest.validator import ContentValidator
from adam.rag.models import UserContext
from adam.storage.local import LocalStorageBackend
from adam.vocabularies import (
    Classification,
    DepartmentId,
    DocType,
    LifecycleStatus,
    ProvenanceStatus,
    ReviewStatus,
)

router = APIRouter()


def get_allowed_classifications(clearance_level: str, is_admin: bool = False) -> List[str]:
    """Calculate accessible classifications based on clearance hierarchy."""
    return AclService.get_accessible_classifications(clearance_level, is_admin)


@router.get("/documents")
def list_documents(
    department_id: Optional[str] = None,
    classification: Optional[str] = None,
    doc_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> Dict[str, Any]:
    """List approved repository documents matching criteria with security clearance enforcement."""
    query = db.query(Document)

    # Security Clearance Gate
    allowed_classifications = get_allowed_classifications(user_ctx.clearance_level, user_ctx.is_admin())
    query = query.filter(Document.classification.in_(allowed_classifications))

    if department_id and department_id != "ALL":
        query = query.filter(Document.department_id == department_id)

    if classification and classification != "ALL":
        query = query.filter(Document.classification == classification)

    if doc_type and doc_type != "ALL":
        query = query.filter(Document.doc_type == doc_type)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(or_(Document.title.ilike(term), Document.id.ilike(term)))

    total = query.count()
    docs = query.order_by(Document.created_at.desc()).offset(offset).limit(limit).all()

    # Batch fetch latest versions and page counts to avoid N+1 queries
    doc_ids = [doc.id for doc in docs]
    latest_ver_by_doc: Dict[str, DocumentVersion] = {}
    page_count_by_version: Dict[str, int] = {}

    if doc_ids:
        all_versions = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.document_id.in_(doc_ids))
            .order_by(DocumentVersion.retrieved_at.desc())
            .all()
        )
        for ver in all_versions:
            if ver.document_id not in latest_ver_by_doc:
                latest_ver_by_doc[ver.document_id] = ver

        version_ids = [v.id for v in latest_ver_by_doc.values()]
        if version_ids:
            page_counts_raw = (
                db.query(DocumentPage.version_id, func.count(DocumentPage.id))
                .filter(DocumentPage.version_id.in_(version_ids))
                .group_by(DocumentPage.version_id)
                .all()
            )
            page_count_by_version = dict(page_counts_raw)

    items = []
    for doc in docs:
        latest_ver = latest_ver_by_doc.get(doc.id)
        page_count = page_count_by_version.get(latest_ver.id, 0) if latest_ver else 0

        items.append(
            {
                "id": doc.id,
                "title": doc.title,
                "department_id": doc.department_id,
                "classification": doc.classification,
                "doc_type": doc.doc_type,
                "lifecycle_status": doc.lifecycle_status,
                "source_id": doc.source_id,
                "go_number": latest_ver.go_number if latest_ver else None,
                "issued_on": latest_ver.issued_on.isoformat() if latest_ver and latest_ver.issued_on else None,
                "version_id": latest_ver.id if latest_ver else None,
                "sha256": latest_ver.sha256 if latest_ver else None,
                "provenance_status": latest_ver.provenance_status if latest_ver else "VERIFIED",
                "page_count": page_count,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
        )

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/documents/{document_id}")
def get_document_details(
    document_id: str,
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> Dict[str, Any]:
    """Retrieve complete metadata, pages, and precedent relations for a document."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Centralized ACL Verification
    if not AclService.can_access_document(user_ctx, doc, db):
        raise HTTPException(status_code=403, detail="Clearance level insufficient to view document")

    latest_ver = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.retrieved_at.desc())
        .first()
    )

    pages = []
    precedents = []
    attributes = None

    if latest_ver:
        page_rows = (
            db.query(DocumentPage)
            .filter(DocumentPage.version_id == latest_ver.id)
            .order_by(DocumentPage.page_number.asc())
            .all()
        )
        pages = [
            {
                "id": p.id,
                "page_number": p.page_number,
                "word_count": p.word_count,
                "is_scanned": bool(p.is_scanned),
                "scan_quality_score": p.scan_quality_score,
                "detected_language": p.detected_language,
                "review_status": p.review_status,
                "text_preview": (p.selected_text or p.clean_text or p.ocr_text or "")[:400],
            }
            for p in page_rows
        ]

        prec_rows = (
            db.query(PrecedentReference)
            .filter(PrecedentReference.source_version_id == latest_ver.id)
            .all()
        )
        precedents = [
            {
                "id": pr.id,
                "raw_citation_text": pr.raw_citation_text,
                "cited_order_number": pr.cited_order_number,
                "cited_act_or_rule": pr.cited_act_or_rule,
                "relation_type": pr.relation_type,
            }
            for pr in prec_rows
        ]

        attr = db.query(DocumentAttribute).filter(DocumentAttribute.version_id == latest_ver.id).first()
        if attr:
            attributes = {
                "subject": attr.subject,
                "issuing_authority_title": attr.issuing_authority_title,
                "signatory_name": attr.signatory_name,
                "order_number": attr.order_number,
                "order_date": attr.order_date.isoformat() if attr.order_date else None,
            }

    return {
        "id": doc.id,
        "title": doc.title,
        "department_id": doc.department_id,
        "classification": doc.classification,
        "doc_type": doc.doc_type,
        "lifecycle_status": doc.lifecycle_status,
        "source_id": doc.source_id,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "version": {
            "id": latest_ver.id if latest_ver else None,
            "go_number": latest_ver.go_number if latest_ver else None,
            "sha256": latest_ver.sha256 if latest_ver else None,
            "provenance_status": latest_ver.provenance_status if latest_ver else None,
            "byte_size": latest_ver.byte_size if latest_ver else 0,
        } if latest_ver else None,
        "attributes": attributes,
        "pages": pages,
        "precedents": precedents,
    }


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    department_id: str = Form(default=DepartmentId.FINANCE_TREASURY.value),
    doc_type: str = Form(default=DocType.GO.value),
    classification: str = Form(default=Classification.PUBLIC.value),
    go_number: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> Dict[str, Any]:
    """Upload and validate an official government order or circular PDF."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    filename = file.filename or "upload.pdf"

    # 1. Malware and magic bytes validation (Phase 01 Security Gate)
    val_result = ContentValidator.validate(content, declared_mime_type="application/pdf")
    if not val_result.is_safe:
        raise HTTPException(status_code=400, detail=f"File validation failed: {', '.join(val_result.issues)}")

    # 2. Store securely
    storage = LocalStorageBackend()
    sha256 = hashlib.sha256(content).hexdigest()
    storage_key = f"documents/uploads/{sha256[:16]}_{filename}"
    storage.store(storage_key, content)

    # 3. Create or find default source
    default_source = db.query(Source).first()
    source_id = default_source.id if default_source else "src_upload_manual"

    now = datetime.now(timezone.utc)
    doc = Document(
        source_id=source_id,
        title=title.strip(),
        department_id=department_id,
        classification=classification,
        doc_type=doc_type,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
        created_at=now,
    )
    db.add(doc)
    db.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        source_url=f"upload://{filename}",
        sha256=sha256,
        mime_type="application/pdf",
        byte_size=len(content),
        original_object_key=storage_key,
        provenance_status=ProvenanceStatus.VERIFIED.value,
        go_number=go_number.strip() if go_number else None,
        retrieved_at=now,
    )
    db.add(ver)
    db.flush()

    # 4. Extract pages if valid PDF
    page_count = 0
    try:
        pdf_doc = fitz.open(stream=content, filetype="pdf")
        page_count = len(pdf_doc)
        for p_idx in range(page_count):
            p = pdf_doc[p_idx]
            extracted_text = p.get_text("text") or ""
            d_page = DocumentPage(
                version_id=ver.id,
                page_number=p_idx + 1,
                clean_text=extracted_text,
                selected_text=extracted_text,
                word_count=len(extracted_text.split()),
                review_status=ReviewStatus.AUTO_APPROVED.value if len(extracted_text.strip()) > 30 else ReviewStatus.FLAGGED.value,
                created_at=now,
            )
            db.add(d_page)
    except Exception:
        pass

    db.commit()

    return {
        "success": True,
        "document_id": doc.id,
        "version_id": ver.id,
        "title": doc.title,
        "page_count": page_count,
        "sha256": sha256,
        "status": "STORED_AND_INDEXED",
    }
