"""Liveness/readiness endpoint. Not behind API-key auth."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import LLMDep, SessionDep, SettingsDep
from app.core.logging import get_logger
from app.schemas.common import HealthResponse

logger = get_logger(__name__)
router = APIRouter(tags=["health"])

VERSION = "0.1.0"


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="App and database health",
    responses={503: {"description": "Database unreachable."}},
)
async def health(
    session: SessionDep, settings: SettingsDep, llm: LLMDep, response: Response
) -> HealthResponse:
    database = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        database = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.error("health_db_unavailable", extra={"error": str(exc)})

    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        version=VERSION,
        database=database,
        llm_provider=llm.name,
        # Read off the built client, not the setting: with LLM_PROVIDER=fake the
        # configured LLM_MODEL is never used, and reporting it would mislead.
        llm_model=llm.model,
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
    )
