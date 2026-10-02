"""Config-gated behaviour: API-key auth and hybrid (vector + full-text) search."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.main import app
from tests.integration.conftest import upload_and_wait

HYBRID_DOC = (
    "# Runbook\n\n"
    "To rotate the signing certificate, run `nwctl cert rotate --service gateway` "
    "and confirm the fingerprint.\n\n"
    "Rollbacks are performed with `nwctl release rollback --to previous`.\n"
)


def override_settings(**changes: Any) -> Settings:
    """Replace the settings dependency for the duration of a test."""
    current = get_settings()
    patched = Settings(**{**current.model_dump(), **changes})
    app.dependency_overrides[get_settings] = lambda: patched
    return patched


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.pop(get_settings, None)


# -- API key ---------------------------------------------------------------


async def test_api_key_is_required_when_configured(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The guard reads settings directly rather than through a dependency, so
    # that one API_KEY value protects every route including future ones.
    monkeypatch.setattr("app.core.security.get_settings", lambda: Settings(api_key="s3cret"))

    unauthenticated = await client.get("/documents")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "unauthorized"

    wrong = await client.get("/documents", headers={"X-API-Key": "nope"})
    assert wrong.status_code == 401

    authorized = await client.get("/documents", headers={"X-API-Key": "s3cret"})
    assert authorized.status_code == 200


async def test_health_stays_open_when_a_key_is_configured(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: Settings(api_key="s3cret"))
    assert (await client.get("/health")).status_code == 200


# -- hybrid search ---------------------------------------------------------


async def test_hybrid_search_finds_a_lexical_match(client: httpx.AsyncClient) -> None:
    """A rare literal term should be found through the full-text half of RRF.

    The default embedder is lexical too, so this asserts the hybrid path runs
    end to end against the real tsvector index and returns fused results -
    not that hybrid beats vector-only on this corpus.
    """
    document = await upload_and_wait(client, "runbook.md", HYBRID_DOC)
    override_settings(hybrid_search_enabled=True)

    response = await client.post("/chat", json={"message": "nwctl cert rotate gateway fingerprint"})
    assert response.status_code == 200
    body = response.json()
    assert body["sources"], "hybrid retrieval should return the runbook chunk"
    assert {source["document_id"] for source in body["sources"]} == {document["id"]}
    assert all(0.0 <= source["score"] <= 1.0 for source in body["sources"])


async def test_hybrid_search_still_refuses_an_unrelated_question(
    client: httpx.AsyncClient,
) -> None:
    await upload_and_wait(client, "runbook.md", HYBRID_DOC)
    override_settings(hybrid_search_enabled=True)

    body = (
        await client.post("/chat", json={"message": "How do migrating storks navigate at night?"})
    ).json()
    assert body["grounded"] is False
