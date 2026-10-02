"""Aggregates the v1 routers. Auth guards everything except /health."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1 import chat, conversations, documents, health
from app.core.security import require_api_key

api_router = APIRouter()

# /health must stay reachable without a key so orchestrators can probe it.
api_router.include_router(health.router)

guarded = APIRouter(dependencies=[Depends(require_api_key)])
guarded.include_router(documents.router)
guarded.include_router(conversations.router)
guarded.include_router(chat.router)

api_router.include_router(guarded)
