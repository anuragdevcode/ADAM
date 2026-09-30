"""ADAM API Server — FastAPI application factory."""

import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

from adam.api.middleware import TraceIdMiddleware, RateLimitMiddleware
from adam.api.routers import (
    audit,
    auth,
    chat,
    documents,
    precedents,
    review,
    sessions,
    sources,
    ingestions,
    system,
    user,
    voice,
    v1_chat,
    v1_documents,
    v1_ingestions,
    v1_search,
    v1_feedback,
)
from adam.config import CORS_ORIGINS, DATABASE_URL, SECURITY_HEADERS_ENABLED
from adam.db.session import get_engine, get_session, init_db

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforce defense-in-depth HTTP security headers (CSP, HSTS, frame-busting, nosniff) (S12)."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if SECURITY_HEADERS_ENABLED:
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; object-src 'none'; frame-ancestors 'none';"
            )
            env = os.getenv("ADAM_ENV", "development").lower()
            if env in ("production", "prod"):
                response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Configure OpenTelemetry OTLP exporter when endpoint is provided (H8)
    _configure_otel(app)

    engine = get_engine(DATABASE_URL)
    init_db(engine)
    logger.info("Database initialized.")

    # Bootstrap initial dev admin if user table is empty
    from adam.auth.service import seed_default_admin_if_empty
    db_session = get_session(engine)
    try:
        seed_default_admin_if_empty(db_session)
    finally:
        db_session.close()

    yield
    logger.info("API Server shutdown cleanly.")


def _configure_otel(app: FastAPI) -> None:
    """Configure OpenTelemetry OTLP tracing when OTEL_EXPORTER_OTLP_ENDPOINT is set.

    Gracefully skips configuration if the ``opentelemetry-sdk`` package is not
    installed so that the base image remains lightweight.
    """
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not otlp_endpoint:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME

        resource = Resource.create({SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "adam-api")})
        provider = TracerProvider(resource=resource)

        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("OpenTelemetry OTLP gRPC exporter configured → %s", otlp_endpoint)
        except ImportError:
            logger.warning(
                "opentelemetry-exporter-otlp-proto-grpc not installed; "
                "tracing spans will not be exported. Install adam[otel] to enable export."
            )

        trace.set_tracer_provider(provider)

        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(app)
            logger.info("OpenTelemetry FastAPI instrumentation enabled.")
        except ImportError:
            logger.debug("opentelemetry-instrumentation-fastapi not installed; skipping.")

        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            SQLAlchemyInstrumentor().instrument()
            logger.info("OpenTelemetry SQLAlchemy instrumentation enabled.")
        except ImportError:
            logger.debug("opentelemetry-instrumentation-sqlalchemy not installed; skipping.")

    except ImportError:
        logger.warning(
            "opentelemetry-sdk not installed; distributed tracing disabled. "
            "Set OTEL_EXPORTER_OTLP_ENDPOINT and install adam[otel] to enable."
        )


def create_app() -> FastAPI:
    env = os.getenv("ADAM_ENV", "development").lower()
    is_prod = env in ("production", "prod")

    _app = FastAPI(
        title="ADAM API",
        version="1.0.0",
        description="Uttarakhand Public Records AI Assistant & Knowledge Engine",
        lifespan=lifespan,
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )

    # Global Exception Handlers for Structured Errors
    @_app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        trace_id = getattr(request.state, "trace_id", None) or request.headers.get("X-Trace-Id") or "trace_default"
        code_map = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            422: "UNPROCESSABLE_ENTITY",
            429: "RATE_LIMIT_EXCEEDED",
            500: "INTERNAL_ERROR",
            504: "GATEWAY_TIMEOUT",
        }
        code = code_map.get(exc.status_code, "ERROR")
        headers = dict(exc.headers or {})
        headers["X-Trace-Id"] = trace_id
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code,
                    "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                    "trace_id": trace_id,
                    "details": exc.detail if isinstance(exc.detail, dict) else {},
                }
            },
            headers=headers,
        )

    @_app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        trace_id = getattr(request.state, "trace_id", None) or request.headers.get("X-Trace-Id") or "trace_default"
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Invalid request parameters",
                    "trace_id": trace_id,
                    "details": {"errors": exc.errors()},
                }
            },
            headers={"X-Trace-Id": trace_id},
        )

    # Middleware Pipeline
    _app.add_middleware(SecurityHeadersMiddleware)
    _app.add_middleware(RateLimitMiddleware)
    _app.add_middleware(TraceIdMiddleware)
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @_app.get("/api/health", tags=["system"])
    async def healthcheck():
        """Container and orchestration readiness probe."""
        return {"status": "ok", "service": "adam-api"}

    # /api Routers (Internal & Web UI)
    _app.include_router(auth.router, prefix="/api")
    _app.include_router(chat.router, prefix="/api")
    _app.include_router(sessions.router, prefix="/api")
    _app.include_router(voice.router, prefix="/api")
    _app.include_router(system.router, prefix="/api")
    _app.include_router(documents.router, prefix="/api")
    _app.include_router(precedents.router, prefix="/api")
    _app.include_router(sources.router, prefix="/api")
    _app.include_router(ingestions.router, prefix="/api")
    _app.include_router(audit.router, prefix="/api")
    _app.include_router(review.router, prefix="/api")
    _app.include_router(user.router, prefix="/api")

    # /v1 Gateway Routers (Hardened Core API Contract)
    _app.include_router(v1_chat.router)
    _app.include_router(v1_documents.router)
    _app.include_router(v1_ingestions.router)
    _app.include_router(v1_search.router)
    _app.include_router(v1_feedback.router)

    return _app


app = create_app()


def run_server(host="0.0.0.0", port=8000, reload=False):
    uvicorn.run("adam.api.app:app", host=host, port=port, reload=reload)
