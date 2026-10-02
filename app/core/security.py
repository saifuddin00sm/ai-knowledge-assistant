"""Optional API-key auth: active only when API_KEY is set in the environment."""

from __future__ import annotations

import hmac

from fastapi import Security
from fastapi.security import APIKeyHeader

from app.core.config import get_settings
from app.core.errors import UnauthorizedError

api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="Required only when the server is started with API_KEY set.",
)


def require_api_key(provided: str | None = Security(api_key_header)) -> None:
    """Router dependency. A no-op when no API_KEY is configured."""
    settings = get_settings()
    if not settings.api_key:
        return
    if provided is None:
        raise UnauthorizedError("Missing X-API-Key header.")
    if not hmac.compare_digest(provided, settings.api_key):
        raise UnauthorizedError("Invalid API key.")
