"""Grounded generation: context assembly, prompt building, citations, streaming."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.models import MessageRole
from app.schemas.chat import Source, Timings, Usage
from app.services.conversation import ConversationService
from app.services.llm.base import LLMClient, LLMMessage, LLMUsage
from app.services.prompts import (
    REFUSAL_PHRASE,
    build_answer_system_prompt,
    format_context_block,
)
from app.services.retrieval import RetrievedChunk, Retriever

logger = get_logger(__name__)

SNIPPET_CHARS = 280
CITATION_RE = re.compile(r"\[(\d+)\]")


def select_context(chunks: Sequence[RetrievedChunk], token_budget: int) -> list[RetrievedChunk]:
    """Take the highest-ranked chunks that fit the budget, best first."""
    selected: list[RetrievedChunk] = []
    used = 0
    for chunk in chunks:
        if selected and used + chunk.token_count > token_budget:
            continue
        selected.append(chunk)
        used += chunk.token_count
    return selected


def make_snippet(text: str, limit: int = SNIPPET_CHARS) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def build_sources(chunks: Sequence[RetrievedChunk]) -> list[Source]:
    """Number the chunks 1..n; those numbers are the `[n]` markers in the answer."""
    return [
        Source(
            index=position,
            document_id=chunk.document_id,
            filename=chunk.filename,
            page=chunk.page,
            chunk_index=chunk.chunk_index,
            snippet=make_snippet(chunk.content),
            score=round(chunk.score, 4),
        )
        for position, chunk in enumerate(chunks, start=1)
    ]


def build_system_prompt(chunks: Sequence[RetrievedChunk]) -> str:
    excerpts = [
        (position, chunk.filename, chunk.page, chunk.content)
        for position, chunk in enumerate(chunks, start=1)
    ]
    return build_answer_system_prompt(format_context_block(excerpts))


def cited_indices(answer: str) -> list[int]:
    """Citation numbers appearing in `answer`, in order of first appearance."""
    seen: list[int] = []
    for match in CITATION_RE.finditer(answer):
        number = int(match.group(1))
        if number not in seen:
            seen.append(number)
    return seen


def sanitize_citations(answer: str, source_count: int) -> str:
    """Drop `[n]` markers that do not map to a real source, so citations never lie."""

    def replace(match: re.Match[str]) -> str:
        number = int(match.group(1))
        return match.group(0) if 1 <= number <= source_count else ""

    cleaned = CITATION_RE.sub(replace, answer)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    # Removing a marker can leave a gap before punctuation ("199 ." / "199 ,").
    cleaned = re.sub(r"[ \t]+([.,;:!?)])", r"\1", cleaned)
    return cleaned.strip()


def is_grounded(answer: str, sources: Sequence[Source]) -> bool:
    if not sources:
        return False
    normalized = " ".join(answer.lower().split())
    return REFUSAL_PHRASE.lower().rstrip(".") not in normalized


@dataclass(slots=True)
class ChatResult:
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    answer: str
    sources: list[Source]
    grounded: bool
    rewritten_query: str | None
    model: str
    usage: Usage
    timings: Timings


@dataclass(slots=True)
class StreamContext:
    """Everything the SSE route needs after the prompt is built."""

    conversation_id: uuid.UUID
    system_prompt: str
    llm_messages: list[LLMMessage]
    sources: list[Source] = field(default_factory=list)
    rewritten_query: str | None = None
    retrieval_ms: int = 0


class AnswerGenerator:
    """Orchestrates retrieve -> prompt -> generate -> persist for one turn."""

    def __init__(
        self,
        retriever: Retriever,
        llm: LLMClient,
        conversations: ConversationService,
        settings: Settings | None = None,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._conversations = conversations
        self._settings = settings or get_settings()

    async def prepare(
        self,
        *,
        message: str,
        conversation_id: uuid.UUID | None,
        document_ids: Sequence[uuid.UUID] | None = None,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> StreamContext:
        """Resolve the conversation, rewrite the query, retrieve, and build the prompt."""
        conversation = await self._conversations.get_or_create(conversation_id)
        history = await self._conversations.history_window(conversation.id)
        rewritten = await self._conversations.rewrite_query(message, history)
        search_query = rewritten or message

        retrieval = await self._retriever.retrieve(
            search_query,
            top_k=top_k,
            min_score=min_score,
            document_ids=document_ids,
        )
        context = select_context(retrieval.chunks, self._settings.context_token_budget)
        sources = build_sources(context)

        await self._conversations.add_message(conversation, role=MessageRole.USER, content=message)

        return StreamContext(
            conversation_id=conversation.id,
            system_prompt=build_system_prompt(context),
            llm_messages=[*history.messages, LLMMessage(role="user", content=message)],
            sources=sources,
            rewritten_query=rewritten,
            retrieval_ms=retrieval.latency_ms,
        )

    async def _persist_answer(
        self,
        conversation_id: uuid.UUID,
        answer: str,
        sources: Sequence[Source],
        usage: Usage,
    ) -> uuid.UUID:
        conversation = await self._conversations.get(conversation_id)
        message = await self._conversations.add_message(
            conversation,
            role=MessageRole.ASSISTANT,
            content=answer,
            sources=[source.model_dump(mode="json") for source in sources],
            usage=usage.model_dump(mode="json"),
        )
        return message.id

    @staticmethod
    def _to_usage(usage: LLMUsage | None) -> Usage:
        if usage is None:
            return Usage()
        return Usage(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)

    async def answer(
        self,
        *,
        message: str,
        conversation_id: uuid.UUID | None,
        document_ids: Sequence[uuid.UUID] | None = None,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> ChatResult:
        started = time.perf_counter()
        context = await self.prepare(
            message=message,
            conversation_id=conversation_id,
            document_ids=document_ids,
            top_k=top_k,
            min_score=min_score,
        )

        generation_started = time.perf_counter()
        response = await self._llm.complete(
            system=context.system_prompt,
            messages=context.llm_messages,
            max_tokens=self._settings.llm_max_tokens,
        )
        generation_ms = int((time.perf_counter() - generation_started) * 1000)

        answer = sanitize_citations(response.text, len(context.sources))
        if not answer:
            answer = REFUSAL_PHRASE
        usage = self._to_usage(response.usage)
        message_id = await self._persist_answer(
            context.conversation_id, answer, context.sources, usage
        )
        total_ms = int((time.perf_counter() - started) * 1000)

        logger.info(
            "chat_complete",
            extra={
                "conversation_id": str(context.conversation_id),
                "sources": len(context.sources),
                "cited": cited_indices(answer),
                "retrieval_latency_ms": context.retrieval_ms,
                "generation_latency_ms": generation_ms,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "model": response.model,
            },
        )

        return ChatResult(
            conversation_id=context.conversation_id,
            message_id=message_id,
            answer=answer,
            sources=context.sources,
            grounded=is_grounded(answer, context.sources),
            rewritten_query=context.rewritten_query,
            model=response.model,
            usage=usage,
            timings=Timings(
                retrieval_ms=context.retrieval_ms,
                generation_ms=generation_ms,
                total_ms=total_ms,
            ),
        )

    async def stream(
        self,
        *,
        message: str,
        conversation_id: uuid.UUID | None,
        document_ids: Sequence[uuid.UUID] | None = None,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Yield `(event_name, payload)` pairs for the SSE route to serialise."""
        started = time.perf_counter()
        context = await self.prepare(
            message=message,
            conversation_id=conversation_id,
            document_ids=document_ids,
            top_k=top_k,
            min_score=min_score,
        )
        yield (
            "start",
            {
                "conversation_id": str(context.conversation_id),
                "rewritten_query": context.rewritten_query,
                "retrieval_ms": context.retrieval_ms,
            },
        )

        generation_started = time.perf_counter()
        pieces: list[str] = []
        usage = Usage()
        async for event in self._llm.stream(
            system=context.system_prompt,
            messages=context.llm_messages,
            max_tokens=self._settings.llm_max_tokens,
        ):
            if event.type == "delta":
                pieces.append(event.text)
                yield ("token", {"text": event.text})
            else:
                usage = self._to_usage(event.usage)
        generation_ms = int((time.perf_counter() - generation_started) * 1000)

        answer = sanitize_citations("".join(pieces), len(context.sources))
        if not answer:
            answer = REFUSAL_PHRASE
        message_id = await self._persist_answer(
            context.conversation_id, answer, context.sources, usage
        )
        total_ms = int((time.perf_counter() - started) * 1000)

        logger.info(
            "chat_stream_complete",
            extra={
                "conversation_id": str(context.conversation_id),
                "sources": len(context.sources),
                "cited": cited_indices(answer),
                "retrieval_latency_ms": context.retrieval_ms,
                "generation_latency_ms": generation_ms,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            },
        )

        yield (
            "sources",
            {
                "conversation_id": str(context.conversation_id),
                "message_id": str(message_id),
                "answer": answer,
                "grounded": is_grounded(answer, context.sources),
                "sources": [source.model_dump(mode="json") for source in context.sources],
                "usage": usage.model_dump(mode="json"),
                "timings": {
                    "retrieval_ms": context.retrieval_ms,
                    "generation_ms": generation_ms,
                    "total_ms": total_ms,
                },
            },
        )
        yield ("done", {})
