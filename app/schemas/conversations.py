"""Request/response models for the /conversations routes."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import MessageRole
from app.schemas.chat import Source, Usage


class ConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=512)


class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: MessageRole
    content: str
    sources: list[Source] = Field(default_factory=list)
    usage: Usage | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageListResponse(BaseModel):
    conversation_id: uuid.UUID
    messages: list[MessageResponse]
