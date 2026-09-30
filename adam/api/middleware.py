"""ADAM Gateway Middlewares: Trace ID injection, Rate Limiting, and Structured Error Formatting."""

import os
import time
import uuid
from collections import defaultdict
from typing import Dict, Optional, Tuple

from fastapi import HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Ensure every request has a unique trace_id propagated through request.state and response headers."""

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
        request.state.trace_id = trace_id

        response: Response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response


class InMemoryTokenBucketRateLimiter:
    """Sliding-window token bucket rate limiter tracking requests per client key with bounded eviction."""

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_capacity: int = 15,
        max_keys: int = 10000,
        ttl_seconds: float = 600.0,
    ):
        self.rate = requests_per_minute  # tokens per minute
        self.capacity = burst_capacity + requests_per_minute
        self.tokens: Dict[str, float] = defaultdict(lambda: float(self.capacity))
        self.last_updated: Dict[str, float] = defaultdict(time.time)
        self.fill_rate = requests_per_minute / 60.0  # tokens per second
        self.max_keys = max_keys
        self.ttl_seconds = ttl_seconds

    def _prune_if_needed(self, now: float):
        """Evict stale rate limit keys to bound in-memory resource consumption."""
        if len(self.tokens) > self.max_keys:
            stale_keys = [
                k for k, last in self.last_updated.items()
                if now - last > self.ttl_seconds
            ]
            for k in stale_keys:
                self.tokens.pop(k, None)
                self.last_updated.pop(k, None)

    def is_allowed(self, key: str, cost: float = 1.0) -> Tuple[bool, int]:
        """Check if request is permitted under token bucket algorithm.

        Returns (allowed: bool, retry_after_seconds: int).
        """
        now = time.time()
        self._prune_if_needed(now)

        last = self.last_updated[key]
        elapsed = max(0.0, now - last)

        # Refill tokens based on elapsed time
        current_tokens = min(self.capacity, self.tokens[key] + elapsed * self.fill_rate)
        self.tokens[key] = current_tokens
        self.last_updated[key] = now

        if current_tokens >= cost:
            self.tokens[key] -= cost
            return True, 0

        # Calculate wait time needed for at least 1 token
        needed = cost - current_tokens
        retry_after = max(1, int(needed / self.fill_rate))
        return False, retry_after

    def reset(self, key: Optional[str] = None):
        """Reset rate limiter state (useful for tests)."""
        if key:
            self.tokens.pop(key, None)
            self.last_updated.pop(key, None)
        else:
            self.tokens.clear()
            self.last_updated.clear()


# Global default rate limiter (60 req/min, burst +10)
global_rate_limiter = InMemoryTokenBucketRateLimiter(requests_per_minute=60, burst_capacity=10)

# Per-route resource costs (S9)
ROUTE_COSTS = {
    "/api/chat": 5.0,
    "/v1/chat": 5.0,
    "/api/documents/upload": 10.0,
    "/v1/documents": 10.0,
    "/api/voice": 3.0,
}


def extract_client_rate_limit_key(request: Request) -> str:
    """Derive rate limit key based on verified user identity + client IP to prevent bypass (S9)."""
    client_ip = request.client.host if request.client else "127.0.0.1"

    # 1. Check Bearer token
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        token = auth[7:].strip()
        try:
            from adam.auth.security import decode_access_token
            payload = decode_access_token(token)
            if payload and payload.get("sub"):
                return f"usr:{payload['sub']}:{client_ip}"
        except Exception:
            pass

    # 2. Check Gateway signature
    gw_sig = request.headers.get("X-Gateway-Signature")
    gw_ts = request.headers.get("X-Gateway-Timestamp")
    user_id = request.headers.get("X-User-Id")
    if gw_sig and gw_ts and user_id:
        try:
            from adam.auth.security import verify_gateway_signature
            if verify_gateway_signature(
                signature=gw_sig,
                user_id=user_id,
                role=request.headers.get("X-User-Role", "PUBLIC"),
                clearance=request.headers.get("X-Clearance-Level", "PUBLIC"),
                dept=request.headers.get("X-Department-Id", ""),
                timestamp=int(gw_ts),
            ):
                return f"usr:{user_id}:{client_ip}"
        except Exception:
            pass

    # 3. Non-production / dev / test isolation
    env = os.getenv("ADAM_ENV", "development").lower()
    if env not in ("production", "prod"):
        if user_id and user_id != "anonymous":
            return f"usr:{user_id}:{client_ip}"
        role = request.headers.get("X-User-Role")
        if role and role != "PUBLIC":
            return f"role:{role}:{client_ip}"
        tenant_id = request.headers.get("X-Tenant-Id")
        if tenant_id:
            return f"tenant:{tenant_id}:{client_ip}"


    # 4. In production: unauthenticated requests are strictly bound to client IP (prevents bypass via rotating X-User-Id)
    return f"ip:{client_ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforce per-user/tenant rate limits with per-route costs and return HTTP 429 when exceeded."""

    def __init__(self, app, limiter: Optional[InMemoryTokenBucketRateLimiter] = None, enabled: Optional[bool] = None):
        super().__init__(app)
        self.limiter = limiter or global_rate_limiter
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1")

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)


        # Exclude internal health checks, docs, auth endpoints, and favicon
        path = request.url.path
        if path in ("/docs", "/openapi.json", "/redoc", "/favicon.ico", "/api/health") or path.startswith("/api/auth"):
            return await call_next(request)


        client_key = extract_client_rate_limit_key(request)
        cost = ROUTE_COSTS.get(path, 1.0)

        allowed, retry_after = self.limiter.is_allowed(client_key, cost=cost)
        if not allowed:
            trace_id = getattr(request.state, "trace_id", uuid.uuid4().hex)
            payload = {
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Rate limit exceeded. Please retry after {retry_after} seconds.",
                    "trace_id": trace_id,
                    "details": {"retry_after": retry_after},
                }
            }
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content=payload,
                headers={"Retry-After": str(retry_after), "X-Trace-Id": trace_id},
            )

        return await call_next(request)


def format_error_response(status_code: int, code: str, message: str, trace_id: str, details: Optional[Dict] = None) -> JSONResponse:
    """Generate structured JSON error adhering to core specification."""
    payload = {
        "error": {
            "code": code,
            "message": message,
            "trace_id": trace_id,
            "details": details or {},
        }
    }
    return JSONResponse(status_code=status_code, content=payload, headers={"X-Trace-Id": trace_id})
