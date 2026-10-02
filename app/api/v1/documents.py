"""Document upload, listing, detail and deletion."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, File, Query, Response, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import IngestionPipelineDep, SessionDep
from app.core.errors import InvalidRequestError, NotFoundError
from app.db.models import Chunk, Document
from app.schemas.common import ErrorResponse
from app.schemas.documents import (
    DeleteResponse,
    DocumentChunkPreview,
    DocumentDetail,
    DocumentListResponse,
    DocumentSummary,
)
from app.services.generation import make_snippet
from app.services.ingestion.pipeline import delete_document

router = APIRouter(prefix="/documents", tags=["documents"])

COMMON_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid X-API-Key."},
    404: {"model": ErrorResponse, "description": "Document not found."},
}


@router.post(
    "",
    response_model=DocumentSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document for ingestion",
    description=(
        "Accepts PDF, DOCX, TXT and MD. The file is validated and stored "
        "synchronously, then parsed, chunked and embedded in a background task. "
        "Poll `GET /documents/{id}` until `status` is `ready` or `failed`.\n\n"
        "Uploading a byte-identical file again returns the existing document "
        "with HTTP 200 instead of 201. If that document never finished "
        "ingesting (status `pending` or `failed`), re-uploading requeues it."
    ),
    responses={
        200: {"model": DocumentSummary, "description": "Identical document already ingested."},
        413: {"model": ErrorResponse, "description": "File exceeds MAX_UPLOAD_MB."},
        415: {"model": ErrorResponse, "description": "Unsupported file type."},
        422: {"model": ErrorResponse, "description": "Empty or unreadable file."},
    },
)
async def upload_document(
    session: SessionDep,
    pipeline: IngestionPipelineDep,
    background_tasks: BackgroundTasks,
    response: Response,
    file: UploadFile = File(..., description="PDF, DOCX, TXT or MD file."),
) -> DocumentSummary:
    if not file.filename:
        raise InvalidRequestError("Upload is missing a filename.")
    data = await file.read()
    registration = await pipeline.register(
        session,
        filename=file.filename,
        content_type=file.content_type,
        data=data,
    )
    if registration.should_process:
        background_tasks.add_task(pipeline.process, registration.document.id, data)
    if not registration.created:
        response.status_code = status.HTTP_200_OK
    return DocumentSummary.model_validate(registration.document)


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents with their ingestion status",
    responses=COMMON_ERRORS,
)
async def list_documents(
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponse:
    total = (await session.execute(select(func.count(Document.id)))).scalar_one()
    rows = (
        await session.execute(
            select(Document).order_by(Document.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars()
    return DocumentListResponse(
        documents=[DocumentSummary.model_validate(row) for row in rows], total=total
    )


@router.get(
    "/{document_id}",
    response_model=DocumentDetail,
    summary="Document detail, including chunk metadata",
    responses=COMMON_ERRORS,
)
async def get_document(session: SessionDep, document_id: uuid.UUID) -> DocumentDetail:
    document = await session.get(Document, document_id)
    if document is None:
        raise NotFoundError(f"Document {document_id} not found.")

    chunk_rows = (
        await session.execute(
            select(Chunk.chunk_index, Chunk.page, Chunk.token_count, Chunk.content)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index)
        )
    ).all()

    # Built field by field rather than validated straight off the ORM object:
    # `DocumentDetail.chunks` would otherwise trigger a lazy relationship load
    # during validation, which is illegal on an async session.
    return DocumentDetail(
        **DocumentSummary.model_validate(document).model_dump(),
        content_type=document.content_type,
        content_hash=document.content_hash,
        chunks=[
            DocumentChunkPreview(
                chunk_index=row.chunk_index,
                page=row.page,
                token_count=row.token_count,
                snippet=make_snippet(row.content, limit=200),
            )
            for row in chunk_rows
        ],
    )


@router.delete(
    "/{document_id}",
    response_model=DeleteResponse,
    summary="Delete a document and all of its chunks",
    responses=COMMON_ERRORS,
)
async def remove_document(session: SessionDep, document_id: uuid.UUID) -> DeleteResponse:
    chunks_deleted = await delete_document(session, document_id)
    return DeleteResponse(id=document_id, chunks_deleted=chunks_deleted)
