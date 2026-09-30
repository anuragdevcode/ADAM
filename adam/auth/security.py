"""Cryptographic security utilities for authentication, password hashing, and signed tokens."""

import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import bcrypt
import jwt

from adam.config import SIGNING_SECRET

ALGORITHM = "HS256"
DEFAULT_ACCESS_TOKEN_EXPIRE_HOURS = 24


def hash_password(password: str) -> str:
    """Hash plaintext password with bcrypt."""
    if not isinstance(password, str):
        raise TypeError("Password must be a string")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("ascii")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against bcrypt hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("ascii"))
    except Exception:
        return False


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generate cryptographically signed JWT access token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(hours=DEFAULT_ACCESS_TOKEN_EXPIRE_HOURS)

    to_encode.update({
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
    })
    return jwt.encode(to_encode, SIGNING_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and cryptographically verify JWT access token. Returns claims dict or None."""
    try:
        payload = jwt.decode(token, SIGNING_SECRET, algorithms=[ALGORITHM])
        return payload
    except (jwt.PyJWTError, Exception):
        return None


def sign_gateway_payload(
    user_id: str,
    role: str,
    clearance: str,
    dept: str = "",
    timestamp: Optional[int] = None,
) -> Tuple[str, int]:
    """Generate HMAC-SHA256 signature for trusted proxy gateway headers."""
    ts = timestamp if timestamp is not None else int(time.time())
    message = f"{user_id}:{role}:{clearance}:{dept}:{ts}".encode("utf-8")
    sig = hmac.new(SIGNING_SECRET.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return sig, ts


def verify_gateway_signature(
    signature: str,
    user_id: str,
    role: str,
    clearance: str,
    dept: str = "",
    timestamp: int = 0,
    max_age_seconds: int = 300,
) -> bool:
    """Verify HMAC signature from trusted gateway and check replay prevention timestamp."""
    if not signature or not timestamp:
        return False
    now = int(time.time())
    if abs(now - timestamp) > max_age_seconds:
        return False

    expected_sig, _ = sign_gateway_payload(user_id, role, clearance, dept, timestamp)
    return hmac.compare_digest(signature, expected_sig)
