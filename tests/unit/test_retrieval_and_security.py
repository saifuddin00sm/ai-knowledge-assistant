"""Reciprocal rank fusion, the API-key dependency, and config parsing."""

from __future__ import annotations

import uuid

import pytest

from app.core.config import Settings
from app.core.errors import UnauthorizedError
from app.core.security import require_api_key
from app.services.retrieval import RetrievedChunk, Retriever


def chunk(name: str, score: float) -> RetrievedChunk:
    """A chunk whose id is derived from `name`, so lists can share entries."""
    return RetrievedChunk(
        chunk_id=uuid.uuid5(uuid.NAMESPACE_OID, name),
        document_id=uuid.uuid5(uuid.NAMESPACE_OID, "doc"),
        filename="doc.md",
        page=None,
        chunk_index=0,
        content=name,
        token_count=10,
        score=score,
    )


# -- reciprocal rank fusion ------------------------------------------------


def test_rrf_promotes_items_present_in_both_lists() -> None:
    vector = [chunk("a", 0.9), chunk("b", 0.8), chunk("c", 0.7)]
    keyword = [chunk("c", 0.7), chunk("d", 0.2), chunk("a", 0.9)]

    fused = Retriever._reciprocal_rank_fusion([vector, keyword], k=60)
    names = [item.content for item in fused]

    assert set(names) == {"a", "b", "c", "d"}
    assert names[0] == "a", "rank 1 in one list and rank 3 in the other should win"
    assert names.index("c") < names.index("b")
    assert names[-1] == "d", "a single low-rank appearance should sort last"


def test_rrf_with_one_empty_list_preserves_the_other_order() -> None:
    vector = [chunk("a", 0.9), chunk("b", 0.5)]
    fused = Retriever._reciprocal_rank_fusion([vector, []], k=60)
    assert [item.content for item in fused] == ["a", "b"]


def test_rrf_with_no_results() -> None:
    assert Retriever._reciprocal_rank_fusion([[], []], k=60) == []


def test_rrf_deduplicates() -> None:
    single = [chunk("a", 0.9)]
    fused = Retriever._reciprocal_rank_fusion([single, single, single], k=60)
    assert len(fused) == 1


# -- api key ---------------------------------------------------------------


def test_auth_is_a_no_op_when_no_key_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: Settings(api_key=None))
    assert require_api_key(None) is None


def test_missing_header_is_rejected_when_a_key_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: Settings(api_key="secret"))
    with pytest.raises(UnauthorizedError, match="Missing X-API-Key"):
        require_api_key(None)


def test_wrong_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: Settings(api_key="secret"))
    with pytest.raises(UnauthorizedError, match="Invalid API key"):
        require_api_key("nope")


def test_correct_key_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: Settings(api_key="secret"))
    assert require_api_key("secret") is None


# -- settings --------------------------------------------------------------


def test_csv_environment_values_are_split() -> None:
    settings = Settings(cors_origins="http://a.test, http://b.test", allowed_extensions="pdf, md")
    assert settings.cors_origins == ["http://a.test", "http://b.test"]
    assert settings.allowed_extensions == ["pdf", "md"]


def test_json_array_environment_values_still_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://a.test","http://b.test"]')
    assert Settings().cors_origins == ["http://a.test", "http://b.test"]


def test_csv_from_the_environment_is_split(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_EXTENSIONS", "pdf,txt")
    assert Settings().allowed_extensions == ["pdf", "txt"]


def test_derived_settings() -> None:
    settings = Settings(max_upload_mb=3, database_url="postgresql+asyncpg://u:p@h:5432/d")
    assert settings.max_upload_bytes == 3 * 1024 * 1024
    assert settings.sync_database_url == "postgresql://u:p@h:5432/d"
