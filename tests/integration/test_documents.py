"""Upload -> ingest -> inspect -> delete, against a real database."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from tests.integration.conftest import LEAVE_DOC, upload_text


async def test_health_reports_the_database_and_providers(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["llm_provider"] == "fake"
    assert body["embedding_provider"] == "hashing"
    # The model is read off the built client, so it never advertises a model the
    # configured provider is not actually using.
    assert body["llm_model"] == "fake-deterministic-v1"
    assert body["embedding_model"] == "local-hashing-v1"
    assert body["version"]


async def test_upload_ingests_and_reaches_ready(client: httpx.AsyncClient) -> None:
    created = await upload_text(client, "leave-policy.md", LEAVE_DOC)
    assert created["status"] in {"pending", "processing", "ready"}

    detail = (await client.get(f"/documents/{created['id']}")).json()
    assert detail["status"] == "ready"
    assert detail["chunk_count"] >= 1
    assert detail["error_message"] is None
    assert detail["page_count"] is None  # markdown has no pages
    assert len(detail["chunks"]) == detail["chunk_count"]
    assert detail["chunks"][0]["chunk_index"] == 0
    assert detail["chunks"][0]["token_count"] > 0


async def test_uploading_the_same_bytes_twice_is_idempotent(client: httpx.AsyncClient) -> None:
    first = await client.post(
        "/documents", files={"file": ("a.md", LEAVE_DOC.encode(), "text/markdown")}
    )
    assert first.status_code == 201

    second = await client.post(
        "/documents", files={"file": ("different-name.md", LEAVE_DOC.encode(), "text/markdown")}
    )
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]

    listing = (await client.get("/documents")).json()
    assert listing["total"] == 1


async def test_reuploading_a_stuck_document_requeues_it(
    client: httpx.AsyncClient,
    session_factory: Any,
) -> None:
    """A document left `pending` by a crashed worker is retried on re-upload."""
    from sqlalchemy import update

    from app.db.models import Document, DocumentStatus

    created = await upload_text(client, "leave-policy.md", LEAVE_DOC)
    async with session_factory() as session:
        await session.execute(
            update(Document)
            .where(Document.id == uuid.UUID(created["id"]))
            .values(status=DocumentStatus.PENDING.value, chunk_count=0)
        )
        await session.commit()

    assert (await client.get(f"/documents/{created['id']}")).json()["status"] == "pending"

    again = await client.post(
        "/documents", files={"file": ("leave-policy.md", LEAVE_DOC.encode(), "text/markdown")}
    )
    assert again.status_code == 200
    detail = (await client.get(f"/documents/{created['id']}")).json()
    assert detail["status"] == "ready"
    assert detail["chunk_count"] >= 1


async def test_listing_is_newest_first_and_paginated(client: httpx.AsyncClient) -> None:
    for index in range(3):
        await upload_text(client, f"doc-{index}.md", f"# Doc {index}\n\nUnique body {index}.\n")

    listing = (await client.get("/documents", params={"limit": 2})).json()
    assert listing["total"] == 3
    assert len(listing["documents"]) == 2

    page_two = (await client.get("/documents", params={"limit": 2, "offset": 2})).json()
    assert len(page_two["documents"]) == 1


async def test_unsupported_file_type_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post("/documents", files={"file": ("data.csv", b"a,b,c", "text/csv")})
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"
    assert "csv" in response.json()["error"]["message"]


async def test_empty_file_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post("/documents", files={"file": ("empty.md", b"", "text/markdown")})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_oversized_file_is_rejected(client: httpx.AsyncClient) -> None:
    from app.core.config import get_settings

    oversized = b"x" * (get_settings().max_upload_bytes + 1)
    response = await client.post("/documents", files={"file": ("big.txt", oversized, "text/plain")})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_unreadable_document_is_marked_failed(client: httpx.AsyncClient) -> None:
    """A file that passes validation but has no extractable text fails loudly."""
    created = await client.post(
        "/documents",
        files={"file": ("broken.pdf", b"%PDF-1.4 not really a pdf", "application/pdf")},
    )
    assert created.status_code == 201

    detail = (await client.get(f"/documents/{created.json()['id']}")).json()
    assert detail["status"] == "failed"
    assert detail["error_message"]
    assert detail["chunk_count"] == 0


async def test_missing_document_is_a_404_with_the_standard_envelope(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(f"/documents/{uuid.uuid4()}")
    assert response.status_code == 404
    assert set(response.json()["error"]) == {"code", "message"}
    assert response.json()["error"]["code"] == "not_found"


async def test_malformed_uuid_is_a_422(client: httpx.AsyncClient) -> None:
    response = await client.get("/documents/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_delete_removes_the_document_and_its_chunks(
    client: httpx.AsyncClient, leave_document: dict[str, Any]
) -> None:
    response = await client.delete(f"/documents/{leave_document['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["deleted"] is True
    assert body["chunks_deleted"] == leave_document["chunk_count"]

    assert (await client.get(f"/documents/{leave_document['id']}")).status_code == 404

    # The chunks are gone too, so nothing can be retrieved from them any more.
    chat = await client.post("/chat", json={"message": "How many days of paid annual leave?"})
    assert chat.status_code == 200
    assert chat.json()["sources"] == []
    assert chat.json()["grounded"] is False


async def test_deleting_twice_is_a_404(
    client: httpx.AsyncClient, leave_document: dict[str, Any]
) -> None:
    assert (await client.delete(f"/documents/{leave_document['id']}")).status_code == 200
    assert (await client.delete(f"/documents/{leave_document['id']}")).status_code == 404


async def test_request_id_is_echoed(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"
