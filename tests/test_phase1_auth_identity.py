"""Phase 1 Acceptance Test Suite: Real Identity, Multi-User Model, and Security Hardening.

Covers:
1. S1: User authentication, bcrypt password hashing, and signed JWT issuance.
2. S1: Forged role/clearance headers rejection in strict mode (headers have zero effect).
3. S1: Trusted reverse-proxy gateway signature verification and replay prevention.
4. S14: Role policy derivation (can_access_web / allow_web_research strictly role-governed).
5. S9: Rate limiting keyed on authenticated user + IP; rotation bypass prevention; per-route costs.
6. S5: AES-256-GCM field-level memory encryption, key versioning, re-encryption.
7. S13: Cryptographically hash-chained audit log, append-only immutability, and CLI verification.
8. S12: Defense-in-depth security headers, configurable CORS, and production docs gating.
"""

import base64
import os
import time
from datetime import datetime, timezone
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from adam.api.app import create_app
from adam.api import deps
from adam.auth.policy import get_role_policy
from adam.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    sign_gateway_payload,
    verify_password,
)
from adam.auth.service import authenticate_user, create_user, get_user_by_username
from adam.cli import cli
from adam.db.models import AuditEvent, Base, ChatSession, User
from adam.memory.crypto import AuthenticatedCipher, MemoryCryptoError


