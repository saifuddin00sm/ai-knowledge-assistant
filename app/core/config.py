"""Application configuration, loaded from environment variables."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

EmbeddingProvider = Literal["hashing", "openai"]
LLMProvider = Literal["fake", "anthropic"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Settings(BaseSettings):
    """Every knob the service has. Nothing is hardcoded in business logic."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- app ---------------------------------------------------------------
    app_name: str = "AI Knowledge Assistant"
    app_env: Literal["local", "test", "production"] = "local"
    log_level: str = "INFO"
    log_json: bool = True

    # -- database ----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://rag:rag@localhost:5432/rag"
    db_pool_size: int = 5
    db_max_overflow: int = 5

    # -- http --------------------------------------------------------------
    # NoDecode keeps pydantic-settings from JSON-decoding the env value first,
    # so `_parse_list` below can accept `a,b,c` as well as a JSON array.
    # 3001 is included because `next dev` silently falls back to it when 3000 is
    # already taken, and a CORS failure there is an unhelpful way to find out.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:3001"]
    )
    api_key: str | None = None
    """When set, every /api/v1 route except /health requires the X-API-Key header."""

    # -- uploads -----------------------------------------------------------
    max_upload_mb: int = 20
    allowed_extensions: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["pdf", "docx", "txt", "md"]
    )

    # -- chunking ----------------------------------------------------------
    chunk_size_tokens: int = 600
    chunk_overlap_tokens: int = 100

    # -- embeddings --------------------------------------------------------
    embedding_provider: EmbeddingProvider = "hashing"
    embedding_model: str = "local-hashing-v1"
    embedding_dim: int = 1536
    embedding_batch_size: int = 64
    embedding_max_retries: int = 5
    embedding_backoff_base_seconds: float = 0.5

    # -- llm ---------------------------------------------------------------
    llm_provider: LLMProvider = "fake"
    llm_model: str = "claude-opus-5"
    llm_max_tokens: int = 4096
    llm_effort: Effort = "low"
    llm_thinking: Literal["adaptive", "disabled"] = "adaptive"
    """Anthropic only. 'disabled' lowers latency but is rejected above 'high' effort."""
    llm_timeout_seconds: float = 120.0

    # -- retrieval ---------------------------------------------------------
    retrieval_top_k: int = 5
    retrieval_min_score: float = 0.15
    """Minimum cosine similarity (1 - cosine distance) for a chunk to be usable.

    This is the dial that turns an off-topic question into a refusal. 0.15
    separates relevant from irrelevant for both bundled embedders on
    `sample_docs/`; re-tune it if you change embedder or corpus.
    """
    context_token_budget: int = 3000
    hybrid_search_enabled: bool = False
    hybrid_rrf_k: int = 60
    hybrid_candidate_multiplier: int = 4

    # -- conversation ------------------------------------------------------
    history_turns: int = 4
    history_token_budget: int = 800
    query_rewrite_enabled: bool = True

    # -- provider credentials ---------------------------------------------
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    @field_validator("cors_origins", "allowed_extensions", mode="before")
    @classmethod
    def _parse_list(cls, value: object) -> object:
        """Accept `a,b,c` from the environment as well as a JSON array.

        These fields are annotated `NoDecode`, so the raw environment string
        arrives here undecoded and this validator owns both forms.
        """
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.startswith("["):
            return json.loads(text)
        return [item.strip() for item in text.split(",") if item.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def sync_database_url(self) -> str:
        """Driver-less URL, used by Alembic which runs its own engine."""
        return self.database_url.replace("+asyncpg", "")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
