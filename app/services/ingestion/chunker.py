"""Recursive, token-aware text splitter.

The splitter walks a list of separators from coarse (paragraph) to fine (space),
breaking text only as finely as it needs to in order to fit the token budget.
Adjacent chunks share a configurable token overlap so a fact that straddles a
boundary is still retrievable from at least one chunk.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.services.ingestion.parsers import ParsedPage
from app.services.ingestion.tokenizer import count_tokens

DEFAULT_SEPARATORS: tuple[str, ...] = (
    # Markdown headings first: cutting a structured document at its section
    # boundaries keeps each chunk about one topic, which matters more for
    # retrieval quality than any other single choice in this file.
    "\n## ",
    "\n### ",
    "\n#### ",
    "\n\n",  # paragraphs
    "\n",  # lines
    ". ",  # sentences
    "? ",
    "! ",
    "; ",
    ", ",
    " ",  # words
)

TokenCounter = Callable[[str], int]


@dataclass(slots=True)
class TextChunk:
    content: str
    chunk_index: int
    token_count: int
    page: int | None = None


def _leads_its_piece(separator: str) -> bool:
    """A heading belongs to the text that follows it, not the text before it."""
    return separator.startswith("\n#")


def _split_keeping_separator(text: str, separator: str) -> list[str]:
    """Split on `separator` without losing it, so pieces rejoin exactly."""
    parts = text.split(separator)
    if _leads_its_piece(separator):
        pieces = [parts[0], *(separator + part for part in parts[1:])]
    else:
        pieces = [part + separator for part in parts[:-1]]
        pieces.append(parts[-1])
    return [piece for piece in pieces if piece]


def _hard_split(text: str, max_tokens: int, count: TokenCounter) -> list[str]:
    """Last resort for text with no separators at all (e.g. a huge base64 blob)."""
    tokens = count(text) or 1
    chars_per_chunk = max(1, int(len(text) * max_tokens / tokens))
    return [text[i : i + chars_per_chunk] for i in range(0, len(text), chars_per_chunk)]


def _atomize(
    text: str,
    max_tokens: int,
    separators: Sequence[str],
    count: TokenCounter,
) -> list[str]:
    """Break `text` into pieces that each fit in `max_tokens`, splitting as little as possible."""
    if not text:
        return []
    if count(text) <= max_tokens:
        return [text]
    for position, separator in enumerate(separators):
        if separator not in text:
            continue
        pieces: list[str] = []
        for piece in _split_keeping_separator(text, separator):
            if count(piece) <= max_tokens:
                pieces.append(piece)
            else:
                pieces.extend(_atomize(piece, max_tokens, separators[position + 1 :], count))
        return pieces
    return _hard_split(text, max_tokens, count)


def _merge(
    atoms: Sequence[str],
    max_tokens: int,
    overlap_tokens: int,
    count: TokenCounter,
) -> list[str]:
    """Greedily pack atoms into chunks, seeding each new chunk with an overlap tail."""
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for atom in atoms:
        atom_tokens = count(atom)
        if current and current_tokens + atom_tokens > max_tokens:
            chunks.append("".join(current))
            tail: list[str] = []
            tail_tokens = 0
            for previous in reversed(current):
                previous_tokens = count(previous)
                if tail_tokens + previous_tokens > overlap_tokens:
                    break
                tail.insert(0, previous)
                tail_tokens += previous_tokens
            current, current_tokens = tail, tail_tokens
        current.append(atom)
        current_tokens += atom_tokens

    if current:
        chunks.append("".join(current))
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def split_text(
    text: str,
    *,
    max_tokens: int,
    overlap_tokens: int,
    count: TokenCounter = count_tokens,
    separators: Sequence[str] = DEFAULT_SEPARATORS,
) -> list[str]:
    """Split `text` into chunks of at most `max_tokens` tokens."""
    if max_tokens < 1:
        raise ValueError("max_tokens must be >= 1")
    text = text.strip()
    if not text:
        return []
    overlap = max(0, min(overlap_tokens, max_tokens // 2))
    atoms = _atomize(text, max_tokens, separators, count)
    return _merge(atoms, max_tokens, overlap, count)


def chunk_pages(
    pages: Sequence[ParsedPage],
    *,
    max_tokens: int,
    overlap_tokens: int,
    count: TokenCounter = count_tokens,
) -> list[TextChunk]:
    """Chunk each page independently; `chunk_index` is continuous across the document."""
    chunks: list[TextChunk] = []
    index = 0
    for page in pages:
        for content in split_text(
            page.text, max_tokens=max_tokens, overlap_tokens=overlap_tokens, count=count
        ):
            chunks.append(
                TextChunk(
                    content=content,
                    chunk_index=index,
                    token_count=count(content),
                    page=page.page,
                )
            )
            index += 1
    return chunks
