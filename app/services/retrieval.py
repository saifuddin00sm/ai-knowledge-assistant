"""Retrieval: cosine similarity over pgvector, optionally fused with Postgres FTS."""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.models import Chunk, Document, DocumentStatus
from app.services.embeddings.base import Embedder

logger = get_logger(__name__)


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page: int | None
    chunk_index: int
    content: str
    token_count: int
    score: float
    """Cosine similarity in [0, 1]. 1.0 means identical direction."""


@dataclass(slots=True)
class RetrievalResult:
    chunks: list[RetrievedChunk]
    query: str
    strategy: str
    latency_ms: int


def _row_to_chunk(row: Any) -> RetrievedChunk:
    # pgvector's cosine distance is 1 - cosine similarity.
    similarity = 1.0 - float(row.distance)
    return RetrievedChunk(
        chunk_id=row.id,
        document_id=row.document_id,
        filename=row.filename,
        page=row.page,
        chunk_index=row.chunk_index,
        content=row.content,
        token_count=row.token_count,
        score=max(0.0, min(1.0, similarity)),
    )


class Retriever:
    """Reads chunks for a query. Owns no state beyond its session and config."""

    def __init__(
        self,
        session: AsyncSession,
        embedder: Embedder,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._embedder = embedder
        self._settings = settings or get_settings()

    def _base_select(
        self, query_vector: Sequence[float], document_ids: Sequence[uuid.UUID] | None
    ) -> Select[Any]:
        distance = Chunk.embedding.cosine_distance(list(query_vector)).label("distance")
        statement = (
            select(
                Chunk.id,
                Chunk.document_id,
                Chunk.chunk_index,
                Chunk.page,
                Chunk.content,
                Chunk.token_count,
                Document.filename,
                distance,
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.status == DocumentStatus.READY.value)
        )
        if document_ids:
            statement = statement.where(Chunk.document_id.in_(list(document_ids)))
        return statement

    async def _vector_candidates(
        self,
        query_vector: Sequence[float],
        limit: int,
        document_ids: Sequence[uuid.UUID] | None,
    ) -> list[RetrievedChunk]:
        statement = (
            self._base_select(query_vector, document_ids)
            .order_by(Chunk.embedding.cosine_distance(list(query_vector)))
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [_row_to_chunk(row) for row in rows]

    async def _keyword_candidates(
        self,
        query: str,
        query_vector: Sequence[float],
        limit: int,
        document_ids: Sequence[uuid.UUID] | None,
    ) -> list[RetrievedChunk]:
        tsquery = func.plainto_tsquery("english", query)
        statement = (
            self._base_select(query_vector, document_ids)
            .where(Chunk.content_tsv.op("@@")(tsquery))
            .order_by(func.ts_rank_cd(Chunk.content_tsv, tsquery).desc())
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [_row_to_chunk(row) for row in rows]

    @staticmethod
    def _reciprocal_rank_fusion(
        ranked_lists: Sequence[Sequence[RetrievedChunk]], k: int
    ) -> list[RetrievedChunk]:
        """Standard RRF: score(d) = sum over lists of 1 / (k + rank(d))."""
        scores: dict[uuid.UUID, float] = {}
        by_id: dict[uuid.UUID, RetrievedChunk] = {}
        for ranked in ranked_lists:
            for rank, chunk in enumerate(ranked, start=1):
                scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
                by_id.setdefault(chunk.chunk_id, chunk)
        ordered = sorted(
            by_id.values(),
            key=lambda chunk: (scores[chunk.chunk_id], chunk.score),
            reverse=True,
        )
        return ordered

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        min_score: float | None = None,
        document_ids: Sequence[uuid.UUID] | None = None,
    ) -> RetrievalResult:
        settings = self._settings
        limit = top_k or settings.retrieval_top_k
        threshold = settings.retrieval_min_score if min_score is None else min_score
        started = time.perf_counter()

        query_vector = await self._embedder.embed_query(query)

        if settings.hybrid_search_enabled:
            candidate_limit = max(limit, limit * settings.hybrid_candidate_multiplier)
            vector_hits = await self._vector_candidates(query_vector, candidate_limit, document_ids)
            # The score threshold gates the vector list only; keyword hits are
            # kept on lexical merit and still report their true cosine score.
            vector_hits = [hit for hit in vector_hits if hit.score >= threshold]
            keyword_hits = await self._keyword_candidates(
                query, query_vector, candidate_limit, document_ids
            )
            chunks = self._reciprocal_rank_fusion(
                [vector_hits, keyword_hits], settings.hybrid_rrf_k
            )[:limit]
            strategy = "hybrid_rrf"
        else:
            hits = await self._vector_candidates(query_vector, limit, document_ids)
            chunks = [hit for hit in hits if hit.score >= threshold]
            strategy = "vector"

        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "retrieval_complete",
            extra={
                "strategy": strategy,
                "top_k": limit,
                "min_score": threshold,
                "returned": len(chunks),
                "retrieval_latency_ms": latency_ms,
                "document_filter": len(document_ids) if document_ids else 0,
            },
        )
        return RetrievalResult(chunks=chunks, query=query, strategy=strategy, latency_ms=latency_ms)
