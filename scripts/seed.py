"""Ingest everything in sample_docs/ through the running API.

Usage:
    make seed                      # or: uv run python -m scripts.seed
    API_BASE_URL=... API_KEY=... uv run python -m scripts.seed
"""

from __future__ import annotations

import mimetypes
import sys
import time
from pathlib import Path

import httpx

from scripts._client import explain_error, make_client, require_api

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_docs"
POLL_TIMEOUT_SECONDS = 180
POLL_INTERVAL_SECONDS = 1.0
TERMINAL = {"ready", "failed"}


def upload(client: httpx.Client, path: Path) -> str | None:
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as handle:
        response = client.post("/documents", files={"file": (path.name, handle, media_type)})
    if response.status_code not in (200, 201):
        print(f"  {path.name}: upload failed - {explain_error(response)}")
        return None
    body = response.json()
    note = "already ingested" if response.status_code == 200 else "uploaded"
    print(f"  {path.name}: {note} (id={body['id']})")
    document_id: str = body["id"]
    return document_id


def wait_for_ready(client: httpx.Client, document_id: str) -> dict[str, object]:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        response = client.get(f"/documents/{document_id}")
        response.raise_for_status()
        body: dict[str, object] = response.json()
        if body["status"] in TERMINAL:
            return body
        time.sleep(POLL_INTERVAL_SECONDS)
    return {"status": "timeout", "chunk_count": 0, "error_message": "poll timed out"}


def main() -> int:
    files = sorted(
        path
        for path in SAMPLE_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in {".md", ".txt", ".pdf", ".docx"}
    )
    if not files:
        print(f"No documents found in {SAMPLE_DIR}")
        return 1

    with make_client() as client:
        health = require_api(client)
        print(
            f"API ok - llm={health.get('llm_provider')} "
            f"embeddings={health.get('embedding_provider')} db={health.get('database')}"
        )
        print(f"Seeding {len(files)} document(s) from {SAMPLE_DIR}:")

        document_ids = [document_id for path in files if (document_id := upload(client, path))]
        if not document_ids:
            return 1

        print("Waiting for ingestion to finish...")
        failures = 0
        for document_id in document_ids:
            result = wait_for_ready(client, document_id)
            status = result["status"]
            if status == "ready":
                print(f"  {result['filename']}: ready ({result['chunk_count']} chunks)")
            else:
                failures += 1
                print(f"  {document_id}: {status} - {result.get('error_message')}")

    print("Seed complete." if not failures else f"Seed finished with {failures} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
