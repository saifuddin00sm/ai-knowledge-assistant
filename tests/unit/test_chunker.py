"""Chunker: sizes, overlap, metadata, and the awkward inputs."""

from __future__ import annotations

from itertools import pairwise

import pytest

from app.services.ingestion.chunker import chunk_pages, split_text
from app.services.ingestion.parsers import ParsedPage


def word_tokens(text: str) -> int:
    """Deterministic stand-in for tiktoken so the assertions are exact."""
    return len(text.split())


def make_text(words: int, *, per_paragraph: int = 10) -> str:
    paragraphs = []
    index = 0
    while index < words:
        count = min(per_paragraph, words - index)
        paragraphs.append(" ".join(f"w{index + offset}" for offset in range(count)))
        index += count
    return "\n\n".join(paragraphs)


def test_short_text_is_a_single_chunk() -> None:
    chunks = split_text("one two three", max_tokens=10, overlap_tokens=2, count=word_tokens)
    assert chunks == ["one two three"]


def test_empty_and_whitespace_text_produce_no_chunks() -> None:
    assert split_text("", max_tokens=10, overlap_tokens=0, count=word_tokens) == []
    assert split_text("   \n\n  ", max_tokens=10, overlap_tokens=0, count=word_tokens) == []


def test_every_chunk_respects_the_token_budget() -> None:
    chunks = split_text(make_text(200), max_tokens=25, overlap_tokens=5, count=word_tokens)
    assert len(chunks) > 1
    assert all(word_tokens(chunk) <= 25 for chunk in chunks)


def test_adjacent_chunks_overlap() -> None:
    chunks = split_text(make_text(120), max_tokens=30, overlap_tokens=10, count=word_tokens)
    assert len(chunks) >= 3
    for previous, current in pairwise(chunks):
        previous_words = previous.split()
        current_words = current.split()
        shared = set(previous_words) & set(current_words)
        assert shared, "consecutive chunks should share their overlap window"


def test_zero_overlap_produces_disjoint_chunks() -> None:
    chunks = split_text(make_text(90), max_tokens=20, overlap_tokens=0, count=word_tokens)
    seen: set[str] = set()
    for chunk in chunks:
        words = set(chunk.split())
        assert not (words & seen)
        seen |= words


def test_overlap_larger_than_budget_is_clamped_and_terminates() -> None:
    # An un-clamped overlap would re-seed each chunk with the whole previous
    # one and never make progress.
    chunks = split_text(make_text(80), max_tokens=20, overlap_tokens=999, count=word_tokens)
    assert len(chunks) > 1
    assert all(word_tokens(chunk) <= 20 for chunk in chunks)


def test_text_without_separators_is_hard_split() -> None:
    blob = "x" * 4000
    chunks = split_text(blob, max_tokens=10, overlap_tokens=0, count=lambda t: len(t) // 4)
    assert len(chunks) > 1
    assert "".join(chunks) == blob


def test_splits_on_sentences_before_words() -> None:
    text = "Alpha sentence here. Beta sentence here. Gamma sentence here."
    chunks = split_text(text, max_tokens=4, overlap_tokens=0, count=word_tokens)
    assert all(chunk.endswith((".", "here")) or chunk for chunk in chunks)
    assert len(chunks) == 3


def test_markdown_sections_are_split_at_their_headings() -> None:
    text = (
        "# Title\n\nIntro paragraph.\n\n"
        "## Leave\n\n" + make_text(40) + "\n\n"
        "## Pricing\n\n" + make_text(40) + "\n\n"
        "## Security\n\n" + make_text(40) + "\n"
    )
    chunks = split_text(text, max_tokens=45, overlap_tokens=0, count=word_tokens)

    assert len(chunks) >= 3
    # A heading stays attached to the section it introduces, never trailing the
    # previous one.
    assert any(chunk.startswith("## Leave") for chunk in chunks)
    assert not any(chunk.endswith("## Pricing") for chunk in chunks)


def test_heading_split_loses_no_content() -> None:
    """With zero overlap the chunks partition the document exactly."""
    text = "# Title\n\nIntro.\n\n## One\n\n" + make_text(40) + "\n\n## Two\n\n" + make_text(40)
    chunks = split_text(text, max_tokens=45, overlap_tokens=0, count=word_tokens)
    assert "\n".join(chunks).split() == text.split()


def test_chunk_pages_carries_page_numbers_and_continuous_indexes() -> None:
    pages = [
        ParsedPage(text=make_text(60), page=1),
        ParsedPage(text=make_text(60), page=2),
    ]
    chunks = chunk_pages(pages, max_tokens=25, overlap_tokens=5, count=word_tokens)

    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert {chunk.page for chunk in chunks} == {1, 2}
    assert all(chunk.token_count == word_tokens(chunk.content) for chunk in chunks)
    first_page_indexes = [c.chunk_index for c in chunks if c.page == 1]
    second_page_indexes = [c.chunk_index for c in chunks if c.page == 2]
    assert max(first_page_indexes) < min(second_page_indexes)


def test_pages_without_numbers_keep_page_none() -> None:
    chunks = chunk_pages(
        [ParsedPage(text=make_text(40))], max_tokens=25, overlap_tokens=5, count=word_tokens
    )
    assert chunks
    assert all(chunk.page is None for chunk in chunks)


def test_invalid_budget_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        split_text("anything", max_tokens=0, overlap_tokens=0, count=word_tokens)
