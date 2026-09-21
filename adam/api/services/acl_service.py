"""Centralized Access Control List (ACL) and security clearance authorization service."""

from datetime import datetime, timezone
from typing import List, Optional, Set
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session, Query

from adam.db.models import Document, AccessGrant
from adam.rag.models import UserContext
from adam.vocabularies import Classification, AccessAction


class AclService:
    """Centralized authorization engine for document inspection, browsing, and download."""

    CLEARANCE_HIERARCHY = {
        Classification.PUBLIC.value: [Classification.PUBLIC.value],
        Classification.INTERNAL.value: [Classification.PUBLIC.value, Classification.INTERNAL.value],
        Classification.RESTRICTED.value: [
            Classification.PUBLIC.value,
            Classification.INTERNAL.value,
            Classification.RESTRICTED.value,
        ],
        Classification.CONFIDENTIAL.value: [
            Classification.PUBLIC.value,
            Classification.INTERNAL.value,
            Classification.RESTRICTED.value,
            Classification.CONFIDENTIAL.value,
        ],
    }

    @classmethod
    def get_accessible_classifications(cls, clearance_level: str, is_admin: bool = False) -> List[str]:
        """Calculate accessible classifications based on standard clearance hierarchy."""
        if is_admin:
            return [c.value for c in Classification]
        return cls.CLEARANCE_HIERARCHY.get(clearance_level, [Classification.PUBLIC.value])

    @classmethod
    def can_access_document(cls, user_ctx: UserContext, doc: Document, db: Session) -> bool:
        """Evaluate whether user context is authorized to view a document under ACL and clearance rules."""
        if user_ctx.is_admin():
            return True

        # PUBLIC documents are accessible to all officers and citizens
        if doc.classification == Classification.PUBLIC.value:
            return True

        now = datetime.now(timezone.utc)
        subjects = [user_ctx.user_id] + list(user_ctx.roles or [])

        # Check for explicit active AccessGrants
        grants = (
            db.query(AccessGrant)
            .filter(
                AccessGrant.subject_id.in_(subjects),
                or_(AccessGrant.document_id == doc.id, AccessGrant.classification == doc.classification),
                AccessGrant.action.in_([AccessAction.READ.value, AccessAction.ADMIN.value, "READ", "ADMIN"]),
                or_(AccessGrant.expires_at.is_(None), AccessGrant.expires_at > now),
            )
            .all()
        )

        has_explicit_doc_grant = any(g.document_id == doc.id for g in grants)
        has_explicit_class_grant = any(g.classification == doc.classification for g in grants)

        # Clearance level check
        allowed_classifications = cls.get_accessible_classifications(user_ctx.clearance_level, False)
        clearance_permitted = (doc.classification in allowed_classifications) or has_explicit_class_grant

        if not (clearance_permitted or has_explicit_doc_grant):
            return False

        # If explicit document grant exists, it overrides departmental boundary
        if has_explicit_doc_grant:
            return True

        # Check department boundary for non-public records
        if user_ctx.department_id and doc.department_id and doc.department_id != user_ctx.department_id:
            return False

        return True

    @classmethod
    def apply_document_query_acl(
        cls,
        query: Query,
        user_ctx: UserContext,
        db: Session,
    ) -> Query:
        """Filter a Document query to only include records authorized for the user."""
        if user_ctx.is_admin():
            return query

        now = datetime.now(timezone.utc)
        subjects = [user_ctx.user_id] + list(user_ctx.roles or [])

        # Active grants
        active_grants = (
            db.query(AccessGrant)
            .filter(
                AccessGrant.subject_id.in_(subjects),
                AccessGrant.action.in_([AccessAction.READ.value, AccessAction.ADMIN.value, "READ", "ADMIN"]),
                or_(AccessGrant.expires_at.is_(None), AccessGrant.expires_at > now),
            )
            .all()
        )

        granted_doc_ids: Set[str] = {g.document_id for g in active_grants if g.document_id}
        granted_classifications: Set[str] = {g.classification for g in active_grants if g.classification}

        conditions = [Document.classification == Classification.PUBLIC.value]

        if granted_doc_ids:
            conditions.append(Document.id.in_(list(granted_doc_ids)))

        # Clearance hierarchy conditions
        allowed = cls.get_accessible_classifications(user_ctx.clearance_level, False)

        for c_val in [Classification.INTERNAL.value, Classification.RESTRICTED.value]:
            if c_val in allowed or c_val in granted_classifications:
                if user_ctx.department_id:
                    conditions.append(
                        and_(Document.classification == c_val, Document.department_id == user_ctx.department_id)
                    )
                elif c_val in granted_classifications:
                    conditions.append(Document.classification == c_val)

        if Classification.CONFIDENTIAL.value in granted_classifications:
            conditions.append(Document.classification == Classification.CONFIDENTIAL.value)

        return query.filter(or_(*conditions))
