"""Deterministic offline LLM provider.

A stand-in, not a model. It reads the top context excerpt out of the system
prompt, quotes back the sentence with the most word overlap with the question,
appends a `[1]` citation, and refuses when no context was retrieved. There is no
inference of any kind: the behaviour is pure string matching, which is exactly
why it is useful - the full ingest -> retrieve -> cite -> stream path can be
exercised in tests, in CI and in the demo with no API key and no network, and
every assertion about it is stable.

Anything resembling answer *quality* in its output comes from retrieval, not
from this class.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence

from app.services.llm.base import (
    LLMClient,
    LLMMessage,
    LLMResponse,
    LLMStreamEvent,
    LLMUsage,
)
from app.services.prompts import (
    NO_CONTEXT_MARKER,
    REFUSAL_PHRASE,
    REWRITE_SENTINEL,
)

_EXCERPT_RE = re.compile(
    r"^\[1\] source: .*?$\n(.*?)(?=\n\n\[\d+\] source:|\n</context>|\Z)", re.MULTILINE | re.DOTALL
)
# Sentence end, or a blank line. Not a single newline: source documents wrap
# lines mid-sentence, and splitting there truncates the quote.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")
_WORD_RE = re.compile(r"[a-z0-9]+")

MIN_WORD_LENGTH = 4
"""Short words carry no signal for this crude overlap score."""


def _keywords(text: str) -> set[str]:
    return {word for word in _WORD_RE.findall(text.lower()) if len(word) >= MIN_WORD_LENGTH}


def _sentences(text: str) -> list[str]:
    return [piece.strip() for piece in _SENTENCE_RE.split(text.strip()) if piece.strip()]


def _best_sentence(excerpt: str, question: str) -> str:
    """The sentence of `excerpt` sharing the most words with `question`.

    Ties keep document order, so the result is stable for a given input.
    """
    sentences = _sentences(excerpt)
    if not sentences:
        return excerpt.strip()
    wanted = _keywords(question)
    if not wanted:
        return sentences[0]
    scored = [
        (len(wanted & _keywords(sentence)), -index, sentence)
        for index, sentence in enumerate(sentences)
    ]
    best_score, _, best = max(scored)
    return best if best_score else sentences[0]


class FakeLLMClient(LLMClient):
    name = "fake"

    def __init__(self, model: str = "fake-deterministic-v1") -> None:
        self.model = model

    def _answer(self, system: str, messages: Sequence[LLMMessage]) -> str:
        if REWRITE_SENTINEL in system:
            # Query rewriting: echo the latest user message unchanged.
            return messages[-1].content.strip() if messages else ""
        if NO_CONTEXT_MARKER in system:
            return REFUSAL_PHRASE
        match = _EXCERPT_RE.search(system)
        if not match:
            return REFUSAL_PHRASE
        question = messages[-1].content if messages else ""
        sentence = _best_sentence(match.group(1), question)
        if not sentence:
            return REFUSAL_PHRASE
        return f"{sentence} [1]"

    @staticmethod
    def _usage(system: str, messages: Sequence[LLMMessage], answer: str) -> LLMUsage:
        prompt_chars = len(system) + sum(len(m.content) for m in messages)
        return LLMUsage(
            input_tokens=max(1, prompt_chars // 4),
            output_tokens=max(1, len(answer) // 4),
        )

    async def complete(
        self,
        *,
        system: str,
        messages: Sequence[LLMMessage],
        max_tokens: int,
    ) -> LLMResponse:
        answer = self._answer(system, messages)
        return LLMResponse(
            text=answer, model=self.model, usage=self._usage(system, messages, answer)
        )

    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[LLMMessage],
        max_tokens: int,
    ) -> AsyncIterator[LLMStreamEvent]:
        answer = self._answer(system, messages)
        words = answer.split(" ")
        for position, word in enumerate(words):
            text = word if position == 0 else f" {word}"
            yield LLMStreamEvent(type="delta", text=text)
        yield LLMStreamEvent(type="done", usage=self._usage(system, messages, answer))
