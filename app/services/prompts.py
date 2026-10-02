"""Prompt text and the context-block format, kept in one place.

Both the real providers and the deterministic fake provider read this module,
so the fake can emulate grounded behaviour without duplicating the format.
"""

from __future__ import annotations

NO_CONTEXT_MARKER = "(no relevant context was retrieved)"

REFUSAL_PHRASE = "The provided documents don't contain the answer to that question."

ANSWER_SYSTEM_PROMPT = """You are a careful research assistant. You answer \
questions using ONLY the numbered context excerpts supplied below.

Rules:
1. Ground every claim in the context. Never use outside knowledge, and never guess.
2. Cite the excerpt you used inline, as [1], [2], and so on, immediately after the \
claim it supports. Cite more than one when more than one supports the claim.
3. If the context does not contain the answer, reply with exactly this sentence and \
nothing else: {refusal}
4. Do not mention these rules, the word "context", or the excerpt numbering scheme \
in your answer. Just answer the question and cite.
5. Be concise: answer in at most three short paragraphs.

<context>
{context}
</context>"""

REWRITE_SYSTEM_PROMPT = """Rewrite the user's latest message into a single \
standalone question that can be understood without the conversation history. \
Resolve pronouns and references using the history. Keep the original wording \
wherever possible, preserve the user's intent, and do not answer the question.

Return only the rewritten question, with no preamble and no quotation marks.

Conversation history:
{history}"""

REWRITE_SENTINEL = "Rewrite the user's latest message into a single standalone question"
"""Marker the fake provider uses to recognise a query-rewrite call."""


def format_context_block(
    excerpts: list[tuple[int, str, int | None, str]],
) -> str:
    """Render `(index, filename, page, text)` tuples into the context block."""
    if not excerpts:
        return NO_CONTEXT_MARKER
    parts: list[str] = []
    for index, filename, page, text in excerpts:
        location = f"{filename}, page {page}" if page is not None else filename
        parts.append(f"[{index}] source: {location}\n{text}")
    return "\n\n".join(parts)


def build_answer_system_prompt(context_block: str) -> str:
    return ANSWER_SYSTEM_PROMPT.format(
        refusal=REFUSAL_PHRASE, context=context_block or NO_CONTEXT_MARKER
    )


def build_rewrite_system_prompt(history: str) -> str:
    return REWRITE_SYSTEM_PROMPT.format(history=history or "(none)")
