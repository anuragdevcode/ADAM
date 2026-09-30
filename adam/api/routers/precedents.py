"""Precedent references and statutory relationship chain endpoints."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from adam.api.deps import get_db, get_user_context
from adam.api.services.acl_service import AclService
from adam.db.models import Document, DocumentVersion, PrecedentReference
from adam.rag.models import UserContext

router = APIRouter()


@router.get("/precedents")
def list_precedents(
    relation_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> List[Dict[str, Any]]:
    """Return verified precedent relationships, supersessions, and statutory links."""
    allowed_classifications = AclService.get_accessible_classifications(
        user_ctx.clearance_level, user_ctx.is_admin()
    )

    query = (
        db.query(PrecedentReference)
        .join(DocumentVersion, PrecedentReference.source_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .filter(Document.classification.in_(allowed_classifications))
    )

    if relation_type and relation_type != "ALL":
        query = query.filter(PrecedentReference.relation_type == relation_type)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            PrecedentReference.cited_order_number.ilike(term)
            | PrecedentReference.raw_citation_text.ilike(term)
            | Document.title.ilike(term)
        )

    records = query.limit(limit).all()

    results = []
    for pr in records:
        source_ver = pr.source_version
        source_doc = source_ver.document if source_ver else None
        target_doc = pr.target_document

        results.append(
            {
                "id": pr.id,
                "source_document_id": source_doc.id if source_doc else None,
                "source_title": source_doc.title if source_doc else "Unknown Source",
                "source_go_number": source_ver.go_number if source_ver else None,
                "source_department_id": source_doc.department_id if source_doc else None,
                "relation_type": pr.relation_type,
                "cited_order_number": pr.cited_order_number,
                "cited_act_or_rule": pr.cited_act_or_rule,
                "target_document_id": target_doc.id if target_doc else None,
                "target_title": target_doc.title if target_doc else None,
                "raw_citation_text": pr.raw_citation_text,
                "created_at": pr.created_at.isoformat() if pr.created_at else None,
            }
        )

    return results
