"""Session management endpoints for ADAM API (Phase 06)."""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from adam.api.deps import get_db
from adam.db.models import ChatSession
from adam.memory.session import (
    SessionAccessDeniedError,
    SessionExpiredError,
    SessionManager,
)
from adam.memory.retention import ensure_utc

router = APIRouter()


@router.get("/sessions")
def get_sessions(user_id: str, db: Session = Depends(get_db)):
    """List all sessions for a given user, ordered newest-first."""
    from sqlalchemy import func
    from adam.db.models import ChatTurn

    # Compute turn counts in a single SQL query to avoid lazy-loading in threads
    rows = (
        db.query(
            ChatSession,
            func.count(ChatTurn.id).label("turn_count"),
        )
        .outerjoin(ChatTurn, ChatTurn.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id)
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
    db: Session = Depends(get_db),
):
    """Return decrypted conversation turns for an authorized session owner."""
    manager = SessionManager(db)
    try:
        turns = manager.get_turns(session_id, requesting_user_id=x_user_id)
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
    db: Session = Depends(get_db),
):
    """Delete a session and all its encrypted turns. Only the owning user may delete."""
    manager = SessionManager(db)
    try:
        manager.delete_session(session_id, requesting_user_id=x_user_id)
        return {"deleted": True}
    except SessionAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SessionExpiredError:
        # Expired sessions can still be deleted by owner — treat as success
        return {"deleted": True}
