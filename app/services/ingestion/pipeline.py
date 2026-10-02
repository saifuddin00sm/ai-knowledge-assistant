"""Ingestion pipeline: validate -> dedupe -> parse -> chunk -> embed -> store.

`register` runs inside the upload request and returns immediately. `process`
runs in a FastAPI background task with its own session, and is responsible for
moving the document through pending -> processing -> ready | failed.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.errors import (
    InvalidRequestError,
    NotFoundError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)
from app.core.logging import get_logger, log_fields
from app.db.models import Chunk, Document, DocumentStatus
from app.services.embeddings.base import Embedder
from app.services.ingestion import parsers
from app.services.ingestion.chunker import chunk_pages
from app.services.ingestion.parsers import extension_of

logger = get_logger(__name__)

ERROR_MESSAGE_MAX_CHARS = 2000


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(slots=True)
class Registration:
    """Outcome of registering an upload."""

    document: Document
    created: bool
    """False when the same bytes were already uploaded (drives 200 vs 201)."""
    should_process: bool
    """True for a new document, or an existing one that never finished."""


class IngestionPipeline:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embedder: Embedder,
        settings: Settings | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._embedder = embedder
        self._settings = settings or get_settings()

    # -- validation --------------------------------------------------------

    def validate(self, filename: str, data: bytes) -> str:
        """Check type and size up front so bad uploads fail fast with a 4xx."""
        settings = self._settings
        extension = extension_of(filename)
        if extension not in settings.allowed_extensions:
            raise UnsupportedMediaTypeError(
                f"Unsupported file type '.{extension or filename}'. "
                f"Allowed: {', '.join(settings.allowed_extensions)}."
            )
        if not data:
            raise InvalidRequestError("Uploaded file is empty.")
        if len(data) > settings.max_upload_bytes:
            raise PayloadTooLargeError(
                f"File is {len(data) / 1_048_576:.1f} MB; the limit is {settings.max_upload_mb} MB."
            )
        return extension

    # -- step 1: register (inside the request) -----------------------------

    async def register(
        self,
        session: AsyncSession,
        *,
        filename: str,
        content_type: str | None,
        data: bytes,
    ) -> Registration:
        """Create (or re-find) the document row for this upload.

        Uploads are idempotent by content hash: the same bytes always map to the
        same document. An existing document that never reached `ready` is
        requeued, so a crashed or interrupted ingestion can be retried simply
        by uploading the file again.
        """
        extension = self.validate(filename, data)
        digest = content_hash(data)

        existing = (
            await session.execute(select(Document).where(Document.content_hash == digest))
        ).scalar_one_or_none()
        if existing is not None:
            unfinished = existing.status in {
                DocumentStatus.PENDING.value,
                DocumentStatus.FAILED.value,
            }
            if unfinished:
                existing.status = DocumentStatus.PENDING.value
                existing.error_message = None
                existing.chunk_count = 0
                await session.commit()
                await session.refresh(existing)
            logger.info(
                "document_duplicate",
                extra=log_fields(
                    document_id=str(existing.id),
                    filename=filename,
                    status=existing.status,
                    requeued=unfinished,
                ),
            )
            return Registration(document=existing, created=False, should_process=unfinished)

        document = Document(
            filename=filename,
            content_type=content_type or "application/octet-stream",
            extension=extension,
            size_bytes=len(data),
            content_hash=digest,
            status=DocumentStatus.PENDING.value,
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)
        logger.info(
            "document_registered",
            extra=log_fields(document_id=str(document.id), filename=filename, size_bytes=len(data)),
        )
        return Registration(document=document, created=True, should_process=True)

    # -- step 2: process (background task) --------------------------------

    async def process(self, document_id: uuid.UUID, data: bytes) -> None:
        """Parse, chunk, embed and store. Never raises; failures land on the row."""
        started = time.perf_counter()
        async with self._session_factory() as session:
            document = await session.get(Document, document_id)
            if document is None:
                logger.error("document_missing", extra={"document_id": str(document_id)})
                return
            document.status = DocumentStatus.PROCESSING.value
            document.error_message = None
            await session.commit()

            try:
                chunk_count, page_count = await self._ingest(session, document, data)
            except Exception as exc:
                await session.rollback()
                document = await session.get(Document, document_id)
                if document is not None:
                    document.status = DocumentStatus.FAILED.value
                    document.error_message = str(exc)[:ERROR_MESSAGE_MAX_CHARS]
                    document.chunk_count = 0
                    await session.commit()
                logger.exception(
                    "document_failed",
                    extra={
                        "document_id": str(document_id),
                        "error_type": type(exc).__name__,
                    },
                )
                return

            document.status = DocumentStatus.READY.value
            document.chunk_count = chunk_count
            document.page_count = page_count
            await session.commit()

        logger.info(
            "document_ready",
            extra={
                "document_id": str(document_id),
                "chunks": chunk_count,
                "pages": page_count,
                "ingest_latency_ms": int((time.perf_counter() - started) * 1000),
            },
        )

    async def _ingest(
        self, session: AsyncSession, document: Document, data: bytes
    ) -> tuple[int, int | None]:
        settings = self._settings
        parsed = parsers.parse(document.filename, data)
        if parsed.is_empty:
            raise InvalidRequestError(
                "No extractable text found in the document "
                "(it may be a scanned image; OCR is not supported)."
            )

        chunks = chunk_pages(
            parsed.pages,
            max_tokens=settings.chunk_size_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
        )
        if not chunks:
            raise InvalidRequestError("Document produced no chunks.")

        vectors = await self._embedder.embed_documents(
            [chunk.content for chunk in chunks],
            batch_size=settings.embedding_batch_size,
            max_retries=settings.embedding_max_retries,
            backoff_base_seconds=settings.embedding_backoff_base_seconds,
        )

        # Re-ingestion of the same document id replaces its chunks.
        await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
        session.add_all(
            Chunk(
                document_id=document.id,
                chunk_index=chunk.chunk_index,
                page=chunk.page,
                content=chunk.content,
                token_count=chunk.token_count,
                embedding=vector,
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        )
        await session.flush()
        return len(chunks), parsed.page_count


async def delete_document(session: AsyncSession, document_id: uuid.UUID) -> int:
    """Delete a document and its chunks. Returns the number of chunks removed."""
    document = await session.get(Document, document_id)
    if document is None:
        raise NotFoundError(f"Document {document_id} not found.")
    chunk_count = document.chunk_count
    await session.execute(delete(Document).where(Document.id == document_id))
    await session.commit()
    logger.info(
        "document_deleted",
        extra={"document_id": str(document_id), "chunks_deleted": chunk_count},
    )
    return chunk_count
