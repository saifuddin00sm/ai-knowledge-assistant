"""Request/response models for the /documents routes."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import DocumentStatus


class DocumentSummary(BaseModel):
    """A document as returned by POST /documents and GET /documents."""

    id: uuid.UUID
    filename: str
    extension: str
    size_bytes: int
    status: DocumentStatus
    chunk_count: int
    page_count: int | None = None
    error_message: str | None = Field(
        default=None, description="Populated only when status is 'failed'."
    )
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "7a1f3f4e-2c9a-4a1f-9d3c-6b8a1f2e4d55",
                    "filename": "employee-handbook.md",
                    "extension": "md",
                    "size_bytes": 5412,
                    "status": "ready",
                    "chunk_count": 4,
                    "page_count": None,
                    "error_message": None,
                    "created_at": "2026-10-02T09:14:03Z",
                    "updated_at": "2026-10-02T09:14:07Z",
                }
            ]
        },
    )


class DocumentListResponse(BaseModel):
    documents: list[DocumentSummary]
    total: int


class DocumentChunkPreview(BaseModel):
    chunk_index: int
    page: int | None
    token_count: int
    snippet: str = Field(description="First ~200 characters of the chunk.")

    model_config = ConfigDict(from_attributes=True)


class DocumentDetail(DocumentSummary):
    content_type: str
    content_hash: str
    chunks: list[DocumentChunkPreview] = Field(
        default_factory=list, description="Chunk metadata, ordered by chunk_index."
    )


class DeleteResponse(BaseModel):
    id: uuid.UUID
    deleted: bool = True
    chunks_deleted: int
