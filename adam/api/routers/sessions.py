"""Session management endpoints for ADAM API (Phase 06)."""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from adam.api.deps import get_db, get_user_context
from adam.db.models import ChatSession
from adam.memory.session import (
    SessionAccessDeniedError,
    SessionExpiredError,
    SessionManager,
)
from adam.memory.retention import ensure_utc
from adam.rag.models import UserContext

router = APIRouter()


@router.get("/sessions")
def get_sessions(
    user_id: Optional[str] = None,
    user_ctx: UserContext = Depends(get_user_context),
    db: Session = Depends(get_db),
):
    """List all sessions for the authenticated user, ordered newest-first."""
    from sqlalchemy import func
    from adam.db.models import ChatTurn

    # Server-side identity enforcement (S6 IDOR prevention)
    target_user_id = user_ctx.user_id
    if user_id:
        if user_ctx.is_admin():
            target_user_id = user_id
        elif user_ctx.user_id != "anonymous" and user_id != user_ctx.user_id:
            raise HTTPException(status_code=403, detail="Forbidden: Cannot list sessions for another user.")
        else:
            target_user_id = user_id

    # Compute turn counts in a single SQL query to avoid lazy-loading in threads
    rows = (
        db.query(
            ChatSession,
            func.count(ChatTurn.id).label("turn_count"),
        )
        .outerjoin(ChatTurn, ChatTurn.session_id == ChatSession.id)
        .filter(ChatSession.user_id == target_user_id)
        .group_by(ChatSession.id)
        .order_by(ChatSession.created_at.desc())
        .all()
    )
    return [
        {
            "session_id": s.id,
            "user_id": s.user_id,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "is_active": True,  # If record exists and not deleted, it is active
            "turn_count": turn_count,
        }
        for s, turn_count in rows
    ]


@router.get("/sessions/{session_id}/history")
def get_session_history(
    session_id: str,
    x_user_id: str = Header(default="anonymous"),
    user_ctx: UserContext = Depends(get_user_context),
    db: Session = Depends(get_db),
):
    """Return decrypted conversation turns for an authorized session owner."""
    effective_user_id = user_ctx.user_id if user_ctx.user_id != "anonymous" else x_user_id
    if user_ctx.is_admin():
        # Admin can view any session
        session_row = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if session_row:
            effective_user_id = session_row.user_id

    manager = SessionManager(db)
    try:
        turns = manager.get_turns(session_id, requesting_user_id=effective_user_id)
        from adam.db.models import AgentExecutionAudit
        audit = (
            db.query(AgentExecutionAudit)
            .filter(AgentExecutionAudit.session_id == session_id)
            .order_by(AgentExecutionAudit.created_at.desc())
            .first()
        )
        model_id = audit.model_id if audit else None

        return {
            "session_id": session_id,
            "model_id": model_id,
            "turns": [
                {
                    "id": t.id,
                    "role": t.role,
                    "content": t.content,
                    "model_id": model_id if t.role == "assistant" else None,
                    "created_at": (
                        t.created_at.isoformat()
                        if hasattr(t.created_at, "isoformat")
                        else str(t.created_at)
                    ),
                    "cited_chunk_ids": t.cited_chunk_ids or [],
                }
                for t in turns
            ],
        }
    except SessionAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SessionExpiredError as exc:
        raise HTTPException(status_code=410, detail=str(exc))


@router.delete("/sessions/{session_id}")
def delete_session_endpoint(
    session_id: str,
    x_user_id: str = Header(default="anonymous"),
    user_ctx: UserContext = Depends(get_user_context),
    db: Session = Depends(get_db),
):
    """Delete a session and all its encrypted turns. Only the owning user or admin may delete."""
    effective_user_id = user_ctx.user_id if user_ctx.user_id != "anonymous" else x_user_id
    if user_ctx.is_admin():
        session_row = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if session_row:
            effective_user_id = session_row.user_id

    manager = SessionManager(db)
    try:
        manager.delete_session(session_id, requesting_user_id=effective_user_id)
        return {"deleted": True}
    except SessionAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SessionExpiredError:
        # Expired sessions can still be deleted by owner — treat as success
        return {"deleted": True}

