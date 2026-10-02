"""OpenAI embeddings provider (semantic retrieval; requires OPENAI_API_KEY)."""

from __future__ import annotations

from collections.abc import Sequence

from app.core.errors import ProviderError
from app.services.embeddings.base import Embedder, TransientEmbeddingError


class OpenAIEmbedder(Embedder):
    name = "openai"

    def __init__(
        self,
        api_key: str | None,
        *,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        timeout_seconds: float = 60.0,
    ) -> None:
        if not api_key:
            raise ProviderError("EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY to be set.")
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)
        self.model = model
        self.dimensions = dimensions

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        import openai

        try:
            response = await self._client.embeddings.create(
                model=self.model,
                input=list(texts),
                dimensions=self.dimensions,
                encoding_format="float",
            )
        except (
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.InternalServerError,
        ) as exc:
            raise TransientEmbeddingError(str(exc)) from exc

        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]
