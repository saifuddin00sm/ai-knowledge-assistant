"""Grounded chat: one JSON answer, or the same answer over Server-Sent Events."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import (
    AnswerGeneratorDep,
    EmbedderDep,
    LLMDep,
    SettingsDep,
    build_answer_generator,
)
from app.core.errors import AppError, error_body
from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.common import ErrorResponse
from app.services.conversation import ConversationService

logger = get_logger(__name__)
router = APIRouter(tags=["chat"])

CHAT_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid X-API-Key."},
    404: {"model": ErrorResponse, "description": "conversation_id does not exist."},
    422: {"model": ErrorResponse, "description": "Invalid request body."},
    502: {"model": ErrorResponse, "description": "The LLM or embedding provider failed."},
}

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # stop nginx from buffering the stream
}


def sse(event: str, payload: dict[str, Any]) -> str:
    """One Server-Sent Event frame: a named event plus a compact JSON payload."""
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask a question and get a grounded, cited answer",
    description=(
        "Retrieves the most similar chunks, assembles them into a token-budgeted "
        "context, and asks the model to answer using only that context.\n\n"
        "`conversation_id` is optional: omit it to start a new conversation (the id "
        "is returned). Follow-up questions are rewritten into standalone queries "
        "before retrieval. When the context does not support an answer, `grounded` "
        "is `false` and the answer says the documents do not contain it."
    ),
    responses=CHAT_ERRORS,
)
async def chat(payload: ChatRequest, generator: AnswerGeneratorDep) -> ChatResponse:
    result = await generator.answer(
        message=payload.message,
        conversation_id=payload.conversation_id,
        document_ids=payload.document_ids,
        top_k=payload.top_k,
        min_score=payload.min_score,
    )
    return ChatResponse(
        conversation_id=result.conversation_id,
        message_id=result.message_id,
        answer=result.answer,
        sources=result.sources,
        grounded=result.grounded,
        rewritten_query=result.rewritten_query,
        model=result.model,
        usage=result.usage,
        timings=result.timings,
    )


@router.post(
    "/chat/stream",
    summary="Same as POST /chat, streamed as Server-Sent Events",
    description=(
        "Returns `text/event-stream`. Event sequence:\n\n"
        "1. `start` - `{conversation_id, rewritten_query, retrieval_ms}`, once, "
        "after retrieval completes.\n"
        "2. `token` - `{text}`, repeated; concatenate the `text` fields to build "
        "the answer.\n"
        "3. `sources` - `{conversation_id, message_id, answer, grounded, sources, "
        "usage, timings}`, once; `answer` is the final, citation-sanitised text.\n"
        "4. `done` - `{}`, once, last.\n\n"
        "`error` - `{error: {code, message}}` may replace events 2-4 if generation "
        "fails after the stream has started; the HTTP status is already 200 at that "
        "point, so clients must handle this event."
    ),
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": (
                        'event: start\ndata: {"conversation_id":"2f6b…","rewritten_query":null,'
                        '"retrieval_ms":31}\n\n'
                        'event: token\ndata: {"text":"Employees receive 28 days"}\n\n'
                        'event: sources\ndata: {"message_id":"a0e5…","answer":"…[1]",'
                        '"grounded":true,"sources":[…]}\n\n'
                        "event: done\ndata: {}\n\n"
                    ),
                }
            },
            "description": "The SSE stream.",
        },
        **CHAT_ERRORS,
    },
)
async def chat_stream(
    payload: ChatRequest,
    embedder: EmbedderDep,
    llm: LLMDep,
    settings: SettingsDep,
) -> StreamingResponse:
    session_factory = get_session_factory()

    # Validate the conversation up front so a bad id is a real 404 rather than
    # an `error` event on an HTTP 200 stream.
    if payload.conversation_id is not None:
        async with session_factory() as session:
            await ConversationService(session, llm, settings).get(payload.conversation_id)

    async def event_stream() -> AsyncIterator[str]:
        # The session is opened here, not injected: FastAPI tears down
        # `yield` dependencies before a streaming body is consumed.
        async with session_factory() as session:
            generator = build_answer_generator(session, embedder, llm, settings)
            try:
                async for event, data in generator.stream(
                    message=payload.message,
                    conversation_id=payload.conversation_id,
                    document_ids=payload.document_ids,
                    top_k=payload.top_k,
                    min_score=payload.min_score,
                ):
                    yield sse(event, data)
            except AppError as exc:
                logger.warning(
                    "chat_stream_app_error",
                    extra={"code": exc.code, "error": exc.message},
                )
                yield sse("error", error_body(exc.code, exc.message))
            except Exception as exc:
                logger.exception("chat_stream_failed", extra={"error_type": type(exc).__name__})
                yield sse(
                    "error",
                    error_body("internal_error", "Generation failed mid-stream."),
                )

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=SSE_HEADERS)
