"""FastAPI dependencies. Wiring lives here so routes stay thin."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db, get_session_factory
from app.services.conversation import ConversationService
from app.services.embeddings.base import Embedder
from app.services.embeddings.factory import get_embedder
from app.services.generation import AnswerGenerator
from app.services.ingestion.pipeline import IngestionPipeline
from app.services.llm.base import LLMClient
from app.services.llm.factory import get_llm_client
from app.services.retrieval import Retriever

SessionDep = Annotated[AsyncSession, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
LLMDep = Annotated[LLMClient, Depends(get_llm_client)]


def build_answer_generator(
    session: AsyncSession,
    embedder: Embedder,
    llm: LLMClient,
    settings: Settings,
) -> AnswerGenerator:
    """Compose the chat services over one session.

    Used both by the request-scoped dependency below and by `/chat/stream`,
    which has to own its session for the lifetime of the SSE body.
    """
    return AnswerGenerator(
        Retriever(session, embedder, settings),
        llm,
        ConversationService(session, llm, settings),
        settings,
    )


def get_conversation_service(
    session: SessionDep, llm: LLMDep, settings: SettingsDep
) -> ConversationService:
    return ConversationService(session, llm, settings)


def get_retriever(session: SessionDep, embedder: EmbedderDep, settings: SettingsDep) -> Retriever:
    return Retriever(session, embedder, settings)


def get_answer_generator(
    session: SessionDep,
    embedder: EmbedderDep,
    llm: LLMDep,
    settings: SettingsDep,
) -> AnswerGenerator:
    return build_answer_generator(session, embedder, llm, settings)


def get_ingestion_pipeline(embedder: EmbedderDep, settings: SettingsDep) -> IngestionPipeline:
    # The pipeline opens its own sessions: it outlives the upload request.
    return IngestionPipeline(get_session_factory(), embedder, settings)


ConversationServiceDep = Annotated[ConversationService, Depends(get_conversation_service)]
RetrieverDep = Annotated[Retriever, Depends(get_retriever)]
AnswerGeneratorDep = Annotated[AnswerGenerator, Depends(get_answer_generator)]
IngestionPipelineDep = Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)]
