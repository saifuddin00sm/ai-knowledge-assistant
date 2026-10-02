"""Fixtures shared by the integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

LEAVE_DOC = (
    "# Leave policy\n\n"
    "Every full-time employee receives 28 days of paid annual leave per year, "
    "in addition to public holidays.\n\n"
    "Up to five unused leave days may be carried into the next calendar year "
    "and expire on 31 March.\n"
)

PRICING_DOC = (
    "# Lumen pricing\n\n"
    "The Team plan costs USD 199 per month and includes 150 GB of monthly ingest.\n\n"
    "Overage on the Team plan is billed at USD 0.40 per gigabyte.\n"
)


async def upload_text(client: httpx.AsyncClient, filename: str, body: str) -> dict[str, Any]:
    """Upload a document and return the response payload.

    Ingestion runs in a FastAPI background task, which the ASGI transport runs
    to completion before the request returns - so the document is already
    terminal (`ready` or `failed`) by the time this function returns.
    """
    response = await client.post(
        "/documents", files={"file": (filename, body.encode("utf-8"), "text/markdown")}
    )
    assert response.status_code in (200, 201), response.text
    payload: dict[str, Any] = response.json()
    return payload


async def upload_and_wait(client: httpx.AsyncClient, filename: str, body: str) -> dict[str, Any]:
    created = await upload_text(client, filename, body)
    response = await client.get(f"/documents/{created['id']}")
    assert response.status_code == 200, response.text
    document: dict[str, Any] = response.json()
    assert document["status"] == "ready", document
    return document


@pytest.fixture
async def leave_document(client: httpx.AsyncClient) -> AsyncIterator[dict[str, Any]]:
    yield await upload_and_wait(client, "leave-policy.md", LEAVE_DOC)


@pytest.fixture
async def pricing_document(client: httpx.AsyncClient) -> AsyncIterator[dict[str, Any]]:
    yield await upload_and_wait(client, "lumen-pricing.md", PRICING_DOC)
