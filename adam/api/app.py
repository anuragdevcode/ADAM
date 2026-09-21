"""ADAM API Server — FastAPI application factory."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from adam.api.middleware import TraceIdMiddleware, RateLimitMiddleware
from adam.api.routers import (
    audit,
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
from adam.config import DATABASE_URL
from adam.db.session import get_engine, init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine(DATABASE_URL)
    init_db(engine)
    logger.info("Database initialized.")
    yield
    logger.info("API Server shutdown cleanly.")


def create_app() -> FastAPI:
    _app = FastAPI(
        title="ADAM API",
        version="1.0.0",
        description="Uttarakhand Public Records AI Assistant & Knowledge Engine",
        lifespan=lifespan,
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
    _app.add_middleware(RateLimitMiddleware)
    _app.add_middleware(TraceIdMiddleware)
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @_app.get("/api/health", tags=["system"])
    async def healthcheck():
        """Container and orchestration readiness probe."""
        return {"status": "ok", "service": "adam-api"}

    # /api Routers (Internal & Web UI)
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
