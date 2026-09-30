"""Access Control List (ACL) enforcement applied prior to retrieval ranking.

Per Phase 03 specification:
- 'Apply metadata ACLs before ranking'
- 'Pilot gate: 0 cross-tenant/ACL leaks'
- Enforce controlled vocabularies: PUBLIC, INTERNAL, RESTRICTED, CONFIDENTIAL
- Verify non-expired AccessGrant records for protected documents
"""

from datetime import datetime, timezone
from typing import List, Optional, Set, Any
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session, Query

from adam.db.models import DocumentChunk, AccessGrant
from adam.rag.models import UserContext
from adam.vocabularies import Classification, AccessAction


class AclEnforcer:
    """Enforces access control list constraints on document chunks prior to ranking."""

    @classmethod
    def apply_acl_filter(
        cls,
        session: Session,
        query: Query,
        user_context: Optional[UserContext] = None,
    ) -> Query:
        """Apply pre-ranking metadata ACL constraints to a DocumentChunk query.

        Ensures that low-privilege or cross-tenant users cannot see restricted,
        confidential, or other-department internal documents under any circumstances.
        """
        user = user_context or UserContext()

        # System admins bypass departmental filters
        if user.is_admin():
            return query

        # Base condition: PUBLIC documents are always visible to everyone
        conditions = [DocumentChunk.classification == Classification.PUBLIC.value]

        now = datetime.now(timezone.utc)
        subjects = [user.user_id] + list(user.roles)

        # Query active AccessGrants for this user/roles
        active_grants = (
            session.query(AccessGrant)
            .filter(
                AccessGrant.subject_id.in_(subjects),
                AccessGrant.action.in_([AccessAction.READ.value, AccessAction.ADMIN.value, "READ", "ADMIN"]),
                or_(AccessGrant.expires_at.is_(None), AccessGrant.expires_at > now),
            )
            .all()
        )

        granted_doc_ids: Set[str] = {g.document_id for g in active_grants if g.document_id}
        granted_classifications: Set[str] = {g.classification for g in active_grants if g.classification}

        # 1. Any explicitly granted document IDs
        if granted_doc_ids:
            conditions.append(DocumentChunk.document_id.in_(list(granted_doc_ids)))

        # 2. INTERNAL documents:
        # Accessible if:
        # - User clearance is INTERNAL/RESTRICTED/CONFIDENTIAL and department matches user's department, OR
        # - User has explicit grant for INTERNAL classification
        if Classification.INTERNAL.value in granted_classifications:
            conditions.append(DocumentChunk.classification == Classification.INTERNAL.value)
        elif user.clearance_level in (Classification.INTERNAL.value, Classification.RESTRICTED.value, Classification.CONFIDENTIAL.value):
            if user.department_id:
                conditions.append(
                    and_(
                        DocumentChunk.classification == Classification.INTERNAL.value,
                        DocumentChunk.department_id == user.department_id,
                    )
                )

        # 3. RESTRICTED documents:
        # Accessible only if user has explicit classification grant or matching department clearance
        if Classification.RESTRICTED.value in granted_classifications:
            conditions.append(DocumentChunk.classification == Classification.RESTRICTED.value)
        elif user.clearance_level in (Classification.RESTRICTED.value, Classification.CONFIDENTIAL.value):
            if user.department_id and "OFFICER" in [r.upper() for r in user.roles]:
                conditions.append(
                    and_(
                        DocumentChunk.classification == Classification.RESTRICTED.value,
                        DocumentChunk.department_id == user.department_id,
                    )
                )

        # 4. CONFIDENTIAL documents:
        # Accessible ONLY through explicit document-level grant in `granted_doc_ids` (already covered above)
        # or explicit CONFIDENTIAL classification grant
        if Classification.CONFIDENTIAL.value in granted_classifications:
            conditions.append(DocumentChunk.classification == Classification.CONFIDENTIAL.value)

        return query.filter(or_(*conditions))

    @classmethod
    def apply_document_acl_filter(
        cls,
        session: Session,
        query: Query,
        user_context: Optional[UserContext] = None,
    ) -> Query:
        """Apply pre-query metadata ACL constraints to a Document query.

        Ensures that low-privilege or cross-tenant users cannot see restricted,
        confidential, or other-department internal documents via relational queries.
        """
        from adam.db.models import Document
        user = user_context or UserContext()

        if user.is_admin():
            return query

        conditions = [Document.classification == Classification.PUBLIC.value]

        now = datetime.now(timezone.utc)
        subjects = [user.user_id] + list(user.roles)

        active_grants = (
            session.query(AccessGrant)
            .filter(
                AccessGrant.subject_id.in_(subjects),
                AccessGrant.action.in_([AccessAction.READ.value, AccessAction.ADMIN.value, "READ", "ADMIN"]),
                or_(AccessGrant.expires_at.is_(None), AccessGrant.expires_at > now),
            )
            .all()
        )

        granted_doc_ids: Set[str] = {g.document_id for g in active_grants if g.document_id}
        granted_classifications: Set[str] = {g.classification for g in active_grants if g.classification}

        if granted_doc_ids:
            conditions.append(Document.id.in_(list(granted_doc_ids)))

        if Classification.INTERNAL.value in granted_classifications:
            conditions.append(Document.classification == Classification.INTERNAL.value)
        elif user.clearance_level in (Classification.INTERNAL.value, Classification.RESTRICTED.value, Classification.CONFIDENTIAL.value):
            if user.department_id:
                conditions.append(
                    and_(
                        Document.classification == Classification.INTERNAL.value,
                        Document.department_id == user.department_id,
                    )
                )

        if Classification.RESTRICTED.value in granted_classifications:
            conditions.append(Document.classification == Classification.RESTRICTED.value)
        elif user.clearance_level in (Classification.RESTRICTED.value, Classification.CONFIDENTIAL.value):
            if user.department_id and "OFFICER" in [r.upper() for r in user.roles]:
                conditions.append(
                    and_(
                        Document.classification == Classification.RESTRICTED.value,
                        Document.department_id == user.department_id,
                    )
                )

        if Classification.CONFIDENTIAL.value in granted_classifications:
            conditions.append(Document.classification == Classification.CONFIDENTIAL.value)

        return query.filter(or_(*conditions))

    @classmethod
    def is_chunk_authorized(
        cls,
        session: Session,
        chunk: DocumentChunk,
        user_context: Optional[UserContext] = None,
    ) -> bool:
        """Verify whether an individual chunk is accessible to the user context."""
        user = user_context or UserContext()
        if user.is_admin():
            return True

        if chunk.classification == Classification.PUBLIC.value:
            return True

        now = datetime.now(timezone.utc)
        subjects = [user.user_id] + list(user.roles)

        # Check explicit AccessGrant
        grant = (
            session.query(AccessGrant)
            .filter(
                AccessGrant.subject_id.in_(subjects),
                or_(
                    AccessGrant.document_id == chunk.document_id,
                    AccessGrant.classification == chunk.classification,
                ),
                AccessGrant.action.in_([AccessAction.READ.value, AccessAction.ADMIN.value, "READ", "ADMIN"]),
                or_(AccessGrant.expires_at.is_(None), AccessGrant.expires_at > now),
            )
            .first()
        )
        if grant:
            return True

        if chunk.classification == Classification.INTERNAL.value:
            if user.clearance_level in (Classification.INTERNAL.value, Classification.RESTRICTED.value, Classification.CONFIDENTIAL.value):
                if user.department_id and user.department_id == chunk.department_id:
                    return True

        if chunk.classification == Classification.RESTRICTED.value:
            if user.clearance_level in (Classification.RESTRICTED.value, Classification.CONFIDENTIAL.value):
                if user.department_id and user.department_id == chunk.department_id and "OFFICER" in [r.upper() for r in user.roles]:
                    return True

        return False

    @classmethod
    def is_document_authorized(
        cls,
        session: Session,
        document_or_id: Any,
        user_context: Optional[UserContext] = None,
    ) -> bool:
        """Verify whether an entire Document record is accessible to the user context."""
        user = user_context or UserContext()
        if user.is_admin():
            return True

        from adam.db.models import Document
        if isinstance(document_or_id, str):
            doc = session.query(Document).filter(Document.id == document_or_id).first()
            if not doc:
                return False
        else:
            doc = document_or_id

        if not doc:
            return False

        if doc.classification == Classification.PUBLIC.value:
            return True

        now = datetime.now(timezone.utc)
        subjects = [user.user_id] + list(user.roles)

        grant = (
            session.query(AccessGrant)
            .filter(
                AccessGrant.subject_id.in_(subjects),
                or_(
                    AccessGrant.document_id == doc.id,
                    AccessGrant.classification == doc.classification,
                ),
                AccessGrant.action.in_([AccessAction.READ.value, AccessAction.ADMIN.value, "READ", "ADMIN"]),
                or_(AccessGrant.expires_at.is_(None), AccessGrant.expires_at > now),
            )
            .first()
        )
        if grant:
            return True

        if doc.classification == Classification.INTERNAL.value:
            if user.clearance_level in (Classification.INTERNAL.value, Classification.RESTRICTED.value, Classification.CONFIDENTIAL.value):
                if user.department_id and user.department_id == doc.department_id:
                    return True

        if doc.classification == Classification.RESTRICTED.value:
            if user.clearance_level in (Classification.RESTRICTED.value, Classification.CONFIDENTIAL.value):
                if user.department_id and user.department_id == doc.department_id and "OFFICER" in [r.upper() for r in user.roles]:
                    return True

        return False

    @classmethod
    def is_source_authorized(
        cls,
        session: Session,
        source_or_id: Any,
        user_context: Optional[UserContext] = None,
    ) -> bool:
        """Verify whether a Source collection is accessible to the user context."""
        user = user_context or UserContext()
        if user.is_admin():
            return True

        from adam.db.models import Source
        if isinstance(source_or_id, str):
            src = session.query(Source).filter(Source.id == source_or_id).first()
            if not src:
                return False
        else:
            src = source_or_id

        if not src:
            return False

        if src.access_classification == Classification.PUBLIC.value:
            return True

        now = datetime.now(timezone.utc)
        subjects = [user.user_id] + list(user.roles)

        grant = (
            session.query(AccessGrant)
            .filter(
                AccessGrant.subject_id.in_(subjects),
                AccessGrant.classification == src.access_classification,
                AccessGrant.action.in_([AccessAction.READ.value, AccessAction.ADMIN.value, "READ", "ADMIN"]),
                or_(AccessGrant.expires_at.is_(None), AccessGrant.expires_at > now),
            )
            .first()
        )
        if grant:
            return True

        if src.access_classification == Classification.INTERNAL.value:
            if user.clearance_level in (Classification.INTERNAL.value, Classification.RESTRICTED.value, Classification.CONFIDENTIAL.value):
                if user.department_id and user.department_id == src.department_id:
                    return True

        if src.access_classification == Classification.RESTRICTED.value:
            if user.clearance_level in (Classification.RESTRICTED.value, Classification.CONFIDENTIAL.value):
                if user.department_id and user.department_id == src.department_id and "OFFICER" in [r.upper() for r in user.roles]:
                    return True

        return False

