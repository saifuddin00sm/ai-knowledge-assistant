"""Token counting.

`tiktoken` needs to download its BPE table on first use. The service must still
work (and the test suite must still pass) with no network access, so the counter
falls back to a character-ratio estimate and says so in the logs exactly once.
"""

from __future__ import annotations

import functools
import math
from collections.abc import Callable

from app.core.logging import get_logger

logger = get_logger(__name__)

_FALLBACK_CHARS_PER_TOKEN = 4.0


def _approximate(text: str) -> int:
    return max(1, math.ceil(len(text) / _FALLBACK_CHARS_PER_TOKEN)) if text else 0


@functools.lru_cache(maxsize=1)
def _encoder() -> Callable[[str], int] | None:
    try:
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")
    except Exception as exc:  # pragma: no cover - depends on local cache/network
        logger.warning(
            "tiktoken_unavailable_using_estimate",
            extra={"error": str(exc), "chars_per_token": _FALLBACK_CHARS_PER_TOKEN},
        )
        return None
    return lambda text: len(encoding.encode(text, disallowed_special=()))


def count_tokens(text: str) -> int:
    """Number of tokens in `text`. Exact when tiktoken is available."""
    if not text:
        return 0
    encode = _encoder()
    if encode is None:
        return _approximate(text)
    return encode(text)
