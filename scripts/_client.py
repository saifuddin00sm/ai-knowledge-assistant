"""Shared helpers for the scripts that drive the API over HTTP."""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
API_PREFIX = "/api/v1"


def base_url() -> str:
    return os.environ.get("API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def headers() -> dict[str, str]:
    api_key = os.environ.get("API_KEY")
    return {"X-API-Key": api_key} if api_key else {}


def make_client(timeout: float = 180.0) -> httpx.Client:
    return httpx.Client(base_url=f"{base_url()}{API_PREFIX}", headers=headers(), timeout=timeout)


def require_api(client: httpx.Client) -> dict[str, Any]:
    """Fail with a readable message instead of a traceback when the API is down."""
    try:
        response = client.get("/health")
    except httpx.HTTPError as exc:
        sys.exit(
            f"Cannot reach the API at {base_url()}: {exc}\n"
            "Start it with `docker compose up` (or `make dev`) and retry."
        )
    if response.status_code >= 500:
        sys.exit(f"API is unhealthy: {response.status_code} {response.text}")
    payload: dict[str, Any] = response.json()
    return payload


def explain_error(response: httpx.Response) -> str:
    try:
        body = response.json()
        error = body.get("error", {})
        return f"{response.status_code} {error.get('code')}: {error.get('message')}"
    except ValueError:
        return f"{response.status_code} {response.text[:200]}"
