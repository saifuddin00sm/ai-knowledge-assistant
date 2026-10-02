"""Application factory: logging, CORS, request ids, routers, error handlers."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger, request_id_var
from app.db.session import dispose_engine

logger = get_logger(__name__)

API_PREFIX = "/api/v1"
REQUEST_ID_HEADER = "X-Request-ID"

DESCRIPTION = """\
A document-grounded question answering API.

**How it works.** Upload PDF/DOCX/TXT/MD documents; they are parsed, split into
token-aware overlapping chunks, embedded, and stored in PostgreSQL with
pgvector. A question is embedded, matched against those chunks by cosine
similarity, and the top chunks are assembled into a token-budgeted context. The
model is instructed to answer **only** from that context and to cite excerpts
inline as `[1]`, `[2]`. When the context does not support an answer, the API
says so instead of guessing.

**Auth.** When the server is started with `API_KEY` set, every route except
`/api/v1/health` requires an `X-API-Key` header.

**Errors.** Every non-2xx response is `{"error": {"code", "message"}}`.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info(
        "startup",
        extra={
            "app_env": settings.app_env,
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
            "embedding_provider": settings.embedding_provider,
            "embedding_model": settings.embedding_model,
            "hybrid_search": settings.hybrid_search_enabled,
            "auth_required": bool(settings.api_key),
        },
    )
    yield
    await dispose_engine()
    logger.info("shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, as_json=settings.log_json)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=DESCRIPTION,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        duration_ms = int((time.perf_counter() - started) * 1000)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    register_exception_handlers(app)
    app.include_router(api_router, prefix=API_PREFIX)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": settings.app_name, "docs": "/docs", "api": API_PREFIX}

    return app


app = create_app()
