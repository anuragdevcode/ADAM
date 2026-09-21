"""Idempotency management service for write endpoints."""

import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session
from adam.db.models import IdempotencyRecord


class IdempotencyManager:
    """Provides safe deduplication of requests with identical Idempotency-Key headers."""

    @staticmethod
    def compute_payload_hash(payload: Any) -> str:
        """Deterministically hash request payload."""
        if isinstance(payload, bytes):
            return hashlib.sha256(payload).hexdigest()
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def get_cached_response(
        cls,
        db: Session,
        key: str,
        user_id: str,
        endpoint: str,
        payload: Any,
    ) -> Optional[Tuple[int, Dict[str, Any]]]:
        """Check if an unexpired identical write was previously recorded for this key."""
        req_hash = cls.compute_payload_hash(payload)
        now = datetime.now(timezone.utc)

        record = (
            db.query(IdempotencyRecord)
            .filter(
                IdempotencyRecord.key == key,
                IdempotencyRecord.user_id == user_id,
                IdempotencyRecord.endpoint == endpoint,
            )
            .first()
        )

        if not record:
            return None

        # Check expiration
        exp = record.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now:
            db.delete(record)
            db.commit()
            return None

        # Verify payload consistency (prevent silent corruption on key reuse)
        if record.request_hash and record.request_hash != req_hash:
            raise HTTPException(
                status_code=409,
                detail="Idempotency key reuse conflict: request payload does not match the original request.",
            )

        # Return cached status code and json payload
        return record.response_status, record.response_json

    @classmethod
    def save_response(
        cls,
        db: Session,
        key: str,
        user_id: str,
        endpoint: str,
        payload: Any,
        status_code: int,
        response_json: Dict[str, Any],
        ttl_seconds: int = 86400,
    ) -> IdempotencyRecord:
        """Persist a response for this idempotency key."""
        req_hash = cls.compute_payload_hash(payload)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)

        existing = db.query(IdempotencyRecord).filter(IdempotencyRecord.key == key).first()
        if existing:
            existing.user_id = user_id
            existing.endpoint = endpoint
            existing.request_hash = req_hash
            existing.response_status = status_code
            existing.response_json = response_json
            existing.expires_at = expires_at
            record = existing
        else:
            record = IdempotencyRecord(
                key=key,
                user_id=user_id,
                endpoint=endpoint,
                request_hash=req_hash,
                response_status=status_code,
                response_json=response_json,
                created_at=now,
                expires_at=expires_at,
            )
            db.add(record)

        db.commit()
        return record
