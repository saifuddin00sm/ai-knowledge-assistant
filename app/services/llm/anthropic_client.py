"""Anthropic (Claude) LLM provider."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any

from app.core.errors import ProviderError
from app.core.logging import get_logger
from app.services.llm.base import (
    LLMClient,
    LLMMessage,
    LLMResponse,
    LLMStreamEvent,
    LLMUsage,
)

if TYPE_CHECKING:
    from anthropic.types import Message

logger = get_logger(__name__)

REFUSAL_TEXT = (
    "The model declined to answer this request. Please rephrase or try a different question."
)


class AnthropicClient(LLMClient):
    """Thin wrapper over `anthropic.AsyncAnthropic`.

    Note that Claude Opus 5 and the other current models do not accept
    `temperature`/`top_p` at all - generation is steered by the prompt and by
    `output_config.effort`, which is what this class exposes.
    """

    name = "anthropic"

    def __init__(
        self,
        api_key: str | None,
        *,
        model: str = "claude-opus-5",
        effort: str = "low",
        thinking: str = "adaptive",
        timeout_seconds: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        if not api_key:
            raise ProviderError("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY to be set.")
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(
            api_key=api_key, timeout=timeout_seconds, max_retries=max_retries
        )
        self.model = model
        self._effort = effort
        self._thinking = thinking

    def _request_kwargs(
        self, system: str, messages: Sequence[LLMMessage], max_tokens: int
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "output_config": {"effort": self._effort},
        }
        if self._thinking == "disabled":
            # Accepted only at effort 'high' or below on Claude Opus 5.
            kwargs["thinking"] = {"type": "disabled"}
        return kwargs

    @staticmethod
    def _text_of(message: Message) -> str:
        if message.stop_reason == "refusal":
            return REFUSAL_TEXT
        return "".join(block.text for block in message.content if block.type == "text").strip()

    @staticmethod
    def _usage_of(message: Message) -> LLMUsage:
        return LLMUsage(
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )

    async def complete(
        self,
        *,
        system: str,
        messages: Sequence[LLMMessage],
        max_tokens: int,
    ) -> LLMResponse:
        import anthropic

        try:
            message = await self._client.messages.create(
                **self._request_kwargs(system, messages, max_tokens)
            )
        except anthropic.APIError as exc:
            raise ProviderError(f"Anthropic request failed: {exc}") from exc

        return LLMResponse(
            text=self._text_of(message),
            model=message.model,
            usage=self._usage_of(message),
        )

    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[LLMMessage],
        max_tokens: int,
    ) -> AsyncIterator[LLMStreamEvent]:
        import anthropic

        try:
            async with self._client.messages.stream(
                **self._request_kwargs(system, messages, max_tokens)
            ) as stream:
                async for text in stream.text_stream:
                    yield LLMStreamEvent(type="delta", text=text)
                final = await stream.get_final_message()
        except anthropic.APIError as exc:
            raise ProviderError(f"Anthropic stream failed: {exc}") from exc

        if final.stop_reason == "refusal":
            yield LLMStreamEvent(type="delta", text=REFUSAL_TEXT)
        yield LLMStreamEvent(type="done", usage=self._usage_of(final))
