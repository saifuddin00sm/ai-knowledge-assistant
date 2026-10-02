"""End-to-end smoke test against a running API.

Asks one answerable question, one deliberately unanswerable question, and one
follow-up that only resolves via conversation history. Also exercises the SSE
endpoint. Prints what it got; exits non-zero if the expected shape is missing.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import httpx

from scripts._client import explain_error, make_client, require_api

ANSWERABLE = "How many days of paid annual leave do employees get?"
UNANSWERABLE = "What is Northwind Labs' policy on company-provided pet insurance?"
FOLLOW_UP_FIRST = "What does the Lumen Team plan cost?"
FOLLOW_UP_SECOND = "How much ingest does it include?"


def ask(client: httpx.Client, message: str, conversation_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"message": message}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    response = client.post("/chat", json=payload)
    if response.status_code != 200:
        sys.exit(f"chat failed: {explain_error(response)}")
    body: dict[str, Any] = response.json()
    return body


def show(label: str, result: dict[str, Any]) -> None:
    print(f"\n--- {label} ---")
    print(f"grounded : {result['grounded']}")
    if result.get("rewritten_query"):
        print(f"rewritten: {result['rewritten_query']}")
    print(f"answer   : {result['answer']}")
    for source in result["sources"]:
        page = f" p.{source['page']}" if source["page"] is not None else ""
        print(
            f"  [{source['index']}] {source['filename']}{page} "
            f"chunk={source['chunk_index']} score={source['score']}"
        )
    print(
        f"timings  : retrieval={result['timings']['retrieval_ms']}ms "
        f"generation={result['timings']['generation_ms']}ms"
    )


def stream_once(client: httpx.Client, message: str) -> bool:
    print(f"\n--- streaming: {message} ---")
    tokens: list[str] = []
    saw_sources = False
    saw_done = False
    with client.stream("POST", "/chat/stream", json={"message": message}) as response:
        if response.status_code != 200:
            response.read()
            print(f"stream failed: {explain_error(response)}")
            return False
        event = ""
        for line in response.iter_lines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ").strip()
            elif line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
                if event == "token":
                    tokens.append(data["text"])
                elif event == "sources":
                    saw_sources = True
                    print("".join(tokens).strip())
                    print(f"  message_id={data['message_id']} grounded={data['grounded']}")
                    print(f"  sources={len(data['sources'])}")
                elif event == "done":
                    saw_done = True
                elif event == "error":
                    print(f"  stream error: {data}")
    print(f"  tokens={len(tokens)} sources_event={saw_sources} done_event={saw_done}")
    return bool(tokens) and saw_sources and saw_done


def main() -> int:
    failures: list[str] = []
    with make_client() as client:
        health = require_api(client)
        print(
            f"API ok - llm={health.get('llm_provider')} "
            f"embeddings={health.get('embedding_provider')}"
        )

        answerable = ask(client, ANSWERABLE)
        show("answerable", answerable)
        if not answerable["grounded"] or not answerable["sources"]:
            failures.append("answerable question was not grounded")

        unanswerable = ask(client, UNANSWERABLE)
        show("unanswerable", unanswerable)
        if unanswerable["grounded"]:
            failures.append("unanswerable question was reported as grounded")

        first = ask(client, FOLLOW_UP_FIRST)
        show("follow-up turn 1", first)
        second = ask(client, FOLLOW_UP_SECOND, conversation_id=first["conversation_id"])
        show("follow-up turn 2", second)
        if second["conversation_id"] != first["conversation_id"]:
            failures.append("follow-up did not reuse the conversation")

        if not stream_once(client, ANSWERABLE):
            failures.append("SSE stream did not produce tokens + sources + done")

    print()
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
