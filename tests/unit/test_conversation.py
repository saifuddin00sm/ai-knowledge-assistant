"""History trimming, the follow-up heuristic, and query rewriting."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

import pytest

from app.core.config import Settings
from app.services.conversation import (
    ConversationService,
    HistoryWindow,
    format_history,
    looks_like_follow_up,
    trim_history,
)
from app.services.llm.base import (
    LLMClient,
    LLMMessage,
    LLMResponse,
    LLMStreamEvent,
    LLMUsage,
)
from app.services.prompts import REWRITE_SENTINEL


class StubLLM(LLMClient):
    """Records the prompts it was given and replays a scripted answer."""

    name = "stub"

    def __init__(self, reply: str) -> None:
        self.model = "stub-1"
        self._reply = reply
        self.calls: list[tuple[str, list[LLMMessage]]] = []

    async def complete(
        self, *, system: str, messages: Sequence[LLMMessage], max_tokens: int
    ) -> LLMResponse:
        self.calls.append((system, list(messages)))
        return LLMResponse(text=self._reply, model=self.model, usage=LLMUsage(1, 1))

    async def stream(
        self, *, system: str, messages: Sequence[LLMMessage], max_tokens: int
    ) -> AsyncIterator[LLMStreamEvent]:
        self.calls.append((system, list(messages)))
        yield LLMStreamEvent(type="delta", text=self._reply)
        yield LLMStreamEvent(type="done", usage=LLMUsage(1, 1))


def message(role: str, content: str) -> LLMMessage:
    return LLMMessage(role="user" if role == "user" else "assistant", content=content)


# -- trimming --------------------------------------------------------------


def test_trim_history_keeps_the_most_recent_messages() -> None:
    history = [message("user", "x" * 400), message("assistant", "y" * 400), message("user", "z")]
    window = trim_history(history, token_budget=10)
    assert [m.content for m in window.messages] == ["z"]


def test_trim_history_preserves_chronological_order() -> None:
    history = [message("user", "one"), message("assistant", "two"), message("user", "three")]
    window = trim_history(history, token_budget=1000)
    assert [m.content for m in window.messages] == ["one", "two", "three"]
    assert window.token_count > 0


def test_trim_history_keeps_one_message_even_over_budget() -> None:
    window = trim_history([message("user", "x" * 10_000)], token_budget=5)
    assert len(window.messages) == 1


def test_empty_history() -> None:
    window = trim_history([], token_budget=100)
    assert window.is_empty
    assert window.token_count == 0


def test_format_history_is_role_prefixed() -> None:
    text = format_history([message("user", "hi"), message("assistant", "hello")])
    assert text == "user: hi\nassistant: hello"


# -- follow-up heuristic ---------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "what about its pricing?",
        "And the refund policy?",
        "How much does it include?",
        "Is that the same for Starter?",
        "why?",
    ],
)
def test_detects_follow_ups(text: str) -> None:
    assert looks_like_follow_up(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "How many days of paid annual leave do Northwind Labs employees receive each year?",
        "List the supported Lumen integrations",
    ],
)
def test_ignores_self_contained_questions(text: str) -> None:
    assert looks_like_follow_up(text) is False


# -- rewriting -------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    return Settings(query_rewrite_enabled=True, history_turns=4, history_token_budget=800)


async def test_rewrite_uses_history_and_returns_a_standalone_query(settings: Settings) -> None:
    llm = StubLLM("What does the Lumen Team plan include in monthly ingest?")
    service = ConversationService(session=None, llm=llm, settings=settings)  # type: ignore[arg-type]
    history = HistoryWindow(
        messages=[
            message("user", "What does the Lumen Team plan cost?"),
            message("assistant", "USD 199 per month [1]."),
        ],
        token_count=20,
    )

    rewritten = await service.rewrite_query("How much ingest does it include?", history)

    assert rewritten == "What does the Lumen Team plan include in monthly ingest?"
    system, messages = llm.calls[0]
    assert REWRITE_SENTINEL in system
    assert "Lumen Team plan cost" in system
    assert messages[-1].content == "How much ingest does it include?"


async def test_no_rewrite_without_history(settings: Settings) -> None:
    llm = StubLLM("irrelevant")
    service = ConversationService(session=None, llm=llm, settings=settings)  # type: ignore[arg-type]
    assert await service.rewrite_query("what about it?", HistoryWindow([], 0)) is None
    assert llm.calls == []


async def test_no_rewrite_for_a_self_contained_question(settings: Settings) -> None:
    llm = StubLLM("irrelevant")
    service = ConversationService(session=None, llm=llm, settings=settings)  # type: ignore[arg-type]
    history = HistoryWindow([message("user", "earlier question")], 5)
    question = "How many days of paid annual leave do Northwind Labs employees receive?"
    assert await service.rewrite_query(question, history) is None
    assert llm.calls == []


async def test_rewrite_disabled_by_configuration() -> None:
    llm = StubLLM("rewritten")
    service = ConversationService(
        session=None,  # type: ignore[arg-type]
        llm=llm,
        settings=Settings(query_rewrite_enabled=False),
    )
    history = HistoryWindow([message("user", "earlier")], 5)
    assert await service.rewrite_query("what about it?", history) is None
    assert llm.calls == []


async def test_echoed_rewrite_is_treated_as_no_rewrite(settings: Settings) -> None:
    llm = StubLLM("what about it?")
    service = ConversationService(session=None, llm=llm, settings=settings)  # type: ignore[arg-type]
    history = HistoryWindow([message("user", "earlier")], 5)
    assert await service.rewrite_query("what about it?", history) is None
