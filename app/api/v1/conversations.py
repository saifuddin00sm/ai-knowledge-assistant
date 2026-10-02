"""Conversation creation, message history and deletion."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import ConversationServiceDep
from app.db.models import MessageRole
from app.schemas.chat import Source, Usage
from app.schemas.common import ErrorResponse
from app.schemas.conversations import (
    ConversationCreateRequest,
    ConversationResponse,
    MessageListResponse,
    MessageResponse,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])

NOT_FOUND: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Conversation not found."}
}


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an empty conversation",
    description=(
        "Optional: `POST /chat` creates a conversation on the fly when "
        "`conversation_id` is omitted."
    ),
)
async def create_conversation(
    payload: ConversationCreateRequest,
    conversations: ConversationServiceDep,
) -> ConversationResponse:
    conversation = await conversations.create(title=payload.title)
    return ConversationResponse.model_validate(conversation)


@router.get(
    "/{conversation_id}/messages",
    response_model=MessageListResponse,
    summary="Full message history, with the sources cited by each answer",
    responses=NOT_FOUND,
)
async def list_messages(
    conversation_id: uuid.UUID, conversations: ConversationServiceDep
) -> MessageListResponse:
    messages = await conversations.list_messages(conversation_id)
    return MessageListResponse(
        conversation_id=conversation_id,
        messages=[
            MessageResponse(
                id=message.id,
                role=MessageRole(message.role),
                content=message.content,
                sources=[Source.model_validate(item) for item in message.sources or []],
                usage=Usage.model_validate(message.usage) if message.usage else None,
                created_at=message.created_at,
            )
            for message in messages
        ],
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation and its messages",
    responses=NOT_FOUND,
)
async def delete_conversation(
    conversation_id: uuid.UUID, conversations: ConversationServiceDep
) -> None:
    await conversations.delete(conversation_id)
