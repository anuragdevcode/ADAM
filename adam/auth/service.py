"""Authentication and identity service managing users, organizations, and credentials."""

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session


from adam.auth.security import hash_password, verify_password
from adam.db.models import ApiKey, Membership, Organization, User
from adam.vocabularies import Classification, DepartmentId

logger = logging.getLogger(__name__)


def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    """Retrieve user record by unique ID."""
    return db.query(User).filter(User.id == user_id.strip()).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Retrieve user record by username."""
    return db.query(User).filter(User.username == username.strip().lower()).first()


def create_user(
    db: Session,
    username: str,
    password: str,
    full_name: str = "",
    roles: Optional[List[str]] = None,
    clearance: str = Classification.PUBLIC.value,
    department: str = DepartmentId.UNKNOWN.value,
    email: Optional[str] = None,
    is_superuser: bool = False,
) -> User:
    """Create a new user with hashed password and server-side roles."""
    clean_username = username.strip().lower()
    existing = get_user_by_username(db, clean_username)
    if existing:
        raise ValueError(f"User with username '{clean_username}' already exists.")

    user = User(
        username=clean_username,
        email=email.strip().lower() if email else None,
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        department_id=department or DepartmentId.UNKNOWN.value,
        clearance_level=clearance or Classification.PUBLIC.value,
        roles_json=roles or ["PUBLIC"],
        is_active=True,
        is_superuser=is_superuser,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """Authenticate user with username and password. Returns User if valid, None otherwise."""
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_organization(db: Session, name: str, slug: Optional[str] = None) -> Organization:
    """Create a multi-tenant organization boundary."""
    clean_slug = (slug or name.lower().replace(" ", "-")).strip()
    existing = db.query(Organization).filter(Organization.slug == clean_slug).first()
    if existing:
        return existing

    org = Organization(name=name.strip(), slug=clean_slug)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def add_user_to_org(db: Session, user_id: str, org_id: str, role: str = "OFFICER") -> Membership:
    """Assign user to organization with specific tenant role."""
    mem = db.query(Membership).filter(
        Membership.user_id == user_id,
        Membership.organization_id == org_id,
    ).first()
    if mem:
        mem.role = role
        db.commit()
        db.refresh(mem)
        return mem

    mem = Membership(user_id=user_id, organization_id=org_id, role=role)
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return mem


def create_api_key(
    db: Session,
    user_id: str,
    name: str = "Default API Key",
    roles: Optional[List[str]] = None,
    clearance: str = Classification.PUBLIC.value,
    expires_days: Optional[int] = None,
) -> Tuple[str, ApiKey]:
    """Generate and store machine-to-machine API key. Returns (raw_key, ApiKey)."""
    raw_key = f"adam_sk_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days) if expires_days else None

    api_key_record = ApiKey(
        user_id=user_id,
        key_hash=key_hash,
        name=name,
        roles_json=roles or ["PUBLIC"],
        clearance_level=clearance,
        expires_at=expires_at,
    )
    db.add(api_key_record)
    db.commit()
    db.refresh(api_key_record)
    return raw_key, api_key_record


def verify_api_key(db: Session, raw_key: str) -> Optional[ApiKey]:
    """Verify raw API key string against database hash."""
    if not raw_key.startswith("adam_sk_"):
        return None
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    record = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
    if not record:
        return None
    if record.expires_at and record.expires_at < datetime.now(timezone.utc):
        return None
    return record


def seed_default_admin_if_empty(db: Session) -> Optional[User]:
    """Ensure at least one administrative user exists in development environments."""
    env = os.getenv("ADAM_ENV", "development").lower()
    user_count = db.query(User).count()
    if user_count > 0:
        return None

    if env in ("production", "prod"):
        logger.warning(
            "Production environment has no registered users. Please run `adam user create` to provision an admin."
        )
        return None

    # Dev/test bootstrap admin
    logger.info("Bootstrapping development admin account (admin / admin123)...")
    return create_user(
        db=db,
        username="admin",
        password="dev-admin-password-2026",
        full_name="System Administrator (Dev)",
        roles=["ADMIN", "OFFICER"],
        clearance=Classification.CONFIDENTIAL.value,
        department="GENERAL_ADMIN",
        is_superuser=True,
    )
