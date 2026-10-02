"""Provider interfaces: hashing embedder, retry/backoff, fake LLM, factories."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pytest

from app.core.config import Settings
from app.core.errors import ProviderError
from app.services.embeddings.base import Embedder, TransientEmbeddingError
from app.services.embeddings.factory import build_embedder
from app.services.embeddings.hashing import HashingEmbedder
from app.services.llm.base import LLMMessage
from app.services.llm.factory import build_llm_client
from app.services.llm.fake import FakeLLMClient
from app.services.prompts import (
    REFUSAL_PHRASE,
    REWRITE_SENTINEL,
    build_answer_system_prompt,
    build_rewrite_system_prompt,
    format_context_block,
)

# -- hashing embedder ------------------------------------------------------


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def test_hashing_embeddings_are_deterministic_and_sized() -> None:
    embedder = HashingEmbedder(dimensions=256)
    first = embedder.encode("paid annual leave")
    second = embedder.encode("paid annual leave")
    assert first == second
    assert len(first) == 256


def test_hashing_embeddings_are_unit_length() -> None:
    vector = HashingEmbedder(dimensions=256).encode("some text to encode")
    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-9)


def test_empty_text_gets_a_valid_vector_that_matches_nothing() -> None:
    embedder = HashingEmbedder(dimensions=1024)
    empty = embedder.encode("   ")
    assert math.isclose(math.sqrt(sum(v * v for v in empty)), 1.0, rel_tol=1e-9)
    assert abs(cosine(empty, embedder.encode("real words here"))) < 0.2
    assert empty == embedder.encode("")


def test_lexical_overlap_ranks_above_unrelated_text() -> None:
    embedder = HashingEmbedder(dimensions=1024)
    query = embedder.encode("how many days of paid annual leave")
    on_topic = embedder.encode(
        "Every full-time employee receives 28 days of paid annual leave per year."
    )
    off_topic = embedder.encode("Alert rules are evaluated every 60 seconds by default.")
    assert cosine(query, on_topic) > cosine(query, off_topic)


def test_stopwords_do_not_contribute_to_the_vector() -> None:
    embedder = HashingEmbedder(dimensions=512)
    assert embedder.encode("the leave policy") == embedder.encode("leave policy")
    assert embedder.encode("of the and is") == embedder.encode("")


def test_a_short_question_separates_relevant_from_irrelevant_chunks() -> None:
    """The similarity floor only works if this gap exists."""
    embedder = HashingEmbedder(dimensions=1536)
    question = embedder.encode("How long are audit logs retained?")
    relevant = embedder.encode(
        "## Data retention\n\nAudit logs covering authentication, permission changes "
        "and data exports are retained for 400 days."
    )
    irrelevant = embedder.encode(
        "## Alerting\n\nAlert rules are written in LQL and evaluated every 60 seconds."
    )
    assert cosine(question, relevant) > cosine(question, irrelevant)


def test_dimension_floor_is_enforced() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        HashingEmbedder(dimensions=4)


async def test_embed_documents_preserves_order_across_batches() -> None:
    embedder = HashingEmbedder(dimensions=64)
    texts = [f"document number {index}" for index in range(10)]
    vectors = await embedder.embed_documents(texts, batch_size=3)
    assert len(vectors) == 10
    assert vectors[7] == embedder.encode(texts[7])


# -- retry / backoff ------------------------------------------------------


class FlakyEmbedder(Embedder):
    name = "flaky"

    def __init__(self, failures: int) -> None:
        self.model = "flaky-1"
        self.dimensions = 4
        self.remaining_failures = failures
        self.attempts = 0

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.attempts += 1
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise TransientEmbeddingError("429 rate limited")
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


class BrokenEmbedder(Embedder):
    name = "broken"

    def __init__(self) -> None:
        self.model = "broken-1"
        self.dimensions = 4

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0, 0.0]]  # wrong count on purpose


async def test_transient_failures_are_retried() -> None:
    embedder = FlakyEmbedder(failures=2)
    vectors = await embedder.embed_batch(["a", "b"], max_retries=5, backoff_base_seconds=0.0)
    assert len(vectors) == 2
    assert embedder.attempts == 3


async def test_retries_are_bounded_and_surface_a_provider_error() -> None:
    embedder = FlakyEmbedder(failures=99)
    with pytest.raises(ProviderError, match="after 2 retries"):
        await embedder.embed_batch(["a"], max_retries=2, backoff_base_seconds=0.0)
    assert embedder.attempts == 3


async def test_a_provider_returning_the_wrong_count_is_an_error() -> None:
    with pytest.raises(ProviderError, match="returned 1 vectors for 2 inputs"):
        await BrokenEmbedder().embed_batch(["a", "b"])


async def test_empty_batch_short_circuits() -> None:
    assert await FlakyEmbedder(failures=99).embed_batch([]) == []


# -- fake LLM -------------------------------------------------------------


def context_prompt() -> str:
    return build_answer_system_prompt(
        format_context_block(
            [
                (
                    1,
                    "handbook.md",
                    None,
                    "# Handbook\n\nFictional demo document.\n\n"
                    "Employees receive 28 days of paid annual leave.\n\n"
                    "Expenses must be submitted within 60 days.",
                ),
                (2, "faq.md", 3, "The Team plan costs USD 199 per month."),
            ]
        )
    )


async def test_fake_llm_quotes_the_matching_sentence_with_a_citation() -> None:
    response = await FakeLLMClient().complete(
        system=context_prompt(),
        messages=[LLMMessage(role="user", content="How many days of paid annual leave?")],
        max_tokens=256,
    )
    assert response.text == "Employees receive 28 days of paid annual leave. [1]"
    assert response.usage.input_tokens and response.usage.output_tokens


async def test_fake_llm_picks_a_different_sentence_for_a_different_question() -> None:
    response = await FakeLLMClient().complete(
        system=context_prompt(),
        messages=[LLMMessage(role="user", content="How long do I have to submit expenses?")],
        max_tokens=256,
    )
    assert response.text == "Expenses must be submitted within 60 days. [1]"


async def test_fake_llm_keeps_a_line_wrapped_sentence_whole() -> None:
    """Source documents wrap lines mid-sentence; the quote must not be cut there."""
    system = build_answer_system_prompt(
        format_context_block(
            [(1, "handbook.md", None, "Employees receive 28 days of paid\nannual leave per year.")]
        )
    )
    response = await FakeLLMClient().complete(
        system=system,
        messages=[LLMMessage(role="user", content="How much annual leave?")],
        max_tokens=256,
    )
    assert response.text == "Employees receive 28 days of paid\nannual leave per year. [1]"


async def test_fake_llm_only_ever_cites_the_first_excerpt() -> None:
    response = await FakeLLMClient().complete(
        system=context_prompt(),
        messages=[LLMMessage(role="user", content="What does the Team plan cost?")],
        max_tokens=256,
    )
    assert response.text.endswith("[1]")
    assert "[2]" not in response.text


async def test_fake_llm_refuses_when_there_is_no_context() -> None:
    response = await FakeLLMClient().complete(
        system=build_answer_system_prompt(format_context_block([])),
        messages=[LLMMessage(role="user", content="Anything?")],
        max_tokens=256,
    )
    assert response.text == REFUSAL_PHRASE


async def test_fake_llm_echoes_the_question_for_rewrite_prompts() -> None:
    system = build_rewrite_system_prompt("user: earlier question")
    assert REWRITE_SENTINEL in system
    response = await FakeLLMClient().complete(
        system=system,
        messages=[LLMMessage(role="user", content="what about it?")],
        max_tokens=64,
    )
    assert response.text == "what about it?"


async def test_fake_llm_stream_reassembles_into_the_same_answer() -> None:
    client = FakeLLMClient()
    system = context_prompt()
    messages = [LLMMessage(role="user", content="How much leave?")]

    pieces: list[str] = []
    done = 0
    async for event in client.stream(system=system, messages=messages, max_tokens=256):
        if event.type == "delta":
            pieces.append(event.text)
        else:
            done += 1
            assert event.usage is not None

    expected = await client.complete(system=system, messages=messages, max_tokens=256)
    assert "".join(pieces) == expected.text
    assert done == 1


# -- factories ------------------------------------------------------------


def test_embedding_factory_builds_the_configured_provider() -> None:
    embedder = build_embedder(Settings(embedding_provider="hashing", embedding_dim=256))
    assert isinstance(embedder, HashingEmbedder)
    assert embedder.dimensions == 256


def test_openai_embedder_requires_a_key() -> None:
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        build_embedder(Settings(embedding_provider="openai", openai_api_key=None))


def test_llm_factory_builds_the_fake_provider() -> None:
    assert isinstance(build_llm_client(Settings(llm_provider="fake")), FakeLLMClient)


def test_anthropic_client_requires_a_key() -> None:
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY"):
        build_llm_client(Settings(llm_provider="anthropic", anthropic_api_key=None))