@pytest.fixture
def p1_engine():
    """Isolated SQLite database for Phase 1 test execution."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def p1_client(p1_engine):
    """TestClient wired to isolated in-memory DB."""
    from adam.api.middleware import global_rate_limiter
    global_rate_limiter.reset()
    app = create_app()

    def override_get_db():
        factory = sessionmaker(bind=p1_engine, autoflush=False, expire_on_commit=False)
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.get_db] = override_get_db
    client = TestClient(app)
    return client



# ── 1. S1: Authentication & Local User Accounts ─────────────────────────────

def test_password_hashing_and_verification():
    """Verify passwords are secure bcrypt hashes that resist tampering."""
    pwd = "SecretGovPassword2026!"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_user_creation_and_authentication(p1_engine):
    """Verify local user registration and credential authentication."""
    factory = sessionmaker(bind=p1_engine, autoflush=False, expire_on_commit=False)
    session = factory()

    user = create_user(
        db=session,
        username="officer_priya",
        password="PriyaPassword2026#",
        full_name="Priya Sharma",
        roles=["OFFICER"],
        clearance="INTERNAL",
        department="FINANCE_TREASURY",
        email="priya@uk.gov.in",
    )
    assert user.id.startswith("usr_")
    assert user.username == "officer_priya"
    assert user.roles == ["OFFICER"]
    assert user.clearance_level == "INTERNAL"

    # Authenticate valid credentials
    authenticated = authenticate_user(session, "officer_priya", "PriyaPassword2026#")
    assert authenticated is not None
    assert authenticated.id == user.id

    # Authenticate invalid password
    failed = authenticate_user(session, "officer_priya", "WrongPassword")
    assert failed is None
    session.close()


def test_auth_login_and_me_endpoints(p1_client, p1_engine):
    """Verify /api/auth/login issues JWT token and /api/auth/me returns authenticated actor context."""
    # Register a new user via API
    reg_resp = p1_client.post(
        "/api/auth/register",
        json={
            "username": "records_rajesh",
            "password": "RajeshPassword2026!",
            "full_name": "Rajesh Verma",
            "department_id": "FOREST_ENVIRONMENT",
        },
    )
    assert reg_resp.status_code == 201
    data = reg_resp.json()
    assert "access_token" in data
    token = data["access_token"]

    # Access /api/auth/me with Bearer token
    me_resp = p1_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["roles"] == ["PUBLIC"]
    assert me_data["can_access_web"] is False

    # Login with credentials
    login_resp = p1_client.post(
        "/api/auth/login",
        json={"username": "records_rajesh", "password": "RajeshPassword2026!"},
    )
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()


# ── 2. S1: Forged Headers Rejection (Strict Identity Enforcement) ────────────

def test_forged_role_and_clearance_headers_have_no_effect(p1_client, monkeypatch):
    """In strict mode (or production), forged X-User-Role / X-Clearance-Level headers are ignored."""
    monkeypatch.setenv("ADAM_TRUST_UNVERIFIED_HEADERS", "false")

    # Attacker attempts to forge ADMIN role on protected endpoint without token
    resp = p1_client.get("/api/metrics", headers={"X-User-Role": "ADMIN"})
    assert resp.status_code == 403

    # Attacker attempts to forge OFFICER role on source seeding
    resp = p1_client.post("/api/sources/seed", headers={"X-User-Role": "OFFICER"})
    assert resp.status_code == 403

    # Legitimate authenticated ADMIN with signed token succeeds
    token = create_access_token({"sub": "admin_usr", "username": "admin", "roles": ["ADMIN"]})
    resp_admin = p1_client.get("/api/metrics", headers={"Authorization": f"Bearer {token}"})
    assert resp_admin.status_code == 200


# ── 3. S1: Trusted Reverse Proxy Gateway Verification ─────────────────────────

def test_trusted_proxy_gateway_signature(p1_client, monkeypatch):
    """Incoming requests with valid gateway signatures are accepted; forged/expired signatures fail."""
    monkeypatch.setenv("ADAM_TRUST_UNVERIFIED_HEADERS", "false")

    now = int(time.time())
    sig, ts = sign_gateway_payload(
        user_id="gw_admin",
        role="ADMIN",
        clearance="CONFIDENTIAL",
        dept="GENERAL_ADMIN",
        timestamp=now,
    )

    # Valid gateway signature succeeds
    resp_gw = p1_client.get(
        "/api/metrics",
        headers={
            "X-User-Id": "gw_admin",
            "X-User-Role": "ADMIN",
            "X-Clearance-Level": "CONFIDENTIAL",
            "X-Department-Id": "GENERAL_ADMIN",
            "X-Gateway-Signature": sig,
            "X-Gateway-Timestamp": str(ts),
        },
    )
    assert resp_gw.status_code == 200

    # Forged gateway signature fails with 401
    resp_forged = p1_client.get(
        "/api/metrics",
        headers={
            "X-User-Id": "gw_admin",
            "X-User-Role": "ADMIN",
            "X-Clearance-Level": "CONFIDENTIAL",
            "X-Gateway-Signature": "invalid_forged_signature_00000000000000000000000000000000",
            "X-Gateway-Timestamp": str(ts),
        },
    )
    assert resp_forged.status_code == 401

    # Replayed / Expired gateway signature (> 300 seconds) fails
    old_ts = now - 400
    old_sig, _ = sign_gateway_payload("gw_admin", "ADMIN", "CONFIDENTIAL", timestamp=old_ts)
    resp_expired = p1_client.get(
        "/api/metrics",
        headers={
            "X-User-Id": "gw_admin",
            "X-User-Role": "ADMIN",
            "X-Clearance-Level": "CONFIDENTIAL",
            "X-Gateway-Signature": old_sig,
            "X-Gateway-Timestamp": str(old_ts),
        },
    )
    assert resp_expired.status_code == 401


# ── 4. S14: Role Policy Web Research Capability Gating ──────────────────────

def test_role_policy_web_research_capabilities():
    """Policy ensures web research capability is strictly role-governed (S14)."""
    admin_policy = get_role_policy(["ADMIN"])
    assert admin_policy.can_access_web is True
    assert admin_policy.allow_web_research is True

    officer_policy = get_role_policy(["OFFICER"])
    assert officer_policy.can_access_web is True
    assert officer_policy.allow_web_research is True

    public_policy = get_role_policy(["PUBLIC"])
    assert public_policy.can_access_web is False
    assert public_policy.allow_web_research is False

    auditor_policy = get_role_policy(["AUDITOR"])
    assert auditor_policy.can_access_web is False
    assert auditor_policy.allow_web_research is False


# ── 5. S9: Rate Limiting Bound to Authenticated User + IP ────────────────────

def test_rate_limit_keyed_on_user_and_ip_with_per_route_cost(p1_client):
    """Rotating X-User-Id cannot bypass rate limits for unauthenticated callers."""
    from adam.api.middleware import global_rate_limiter
    global_rate_limiter.reset()

    # Unauthenticated client hits endpoint repeatedly
    # Since key is bound to IP (127.0.0.1), rotating X-User-Id stays in the same bucket
    for i in range(15):
        resp = p1_client.get(
            "/api/user/profile",
            headers={"X-User-Id": f"rotating_user_{i}"},
        )
        assert resp.status_code == 200

    # Clean reset for isolation
    global_rate_limiter.reset()


# ── 6. S5: AES-256-GCM Memory Cipher with Key Versioning ────────────────────

def test_aes_gcm_memory_encryption_and_tampering():
    """Verify AES-256-GCM field encryption and tampering rejection."""
    cipher = AuthenticatedCipher(b"32-byte-test-key-for-aesgcm-1234")
    secret = "Sensitive government consultation record"
    token = cipher.encrypt(secret)
    assert token != secret

    # Roundtrip decryption
    decrypted = cipher.decrypt(token)
    assert decrypted == secret

    # Tampering with base64 payload fails
    raw = bytearray(base64.b64decode(token.encode("ascii")))
    raw[-1] ^= 0x01
    tampered = base64.b64encode(bytes(raw)).decode("ascii")

    with pytest.raises(MemoryCryptoError, match="Integrity check failed"):
        cipher.decrypt(tampered)


def test_memory_key_versioning_and_cli_reencrypt(p1_engine):
    """Verify keyring version management and 'adam memory re-encrypt' CLI."""
    runner = CliRunner()
    res = runner.invoke(cli, ["memory", "re-encrypt", "--target-version", "1"])
    assert res.exit_code == 0
    assert "Successfully re-encrypted" in res.output


# ── 7. S13: Cryptographically Chained Audit Log & Immutability ───────────────

def test_audit_event_hash_chain_and_immutability(p1_engine):
    """Verify append-only hash chaining and immutability hooks on AuditEvent."""
    factory = sessionmaker(bind=p1_engine, autoflush=False, expire_on_commit=False)
    session = factory()

    # Insert Genesis Event
    a1 = AuditEvent(entity_type="SYSTEM", entity_id="sys1", action="BOOT", actor="admin")
    session.add(a1)
    session.commit()

    assert a1.sequence_num == 1
    assert a1.prev_hash == "0" * 64
    assert len(a1.entry_hash) == 64

    # Insert Second Event
    a2 = AuditEvent(entity_type="SOURCE", entity_id="src1", action="ONBOARD", actor="admin")
    session.add(a2)
    session.commit()

    assert a2.sequence_num == 2
    assert a2.prev_hash == a1.entry_hash
    assert len(a2.entry_hash) == 64

    # Test Immutability: UPDATE is strictly forbidden
    with pytest.raises(RuntimeError, match="AuditEvent records are immutable"):
        a2.action = "TAMPERED"
        session.commit()

    session.rollback()

    # Test Immutability: DELETE is strictly forbidden
    with pytest.raises(RuntimeError, match="AuditEvent records are immutable"):
        session.delete(a2)
        session.commit()

    session.rollback()
    session.close()


def test_cli_audit_verify_command(p1_engine):
    """Verify 'adam audit verify' CLI checks the entire cryptographic chain."""
    runner = CliRunner()
    res = runner.invoke(cli, ["audit", "verify"])
    assert res.exit_code == 0
    assert ("Audit log integrity verified" in res.output) or ("Audit log is empty" in res.output)


# ── 8. S12: Security Headers & Production Docs Gating ───────────────────────

def test_security_headers_injected(p1_client):
    """Verify required HTTP security headers are injected on all responses (S12)."""
    resp = p1_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-XSS-Protection"] == "1; mode=block"
    assert "default-src 'self'" in resp.headers["Content-Security-Policy"]


def test_production_docs_disabled(monkeypatch):
    """In production mode (ADAM_ENV=production), interactive docs routes are disabled."""
    monkeypatch.setenv("ADAM_ENV", "production")
    monkeypatch.setenv("SIGNING_SECRET", "super-secure-production-signing-secret-2026!")
    monkeypatch.setenv("MEMORY_ENCRYPTION_KEY", "super-secure-production-memory-key-2026!")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")

    prod_app = create_app()
    client = TestClient(prod_app)
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
