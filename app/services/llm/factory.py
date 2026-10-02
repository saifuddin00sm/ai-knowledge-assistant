"""Builds the configured LLM client. The only place provider names are resolved."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.core.errors import ProviderError
from app.services.llm.base import LLMClient
from app.services.llm.fake import FakeLLMClient


def build_llm_client(settings: Settings | None = None) -> LLMClient:
    settings = settings or get_settings()
    if settings.llm_provider == "fake":
        return FakeLLMClient()
    if settings.llm_provider == "anthropic":
        from app.services.llm.anthropic_client import AnthropicClient

        return AnthropicClient(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
            effort=settings.llm_effort,
            thinking=settings.llm_thinking,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    raise ProviderError(f"Unknown LLM provider '{settings.llm_provider}'.")


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    return build_llm_client()
