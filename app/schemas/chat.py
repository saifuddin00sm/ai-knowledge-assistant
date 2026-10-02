"""Request/response models for /chat and /chat/stream."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class Source(BaseModel):
    """One retrieved chunk, numbered to match the `[n]` markers in the answer."""

    index: int = Field(description="1-based citation number used in the answer text.")
    document_id: uuid.UUID
    filename: str
    page: int | None = None
    chunk_index: int
    snippet: str
    score: float = Field(description="Cosine similarity in [0, 1]; higher is closer.")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "index": 1,
                    "document_id": "7a1f3f4e-2c9a-4a1f-9d3c-6b8a1f2e4d55",
                    "filename": "employee-handbook.md",
                    "page": None,
                    "chunk_index": 2,
                    "snippet": "Northwind Labs offers 28 days of paid leave per year...",
                    "score": 0.71,
                }
            ]
        }
    )


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: uuid.UUID | None = Field(
        default=None,
        description="Omit to start a new conversation; the id is returned in the response.",
    )
    document_ids: list[uuid.UUID] | None = Field(
        default=None,
        description="Restrict retrieval to these documents. Omit to search everything.",
    )
    top_k: int | None = Field(default=None, ge=1, le=20)
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "message": "How many paid leave days do employees get?",
                    "conversation_id": None,
                    "top_k": 5,
                }
            ]
        }
    )


class Timings(BaseModel):
    retrieval_ms: int
    generation_ms: int
    total_ms: int


class Usage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    answer: str
    sources: list[Source]
    grounded: bool = Field(
        description="False when the retrieved context did not support an answer."
    )
    rewritten_query: str | None = Field(
        default=None,
        description="The standalone query actually used for retrieval, when rewriting applied.",
    )
    model: str
    usage: Usage
    timings: Timings

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "conversation_id": "2f6b1a0c-8e4d-4c2a-9f11-5a7e3d9b0c21",
                    "message_id": "a0e5c3d2-11b4-4f6a-8c7d-9e1f2a3b4c5d",
                    "answer": "Employees receive 28 days of paid leave per year [1].",
                    "sources": [
                        {
                            "index": 1,
                            "document_id": "7a1f3f4e-2c9a-4a1f-9d3c-6b8a1f2e4d55",
                            "filename": "employee-handbook.md",
                            "page": None,
                            "chunk_index": 2,
                            "snippet": "Northwind Labs offers 28 days of paid leave...",
                            "score": 0.71,
                        }
                    ],
                    "grounded": True,
                    "rewritten_query": None,
                    "model": "claude-opus-5",
                    "usage": {"input_tokens": 912, "output_tokens": 48},
                    "timings": {
                        "retrieval_ms": 31,
                        "generation_ms": 1840,
                        "total_ms": 1879,
                    },
                }
            ]
        }
    )
