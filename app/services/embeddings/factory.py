"""Builds the configured embedder. The only place provider names are resolved."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.core.errors import ProviderError
from app.services.embeddings.base import Embedder
from app.services.embeddings.hashing import HashingEmbedder


def build_embedder(settings: Settings | None = None) -> Embedder:
    settings = settings or get_settings()
    if settings.embedding_provider == "hashing":
        return HashingEmbedder(dimensions=settings.embedding_dim, model=settings.embedding_model)
    if settings.embedding_provider == "openai":
        from app.services.embeddings.openai_embedder import OpenAIEmbedder

        return OpenAIEmbedder(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
            dimensions=settings.embedding_dim,
        )
    raise ProviderError(f"Unknown embedding provider '{settings.embedding_provider}'.")


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return build_embedder()
