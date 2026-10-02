"""Embedding provider interface.

Business logic depends only on this class, so a provider can be swapped through
`EMBEDDING_PROVIDER` without touching ingestion or retrieval.
"""

from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.core.errors import ProviderError
from app.core.logging import get_logger

logger = get_logger(__name__)


class TransientEmbeddingError(Exception):
    """Rate limit / timeout / 5xx: worth retrying with backoff."""


class Embedder(ABC):
    """A batch text -> vector encoder."""

    name: str
    model: str
    dimensions: int

    @abstractmethod
    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Encode one batch. Raise `TransientEmbeddingError` for retryable failures."""

    async def embed_batch(
        self,
        texts: Sequence[str],
        *,
        max_retries: int = 5,
        backoff_base_seconds: float = 0.5,
    ) -> list[list[float]]:
        """Encode one batch, retrying transient failures with exponential backoff."""
        if not texts:
            return []
        attempt = 0
        while True:
            try:
                vectors = await self._embed(texts)
            except TransientEmbeddingError as exc:
                attempt += 1
                if attempt > max_retries:
                    raise ProviderError(
                        f"Embedding provider '{self.name}' failed after "
                        f"{max_retries} retries: {exc}"
                    ) from exc
                delay = backoff_base_seconds * (2 ** (attempt - 1))
                delay += random.uniform(0, backoff_base_seconds)  # jitter
                logger.warning(
                    "embedding_retry",
                    extra={
                        "provider": self.name,
                        "attempt": attempt,
                        "delay_seconds": round(delay, 3),
                        "error": str(exc),
                    },
                )
                await asyncio.sleep(delay)
                continue
            except Exception as exc:
                raise ProviderError(f"Embedding provider '{self.name}' failed: {exc}") from exc

            if len(vectors) != len(texts):
                raise ProviderError(
                    f"Embedding provider '{self.name}' returned {len(vectors)} "
                    f"vectors for {len(texts)} inputs."
                )
            return vectors

    async def embed_documents(
        self,
        texts: Sequence[str],
        *,
        batch_size: int = 64,
        max_retries: int = 5,
        backoff_base_seconds: float = 0.5,
    ) -> list[list[float]]:
        """Encode many texts, in batches, preserving input order."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            vectors.extend(
                await self.embed_batch(
                    batch,
                    max_retries=max_retries,
                    backoff_base_seconds=backoff_base_seconds,
                )
            )
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_batch([text])
        return vectors[0]
