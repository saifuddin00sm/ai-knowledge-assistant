"""LLM provider interface.

Generation code depends only on these types, so `LLM_PROVIDER` can be switched
without touching prompt building, citation mapping, or the HTTP layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal

Role = Literal["user", "assistant"]


@dataclass(slots=True)
class LLMMessage:
    role: Role
    content: str


@dataclass(slots=True)
class LLMUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(slots=True)
class LLMResponse:
    text: str
    model: str
    usage: LLMUsage


@dataclass(slots=True)
class LLMStreamEvent:
    """`delta` carries incremental text; exactly one `done` ends the stream."""

    type: Literal["delta", "done"]
    text: str = ""
    usage: LLMUsage | None = None


class LLMClient(ABC):
    name: str
    model: str

    @abstractmethod
    async def complete(
        self,
        *,
        system: str,
        messages: Sequence[LLMMessage],
        max_tokens: int,
    ) -> LLMResponse:
        """Single non-streaming completion."""

    @abstractmethod
    def stream(
        self,
        *,
        system: str,
        messages: Sequence[LLMMessage],
        max_tokens: int,
    ) -> AsyncIterator[LLMStreamEvent]:
        """Token stream, terminated by a single `done` event carrying usage."""
