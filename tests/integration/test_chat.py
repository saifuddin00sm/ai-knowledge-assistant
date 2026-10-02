"""Chat: grounding, citation mapping, filters, history, and the SSE stream."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
import pytest

from app.services.llm.base import LLMMessage, LLMResponse, LLMStreamEvent, LLMUsage
from app.services.llm.fake import FakeLLMClient
from app.services.prompts import REFUSAL_PHRASE, REWRITE_SENTINEL

# Deliberately shares no vocabulary with the fixture documents, so retrieval
# returns nothing above the similarity floor and the API has to refuse.
UNANSWERABLE = "What is the vesting schedule for stock options?"
LEAVE_QUESTION = "How many days of paid annual leave do employees receive?"


async def test_answerable_question_is_grounded_and_cited(
    client: httpx.AsyncClient, leave_document: dict[str, Any]
) -> None:
    response = await client.post("/chat", json={"message": LEAVE_QUESTION})
    assert response.status_code == 200
    body = response.json()

    assert body["grounded"] is True
    assert body["sources"], "an answerable question should return sources"
    assert body["conversation_id"]
    assert body["message_id"]
    assert body["model"]
    assert body["timings"]["total_ms"] >= 0
    assert body["usage"]["input_tokens"] > 0


async def test_citations_map_onto_real_chunks(
    client: httpx.AsyncClient, leave_document: dict[str, Any]
) -> None:
    body = (await client.post("/chat", json={"message": LEAVE_QUESTION})).json()

    cited = {int(number) for number in _citation_numbers(body["answer"])}
    assert cited, "the fake provider always cites [1]"
    by_index = {source["index"]: source for source in body["sources"]}
    assert cited <= set(by_index), "every citation must have a matching source"

    detail = (await client.get(f"/documents/{leave_document['id']}")).json()
    real_chunk_indexes = {chunk["chunk_index"] for chunk in detail["chunks"]}
    for number in cited:
        source = by_index[number]
        assert source["document_id"] == leave_document["id"]
        assert source["chunk_index"] in real_chunk_indexes
        assert source["filename"] == "leave-policy.md"
        assert 0.0 <= source["score"] <= 1.0
        assert source["snippet"]


def _citation_numbers(answer: str) -> list[str]:
    import re

    return re.findall(r"\[(\d+)\]", answer)


async def test_unanswerable_question_is_refused(
    client: httpx.AsyncClient, leave_document: dict[str, Any]
) -> None:
    body = (await client.post("/chat", json={"message": UNANSWERABLE})).json()
    assert body["grounded"] is False
    assert body["answer"] == REFUSAL_PHRASE


async def test_chat_with_no_documents_at_all_refuses(client: httpx.AsyncClient) -> None:
    body = (await client.post("/chat", json={"message": LEAVE_QUESTION})).json()
    assert body["sources"] == []
    assert body["grounded"] is False
    assert body["answer"] == REFUSAL_PHRASE


async def test_document_filter_restricts_retrieval(
    client: httpx.AsyncClient,
    leave_document: dict[str, Any],
    pricing_document: dict[str, Any],
) -> None:
    body = (
        await client.post(
            "/chat",
            json={
                "message": "What does the Team plan cost per month?",
                "document_ids": [pricing_document["id"]],
            },
        )
    ).json()
    assert body["sources"]
    assert {source["document_id"] for source in body["sources"]} == {pricing_document["id"]}


async def test_min_score_of_one_filters_everything_out(
    client: httpx.AsyncClient, leave_document: dict[str, Any]
) -> None:
    body = (await client.post("/chat", json={"message": LEAVE_QUESTION, "min_score": 1.0})).json()
    assert body["sources"] == []
    assert body["grounded"] is False


async def test_top_k_caps_the_number_of_sources(
    client: httpx.AsyncClient,
    leave_document: dict[str, Any],
    pricing_document: dict[str, Any],
) -> None:
    body = (await client.post("/chat", json={"message": "leave and pricing", "top_k": 1})).json()
    assert len(body["sources"]) <= 1


async def test_empty_message_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post("/chat", json={"message": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_unknown_conversation_is_a_404(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/chat", json={"message": "hello", "conversation_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# -- conversations ---------------------------------------------------------


async def test_turns_accumulate_in_one_conversation(
    client: httpx.AsyncClient, leave_document: dict[str, Any]
) -> None:
    first = (await client.post("/chat", json={"message": LEAVE_QUESTION})).json()
    conversation_id = first["conversation_id"]

    second = (
        await client.post(
            "/chat",
            json={"message": "And the carry-over rule?", "conversation_id": conversation_id},
        )
    ).json()
    assert second["conversation_id"] == conversation_id

    history = (await client.get(f"/conversations/{conversation_id}/messages")).json()
    roles = [message["role"] for message in history["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert history["messages"][1]["sources"], "stored answers keep their sources"
    assert history["messages"][1]["usage"]["input_tokens"] > 0


async def test_created_conversation_can_be_used_and_deleted(client: httpx.AsyncClient) -> None:
    created = await client.post("/conversations", json={"title": "Onboarding"})
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    assert created.json()["title"] == "Onboarding"

    chat = await client.post("/chat", json={"message": "hello", "conversation_id": conversation_id})
    assert chat.status_code == 200

    assert (await client.delete(f"/conversations/{conversation_id}")).status_code == 204
    assert (await client.get(f"/conversations/{conversation_id}/messages")).status_code == 404


class RewritingLLM(FakeLLMClient):
    """Fake provider that performs a real rewrite, so the path is observable."""

    def __init__(self, rewrite: str) -> None:
        super().__init__(model="rewriting-fake")
        self._rewrite = rewrite
        self.rewrite_calls = 0

    async def complete(
        self, *, system: str, messages: Sequence[LLMMessage], max_tokens: int
    ) -> LLMResponse:
        if REWRITE_SENTINEL in system:
            self.rewrite_calls += 1
            return LLMResponse(text=self._rewrite, model=self.model, usage=LLMUsage(1, 1))
        return await super().complete(system=system, messages=messages, max_tokens=max_tokens)

    async def stream(
        self, *, system: str, messages: Sequence[LLMMessage], max_tokens: int
    ) -> AsyncIterator[LLMStreamEvent]:
        async for event in super().stream(system=system, messages=messages, max_tokens=max_tokens):
            yield event


@pytest.fixture
def rewriting_llm() -> RewritingLLM:
    from app.main import app
    from app.services.llm.factory import get_llm_client

    llm = RewritingLLM("What does the Lumen Team plan include in monthly ingest?")
    app.dependency_overrides[get_llm_client] = lambda: llm
    return llm


async def test_follow_up_is_rewritten_into_a_standalone_query(
    client: httpx.AsyncClient,
    pricing_document: dict[str, Any],
    rewriting_llm: RewritingLLM,
) -> None:
    first = (
        await client.post("/chat", json={"message": "What does the Team plan cost per month?"})
    ).json()
    assert first["rewritten_query"] is None, "a self-contained question is not rewritten"

    second = (
        await client.post(
            "/chat",
            json={
                "message": "How much ingest does it include?",
                "conversation_id": first["conversation_id"],
            },
        )
    ).json()

    assert rewriting_llm.rewrite_calls == 1
    assert second["rewritten_query"] == "What does the Lumen Team plan include in monthly ingest?"
    assert second["sources"], "the rewritten query still retrieves the pricing document"
    assert {source["document_id"] for source in second["sources"]} == {pricing_document["id"]}


# -- streaming -------------------------------------------------------------


def parse_sse(raw: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    name = ""
    for line in raw.splitlines():
        if line.startswith("event: "):
            name = line.removeprefix("event: ").strip()
        elif line.startswith("data: "):
            events.append((name, json.loads(line.removeprefix("data: "))))
    return events


async def test_stream_emits_start_tokens_sources_done(
    client: httpx.AsyncClient, leave_document: dict[str, Any]
) -> None:
    response = await client.post("/chat/stream", json={"message": LEAVE_QUESTION})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "start"
    assert names[-1] == "done"
    assert "token" in names
    assert names.count("sources") == 1
    assert names.index("sources") == len(names) - 2

    start = events[0][1]
    assert start["conversation_id"]
    assert start["retrieval_ms"] >= 0

    streamed = "".join(data["text"] for name, data in events if name == "token")
    final = next(data for name, data in events if name == "sources")
    assert streamed.strip() == final["answer"]
    assert final["grounded"] is True
    assert final["sources"]
    assert final["message_id"]
    assert final["usage"]["output_tokens"] > 0


async def test_streamed_answer_is_persisted_with_its_sources(
    client: httpx.AsyncClient, leave_document: dict[str, Any]
) -> None:
    response = await client.post("/chat/stream", json={"message": LEAVE_QUESTION})
    final = next(data for name, data in parse_sse(response.text) if name == "sources")

    history = (await client.get(f"/conversations/{final['conversation_id']}/messages")).json()
    assistant = [m for m in history["messages"] if m["role"] == "assistant"]
    assert len(assistant) == 1
    assert assistant[0]["id"] == final["message_id"]
    assert assistant[0]["content"] == final["answer"]
    assert len(assistant[0]["sources"]) == len(final["sources"])


async def test_stream_refuses_an_unanswerable_question(
    client: httpx.AsyncClient, leave_document: dict[str, Any]
) -> None:
    response = await client.post("/chat/stream", json={"message": UNANSWERABLE})
    final = next(data for name, data in parse_sse(response.text) if name == "sources")
    assert final["grounded"] is False
    assert final["answer"] == REFUSAL_PHRASE


async def test_stream_rejects_an_unknown_conversation_with_a_404(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/chat/stream", json={"message": "hi", "conversation_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
