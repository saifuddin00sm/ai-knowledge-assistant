"""Conversation persistence, history trimming, and standalone-query rewriting."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.db.models import Conversation, Message, MessageRole
from app.services.ingestion.tokenizer import count_tokens
from app.services.llm.base import LLMClient, LLMMessage
from app.services.prompts import build_rewrite_system_prompt

logger = get_logger(__name__)

FOLLOW_UP_MAX_WORDS = 12
"""Short messages are the ones most likely to depend on the previous turns."""

TITLE_MAX_CHARS = 120


@dataclass(slots=True)
class HistoryWindow:
    messages: list[LLMMessage]
    token_count: int

    @property
    def is_empty(self) -> bool:
        return not self.messages


def trim_history(messages: Sequence[LLMMessage], *, token_budget: int) -> HistoryWindow:
    """Keep the most recent messages that fit in `token_budget`, oldest first."""
    kept: list[LLMMessage] = []
    total = 0
    for message in reversed(messages):
        tokens = count_tokens(message.content)
        if kept and total + tokens > token_budget:
            break
        kept.append(message)
        total += tokens
    kept.reverse()
    return HistoryWindow(messages=kept, token_count=total)


def format_history(messages: Sequence[LLMMessage]) -> str:
    return "\n".join(f"{message.role}: {message.content}" for message in messages)


def looks_like_follow_up(message: str) -> bool:
    """Cheap gate so rewriting only costs a model call when it plausibly helps."""
    lowered = message.strip().lower()
    if len(lowered.split()) > FOLLOW_UP_MAX_WORDS:
        return False
    referential = (
        "it",
        "its",
        "it's",
        "that",
        "this",
        "they",
        "them",
        "their",
        "those",
        "these",
        "he",
        "she",
        "his",
        "her",
        "the same",
        "there",
        "one",
    )
    words = {word.strip("?.,!'\"") for word in lowered.split()}
    if words & set(referential):
        return True
    # "what about pricing?" / "and the refund policy?" style fragments.
    return lowered.startswith(("what about", "and ", "how about", "why", "when", "where"))


class ConversationService:
    def __init__(
        self,
        session: AsyncSession,
        llm: LLMClient,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._llm = llm
        self._settings = settings or get_settings()

    # -- persistence -------------------------------------------------------

    async def create(self, title: str | None = None) -> Conversation:
        conversation = Conversation(title=title)
        self._session.add(conversation)
        await self._session.commit()
        await self._session.refresh(conversation)
        return conversation

    async def get(self, conversation_id: uuid.UUID) -> Conversation:
        conversation = await self._session.get(Conversation, conversation_id)
        if conversation is None:
            raise NotFoundError(f"Conversation {conversation_id} not found.")
        return conversation

    async def get_or_create(self, conversation_id: uuid.UUID | None) -> Conversation:
        if conversation_id is None:
            return await self.create()
        return await self.get(conversation_id)

    async def delete(self, conversation_id: uuid.UUID) -> None:
        await self.get(conversation_id)
        await self._session.execute(delete(Conversation).where(Conversation.id == conversation_id))
        await self._session.commit()

    async def list_messages(self, conversation_id: uuid.UUID) -> list[Message]:
        await self.get(conversation_id)
        result = await self._session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        )
        return list(result.scalars())

    async def add_message(
        self,
        conversation: Conversation,
        *,
        role: MessageRole,
        content: str,
        sources: list[dict[str, Any]] | None = None,
        usage: dict[str, Any] | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation.id,
            role=role.value,
            content=content,
            sources=sources,
            usage=usage,
        )
        self._session.add(message)
        if role is MessageRole.USER and not conversation.title:
            conversation.title = content[:TITLE_MAX_CHARS]
        await self._session.commit()
        await self._session.refresh(message)
        return message

    # -- history + rewriting ----------------------------------------------

    async def history_window(self, conversation_id: uuid.UUID) -> HistoryWindow:
        """The last N turns, trimmed to the history token budget."""
        settings = self._settings
        result = await self._session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(settings.history_turns * 2)
        )
        rows = list(result.scalars())
        rows.reverse()
        messages = [
            LLMMessage(role="user" if row.role == "user" else "assistant", content=row.content)
            for row in rows
        ]
        return trim_history(messages, token_budget=settings.history_token_budget)

    async def rewrite_query(self, message: str, history: HistoryWindow) -> str | None:
        """Turn a follow-up into a standalone question. None when not rewritten."""
        if not self._settings.query_rewrite_enabled:
            return None
        if history.is_empty or not looks_like_follow_up(message):
            return None

        system = build_rewrite_system_prompt(format_history(history.messages))
        response = await self._llm.complete(
            system=system,
            messages=[LLMMessage(role="user", content=message)],
            max_tokens=256,
        )
        rewritten = response.text.strip().strip('"')
        if not rewritten or rewritten.lower() == message.strip().lower():
            return None
        logger.info(
            "query_rewritten",
            extra={"original": message, "rewritten": rewritten},
        )
        return rewritten
