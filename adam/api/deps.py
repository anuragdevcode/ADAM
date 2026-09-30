"""FastAPI dependency providers for ADAM API server."""

import os
from typing import Generator, Optional
from fastapi import Header, Request, Depends, HTTPException, status
from sqlalchemy.orm import Session

from adam.auth.policy import get_role_policy
from adam.auth.security import decode_access_token, verify_gateway_signature
from adam.db.session import get_engine, get_session
from adam.rag.models import UserContext
from adam.vocabularies import Classification


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy database session, closing on teardown."""
    session = get_session(get_engine())
    try:
        yield session
    finally:
        session.close()


def get_user_context(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_gateway_signature: Optional[str] = Header(default=None),
    x_gateway_timestamp: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None),
    x_user_id: str = Header(default="anonymous"),
    x_user_role: str = Header(default="PUBLIC"),
    x_clearance_level: str = Header(default="PUBLIC"),
    x_department_id: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> UserContext:
    """Build a verified UserContext from bearer token, signed gateway headers, or API key.

    In accordance with Phase 1 security hardening (S1), unverified headers (X-User-Role,
    X-Clearance-Level) are ignored unless verified via gateway signature or token.
    """
    valid_levels = {c.value for c in Classification}

    # 1. Bearer Token Verification (Signed JWT)
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired bearer token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = payload.get("sub") or payload.get("user_id") or "authenticated_user"
        roles = payload.get("roles") or ["PUBLIC"]
        clearance = payload.get("clearance_level") or Classification.PUBLIC.value
        department = payload.get("department_id")
        policy = get_role_policy(roles)
        return UserContext(
            user_id=str(user_id),
            roles=roles,
            department_id=department,
            clearance_level=clearance if clearance in valid_levels else Classification.PUBLIC.value,
            can_access_web=policy.can_access_web,
            allow_web_research=policy.allow_web_research,
        )

    # 2. Machine-to-Machine API Key Verification
    if x_api_key:
        from adam.auth.service import verify_api_key
        api_record = verify_api_key(db, x_api_key)
        if not api_record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired API key.",
            )
        roles = api_record.roles_json or ["PUBLIC"]
        clearance = api_record.clearance_level or Classification.PUBLIC.value
        policy = get_role_policy(roles)
        return UserContext(
            user_id=api_record.user_id,
            roles=roles,
            department_id=x_department_id,
            clearance_level=clearance if clearance in valid_levels else Classification.PUBLIC.value,
            can_access_web=policy.can_access_web,
            allow_web_research=policy.allow_web_research,
        )

    # 3. Trusted Reverse Proxy Gateway Verification (HMAC-SHA256 signature)
    if x_gateway_signature and x_gateway_timestamp:
        try:
            ts = int(x_gateway_timestamp)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid gateway timestamp.")

        if not verify_gateway_signature(
            signature=x_gateway_signature,
            user_id=x_user_id,
            role=x_user_role,
            clearance=x_clearance_level,
            dept=x_department_id or "",
            timestamp=ts,
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid trusted gateway proxy signature.")

        roles = [x_user_role]
        policy = get_role_policy(roles)
        clearance = x_clearance_level if x_clearance_level in valid_levels else Classification.PUBLIC.value
        return UserContext(
            user_id=x_user_id,
            roles=roles,
            department_id=x_department_id,
            clearance_level=clearance,
            can_access_web=policy.can_access_web,
            allow_web_research=policy.allow_web_research,
        )

    # 4. Backward-compatible dev/testing escape hatch (strictly disabled in production)
    env = os.getenv("ADAM_ENV", "development").lower()
    allow_unverified = os.getenv("ADAM_TRUST_UNVERIFIED_HEADERS", "true").lower() in ("true", "1")
    if allow_unverified and env not in ("production", "prod"):
        clearance = x_clearance_level if x_clearance_level in valid_levels else Classification.PUBLIC.value
        roles = [x_user_role]
        policy = get_role_policy(roles)
        return UserContext(
            user_id=x_user_id,
            roles=roles,
            department_id=x_department_id,
            clearance_level=clearance,
            can_access_web=policy.can_access_web,
            allow_web_research=policy.allow_web_research,
        )


    # 5. Unauthenticated / Forged Headers Fallback: default-deny roles & clearance
    # Any attacker sending forged headers like `X-User-Role: ADMIN` without token/signature
    # is stripped of privileges and given default PUBLIC permissions.
    policy = get_role_policy(["PUBLIC"])
    return UserContext(
        user_id=x_user_id if x_user_id != "anonymous" else "anonymous",
        roles=["PUBLIC"],
        department_id=x_department_id,
        clearance_level=Classification.PUBLIC.value,
        can_access_web=policy.can_access_web,
        allow_web_research=policy.allow_web_research,
    )


def get_trace_id(request: Request) -> str:
    """Retrieve or generate trace ID for the active request."""
    return getattr(request.state, "trace_id", None) or request.headers.get("X-Trace-Id") or "trace_default"


def require_authenticated_user(user_ctx: UserContext = Depends(get_user_context)) -> UserContext:
    """Dependency requiring caller to be authenticated (non-anonymous)."""
    if user_ctx.user_id == "anonymous":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_ctx


def require_roles(*allowed_roles: str):
    """Dependency enforcing role-based access control."""
    def _role_checker(user_ctx: UserContext = Depends(get_user_context)) -> UserContext:
        user_roles = [r.upper() for r in (user_ctx.roles or [])]
        allowed = [r.upper() for r in allowed_roles]
        if not any(r in allowed for r in user_roles):
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Requires one of roles: {list(allowed_roles)}",
            )
        return user_ctx
    return _role_checker
