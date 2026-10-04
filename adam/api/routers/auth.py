from datetime import datetime, timedelta, timezone
import os
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from adam.api.deps import get_db, get_user_context
from adam.auth.security import create_access_token
from adam.auth.service import authenticate_user, create_user, get_user_by_username
from adam.db.models import AuditEvent, User
from adam.rag.models import UserContext
from adam.vocabularies import Classification, DepartmentId

router = APIRouter(prefix="/auth", tags=["auth"])

_FAILED_LOGIN_ATTEMPTS: Dict[str, List[float]] = {}
_MAX_FAILED_LOGINS = 5
_LOCKOUT_WINDOW_SEC = 300.0  # 5 minutes


def get_client_ip(request: Request) -> str:
    """Extract client IP respecting X-Forwarded-For and X-Real-IP reverse proxy headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def is_registration_allowed() -> bool:
    """Registration policy: default false in production, true in development/test."""
    env_val = os.getenv("ADAM_ALLOW_REGISTRATION")
    if env_val is not None:
        return env_val.strip().lower() in ("true", "1", "yes")
    is_prod = os.getenv("ADAM_ENV", "").strip().lower() == "production"
    return not is_prod


class LoginRequest(BaseModel):
    username: str = Field(..., description="User account username")
    password: str = Field(..., description="Account password")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, description="Unique username")
    password: str = Field(..., min_length=8, description="Account password (min 8 chars)")
    full_name: str = Field(default="", max_length=255)
    email: Optional[str] = Field(default=None)
    department_id: str = Field(default=DepartmentId.UNKNOWN.value)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400
    user: Dict[str, Any]


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Authenticate with username and password, returning signed JWT bearer token."""
    client_ip = get_client_ip(request)
    username_norm = req.username.strip().lower()
    window_start = datetime.now(timezone.utc) - timedelta(seconds=_LOCKOUT_WINDOW_SEC)

    # Database-persisted failed attempt rate-limiting surviving worker reboots
    failed_attempts_count = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.entity_type == "AUTH",
            AuditEvent.action == "LOGIN_FAILED",
            or_(
                AuditEvent.actor == username_norm,
                AuditEvent.entity_id == client_ip,
            ),
            AuditEvent.timestamp >= window_start,
        )
        .count()
    )

    if failed_attempts_count >= _MAX_FAILED_LOGINS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Account temporarily locked. Please try again later.",
        )

    throttle_key = f"{client_ip}:{username_norm}"
    user = authenticate_user(db, req.username, req.password)
    if not user:
        _FAILED_LOGIN_ATTEMPTS.setdefault(throttle_key, []).append(time.time())
        # Record tamper-evident failed attempt in persistent database audit log
        failed_event = AuditEvent(
            entity_type="AUTH",
            entity_id=client_ip,
            action="LOGIN_FAILED",
            actor=username_norm,
            details_json={
                "ip": client_ip,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.add(failed_event)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _FAILED_LOGIN_ATTEMPTS.pop(throttle_key, None)

    # Issue cryptographically signed token
    token = create_access_token({
        "sub": user.id,
        "username": user.username,
        "roles": user.roles,
        "clearance_level": user.clearance_level,
        "department_id": user.department_id,
    })

    # Record tamper-evident audit event
    audit = AuditEvent(
        entity_type="USER",
        entity_id=user.id,
        action="LOGIN",
        actor=user.username,
        details_json={
            "roles": user.roles,
            "clearance": user.clearance_level,
            "ip": client_ip,
        },
    )
    db.add(audit)
    db.commit()

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 86400,
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "roles": user.roles,
            "clearance_level": user.clearance_level,
            "department_id": user.department_id,
        },
    }


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user account."""
    if not is_registration_allowed():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User registration is disabled by administrator.",
        )

    # Password complexity policy: >= 8 characters, at least one letter, at least one digit
    pwd = req.password
    if len(pwd) < 8 or not any(c.isalpha() for c in pwd) or not any(c.isdigit() for c in pwd):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long and contain both letters and digits.",
        )

    existing = get_user_by_username(db, req.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{req.username}' is already taken.",
        )

    try:
        user = create_user(
            db,
            username=req.username,
            password=req.password,
            full_name=req.full_name,
            email=req.email,
            department=req.department_id,
            roles=["PUBLIC"],
            clearance=Classification.PUBLIC.value,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    token = create_access_token({
        "sub": user.id,
        "username": user.username,
        "roles": user.roles,
        "clearance_level": user.clearance_level,
        "department_id": user.department_id,
    })

    audit = AuditEvent(
        entity_type="USER",
        entity_id=user.id,
        action="REGISTER",
        actor=user.username,
        details_json={"roles": user.roles, "clearance": user.clearance_level},
    )
    db.add(audit)
    db.commit()

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 86400,
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "roles": user.roles,
            "clearance_level": user.clearance_level,
            "department_id": user.department_id,
        },
    }


@router.get("/me")
def get_current_user(user_ctx: UserContext = Depends(get_user_context)):
    """Return currently authenticated actor context."""
    if user_ctx.user_id == "anonymous":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "user_id": user_ctx.user_id,
        "roles": user_ctx.roles,
        "department_id": user_ctx.department_id,
        "clearance_level": user_ctx.clearance_level,
        "can_access_web": user_ctx.can_access_web,
        "allow_web_research": user_ctx.allow_web_research,
        "is_admin": user_ctx.is_admin(),
    }
