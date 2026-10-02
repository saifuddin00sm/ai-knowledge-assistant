"""Shared response models: the error envelope and health payload."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    code: str = Field(description="Stable, machine-readable error code.")
    message: str = Field(description="Human-readable explanation.")


class ErrorResponse(BaseModel):
    """Every non-2xx response from this API uses this shape."""

    error: ErrorDetail

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "error": {
                        "code": "unsupported_media_type",
                        "message": "Unsupported file type '.csv'. Allowed: pdf, docx, txt, md.",
                    }
                }
            ]
        }
    )


class HealthResponse(BaseModel):
    status: str = Field(description="'ok' when the app and database are both reachable.")
    version: str
    database: str = Field(description="'ok' or 'unavailable'.")
    llm_provider: str
    llm_model: str = Field(description="The model actually serving generation requests.")
    embedding_provider: str
    embedding_model: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "version": "0.1.0",
                    "database": "ok",
                    "llm_provider": "anthropic",
                    "llm_model": "claude-opus-5",
                    "embedding_provider": "hashing",
                    "embedding_model": "local-hashing-v1",
                }
            ]
        }
    )
