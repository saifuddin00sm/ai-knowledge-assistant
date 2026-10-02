"""Prompt building, context budgeting, citation mapping and grounding checks."""

from __future__ import annotations

import uuid

from app.schemas.chat import Source
from app.services.generation import (
    build_sources,
    build_system_prompt,
    cited_indices,
    is_grounded,
    make_snippet,
    sanitize_citations,
    select_context,
)
from app.services.prompts import NO_CONTEXT_MARKER, REFUSAL_PHRASE
from app.services.retrieval import RetrievedChunk


def chunk(
    *,
    index: int = 0,
    tokens: int = 100,
    content: str = "body text",
    filename: str = "doc.md",
    page: int | None = None,
    score: float = 0.5,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        filename=filename,
        page=page,
        chunk_index=index,
        content=content,
        token_count=tokens,
        score=score,
    )


# -- context selection -----------------------------------------------------


def test_select_context_keeps_best_chunks_within_budget() -> None:
    chunks = [chunk(index=i, tokens=100, score=1.0 - i / 10) for i in range(5)]
    selected = select_context(chunks, token_budget=250)
    assert [c.chunk_index for c in selected] == [0, 1]


def test_select_context_always_keeps_at_least_one_chunk() -> None:
    selected = select_context([chunk(tokens=5000)], token_budget=100)
    assert len(selected) == 1


def test_select_context_skips_an_oversized_chunk_but_keeps_later_ones() -> None:
    chunks = [chunk(index=0, tokens=50), chunk(index=1, tokens=5000), chunk(index=2, tokens=40)]
    selected = select_context(chunks, token_budget=120)
    assert [c.chunk_index for c in selected] == [0, 2]


def test_select_context_with_no_chunks() -> None:
    assert select_context([], token_budget=100) == []


# -- sources ---------------------------------------------------------------


def test_build_sources_numbers_from_one_and_carries_metadata() -> None:
    chunks = [
        chunk(index=3, filename="handbook.md", page=None, score=0.812345),
        chunk(index=7, filename="faq.pdf", page=2, score=0.4),
    ]
    sources = build_sources(chunks)

    assert [source.index for source in sources] == [1, 2]
    assert sources[0].chunk_index == 3
    assert sources[0].filename == "handbook.md"
    assert sources[0].page is None
    assert sources[0].score == 0.8123
    assert sources[1].page == 2


def test_make_snippet_collapses_whitespace_and_truncates() -> None:
    assert make_snippet("a\n\n  b\tc") == "a b c"
    long = "word " * 200
    snippet = make_snippet(long, limit=20)
    assert len(snippet) <= 20
    assert snippet.endswith("…")


# -- prompt ----------------------------------------------------------------


def test_system_prompt_numbers_excerpts_and_names_sources() -> None:
    prompt = build_system_prompt(
        [
            chunk(content="Employees get 28 days.", filename="handbook.md"),
            chunk(content="Team costs USD 199.", filename="faq.md", page=4),
        ]
    )
    assert "[1] source: handbook.md" in prompt
    assert "Employees get 28 days." in prompt
    assert "[2] source: faq.md, page 4" in prompt
    assert REFUSAL_PHRASE in prompt
    assert NO_CONTEXT_MARKER not in prompt


def test_system_prompt_marks_the_no_context_case() -> None:
    prompt = build_system_prompt([])
    assert NO_CONTEXT_MARKER in prompt
    assert REFUSAL_PHRASE in prompt


# -- citations -------------------------------------------------------------


def test_cited_indices_are_deduplicated_in_order() -> None:
    assert cited_indices("a [2] b [1] c [2]") == [2, 1]
    assert cited_indices("no citations here") == []


def test_sanitize_citations_drops_markers_without_a_source() -> None:
    answer = "Leave is 28 days [1], and pricing is USD 199 [7]."
    assert (
        sanitize_citations(answer, source_count=1)
        == "Leave is 28 days [1], and pricing is USD 199."
    )


def test_sanitize_citations_drops_everything_when_there_are_no_sources() -> None:
    assert sanitize_citations("Answer [1][2]", source_count=0) == "Answer"


def test_sanitize_citations_keeps_valid_markers_untouched() -> None:
    answer = "First [1]. Second [2]."
    assert sanitize_citations(answer, source_count=2) == answer


# -- grounding -------------------------------------------------------------


def source(index: int = 1) -> Source:
    return Source(
        index=index,
        document_id=uuid.uuid4(),
        filename="doc.md",
        page=None,
        chunk_index=0,
        snippet="snippet",
        score=0.6,
    )


def test_not_grounded_without_sources() -> None:
    assert is_grounded("Anything at all [1]", []) is False


def test_not_grounded_when_the_model_refuses() -> None:
    assert is_grounded(REFUSAL_PHRASE, [source()]) is False


def test_grounded_for_a_normal_cited_answer() -> None:
    assert is_grounded("Employees get 28 days [1].", [source()]) is True
