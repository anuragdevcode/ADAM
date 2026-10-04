"""Session and conversational turn lifecycle manager.

Enforces:
- 'No cross-user memory.'
- 'A new session cannot retrieve a prior user’s turns.'
- Field-level encryption at rest for all turn content.
- Audit logging for access and deletion without content residuals.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from adam.db.models import AuditEvent, ChatSession, ChatTurn
from adam.memory.crypto import AuthenticatedCipher, get_cipher
from adam.memory.retention import (
    RETENTION_TAG_CLASSIFIED_PII,
    RETENTION_TAG_STANDARD,
    calculate_session_expiry,
    ensure_utc,
)
from adam.vocabularies import Classification


class SessionAccessDeniedError(PermissionError):
    """Raised when a user attempts to access a session or turns belonging to another user."""
    pass


class SessionExpiredError(ValueError):
    """Raised when an operation is attempted on an expired session."""
    pass


@dataclass
class DecryptedTurn:
    """Decrypted representation of a conversation turn for authorized in-memory processing."""
    id: str
    session_id: str
    role: str
    content: str
    cited_chunk_ids: List[str]
    retention_tag: str
    created_at: datetime


class SessionManager:
    """Manages secure lifecycle of chat sessions and encrypted conversational turns."""

    def __init__(self, db: Session, cipher: Optional[AuthenticatedCipher] = None):
        self.db = db
        self.cipher = cipher or get_cipher()

    def create_session(
        self,
        user_id: str,
        classification_ceiling: str = Classification.PUBLIC.value,
        ttl_seconds: Optional[int] = None,
        is_classified_or_pii: bool = False,
    ) -> ChatSession:
        """Create a new bounded chat session for a user."""
        if not user_id or not user_id.strip():
            raise ValueError("user_id is required to create a session")

        retention_tag = RETENTION_TAG_CLASSIFIED_PII if is_classified_or_pii else RETENTION_TAG_STANDARD
        now = datetime.now(timezone.utc)
        expires_at = calculate_session_expiry(ttl_seconds, retention_tag=retention_tag, start_time=now)

        session = ChatSession(
            user_id=user_id.strip(),
            classification_ceiling=classification_ceiling,
            created_at=now,
            expires_at=expires_at,
        )
        self.db.add(session)
        self.db.flush()

        self.db.commit()
        return session

    def get_session(self, session_id: str, requesting_user_id: str) -> ChatSession:
        """Retrieve a session with strict user-boundary enforcement.

        Raises:
            KeyError: if session does not exist.
            SessionAccessDeniedError: if session belongs to another user (Acceptance Criterion 1).
            SessionExpiredError: if session has expired.
        """
        session = self.db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            raise KeyError(f"ChatSession '{session_id}' not found")

        # Strict cross-user isolation: Acceptance Criterion 1
        if session.user_id != requesting_user_id:
            raise SessionAccessDeniedError(
                f"Access denied: Session '{session_id}' does not belong to user '{requesting_user_id}'"
            )

        now = datetime.now(timezone.utc)
        if ensure_utc(session.expires_at) <= now:
            raise SessionExpiredError(f"ChatSession '{session_id}' expired at {session.expires_at.isoformat()}")

        return session

    def add_turn(
        self,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        cited_chunk_ids: Optional[List[str]] = None,
        is_classified_or_pii: bool = False,
    ) -> ChatTurn:
        """Add an encrypted conversational turn to an active session."""
        session = self.get_session(session_id, requesting_user_id=user_id)

        # Determine retention tag
        retention_tag = RETENTION_TAG_CLASSIFIED_PII if is_classified_or_pii else RETENTION_TAG_STANDARD

        # If turn is classified/PII, adjust session expiry if it currently extends beyond short retention
        now = datetime.now(timezone.utc)
        if is_classified_or_pii:
            capped_expiry = calculate_session_expiry(retention_tag=RETENTION_TAG_CLASSIFIED_PII, start_time=now)
            if session.expires_at > capped_expiry:
                session.expires_at = capped_expiry

        # Encrypt content at rest
        ciphertext = self.cipher.encrypt(content)

        turn = ChatTurn(
            session_id=session.id,
            role=role,
            content_ciphertext=ciphertext,
            cited_chunk_ids=cited_chunk_ids or [],
            retention_tag=retention_tag,
            created_at=now,
        )
        self.db.add(turn)
        self.db.commit()
        return turn

    def get_turns(self, session_id: str, requesting_user_id: str) -> List[DecryptedTurn]:
        """Retrieve and decrypt all turns for an authorized session."""
        session = self.get_session(session_id, requesting_user_id=requesting_user_id)

        turns = (
            self.db.query(ChatTurn)
            .filter(ChatTurn.session_id == session.id)
            .order_by(ChatTurn.created_at.asc())
            .all()
        )

        decrypted_turns: List[DecryptedTurn] = []
        for t in turns:
            plaintext = self.cipher.decrypt(t.content_ciphertext)
            decrypted_turns.append(
                DecryptedTurn(
                    id=t.id,
                    session_id=t.session_id,
                    role=t.role,
                    content=plaintext,
                    cited_chunk_ids=t.cited_chunk_ids or [],
                    retention_tag=t.retention_tag,
                    created_at=t.created_at,
                )
            )

        # Audit access without logging turn text
        audit = AuditEvent(
            entity_type="CHAT_SESSION",
            entity_id=session_id,
            action="ACCESS_TURNS",
            actor=requesting_user_id,
            details_json={"turns_read": len(decrypted_turns)},
            timestamp=datetime.now(timezone.utc),
        )
        self.db.add(audit)
        self.db.commit()

        return decrypted_turns

    def delete_session(self, session_id: str, requesting_user_id: str, actor: Optional[str] = None) -> None:
        """Explicitly delete a session and all turns/summaries.

        Enforces:
            'Expiry/deletion removes encrypted content and makes it unavailable
             to retrieval; audit event remains without content.'
        """
        session = self.get_session(session_id, requesting_user_id=requesting_user_id)
        now = datetime.now(timezone.utc)
        turn_count = len(session.turns) if session.turns else 0

        self.db.delete(session)

        # Audit deletion leaving zero content
        audit = AuditEvent(
            entity_type="CHAT_SESSION",
            entity_id=session_id,
            action="DELETE",
            actor=actor or requesting_user_id,
            details_json={
                "user_id": requesting_user_id,
                "turns_deleted": turn_count,
                "deleted_at": now.isoformat(),
            },
            timestamp=now,
        )
        self.db.add(audit)
        self.db.commit()
