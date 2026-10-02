"""Evaluate retrieval and refusal behaviour against evals/dataset.jsonl.

Reports three numbers, all computed from this repository's own dataset against
a running API:

  retrieval hit rate @k  - share of answerable questions where the expected
                           document appears among the returned sources.
  refusal correctness    - share of unanswerable questions the API declines.
  false refusal rate     - share of answerable questions the API declines
                           (the cost of the refusal behaviour).

Nothing here is a benchmark against other systems; the numbers describe this
dataset, this corpus, and the providers configured at run time. Both are
recorded in the report header.

Usage:
    make eval        # or: uv run python -m evals.run_eval
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from scripts._client import explain_error, make_client, require_api

EVAL_DIR = Path(__file__).resolve().parent
DATASET_PATH = EVAL_DIR / "dataset.jsonl"
REPORT_DIR = EVAL_DIR / "reports"


@dataclass(slots=True)
class Case:
    id: str
    question: str
    answerable: bool
    expected_document: str | None


@dataclass(slots=True)
class CaseResult:
    id: str
    question: str
    answerable: bool
    expected_document: str | None
    retrieved_documents: list[str]
    hit: bool | None
    """True/False for answerable cases; None for unanswerable ones."""
    grounded: bool
    refused_correctly: bool | None
    top_score: float | None
    answer: str
    retrieval_ms: int
    generation_ms: int


def load_cases(path: Path = DATASET_PATH) -> list[Case]:
    cases: list[Case] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{number}: invalid JSON - {exc}") from exc
        cases.append(
            Case(
                id=record["id"],
                question=record["question"],
                answerable=bool(record["answerable"]),
                expected_document=record.get("expected_document"),
            )
        )
    return cases


def evaluate_case(client: httpx.Client, case: Case) -> CaseResult:
    response = client.post("/chat", json={"message": case.question})
    if response.status_code != 200:
        raise SystemExit(f"chat failed for {case.id}: {explain_error(response)}")
    body: dict[str, Any] = response.json()

    documents = [source["filename"] for source in body["sources"]]
    hit = (case.expected_document in documents) if case.answerable else None
    refused_correctly = (not body["grounded"]) if not case.answerable else None

    return CaseResult(
        id=case.id,
        question=case.question,
        answerable=case.answerable,
        expected_document=case.expected_document,
        retrieved_documents=documents,
        hit=hit,
        grounded=bool(body["grounded"]),
        refused_correctly=refused_correctly,
        top_score=body["sources"][0]["score"] if body["sources"] else None,
        answer=body["answer"],
        retrieval_ms=body["timings"]["retrieval_ms"],
        generation_ms=body["timings"]["generation_ms"],
    )


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    answerable = [result for result in results if result.answerable]
    unanswerable = [result for result in results if not result.answerable]
    hits = sum(1 for result in answerable if result.hit)
    correct_refusals = sum(1 for result in unanswerable if result.refused_correctly)
    false_refusals = sum(1 for result in answerable if not result.grounded)

    def ratio(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 3) if denominator else None

    return {
        "cases": len(results),
        "answerable_cases": len(answerable),
        "unanswerable_cases": len(unanswerable),
        "retrieval_hits": hits,
        "retrieval_hit_rate": ratio(hits, len(answerable)),
        "correct_refusals": correct_refusals,
        "refusal_correctness": ratio(correct_refusals, len(unanswerable)),
        "false_refusals": false_refusals,
        "false_refusal_rate": ratio(false_refusals, len(answerable)),
        "median_retrieval_ms": _median([r.retrieval_ms for r in results]),
        "median_generation_ms": _median([r.generation_ms for r in results]),
    }


def _median(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) // 2


def render_markdown(
    header: dict[str, Any], summary: dict[str, Any], results: list[CaseResult]
) -> str:
    lines = [
        "# Evaluation report",
        "",
        f"- **Run at:** {header['run_at']}",
        f"- **Dataset:** `evals/dataset.jsonl` ({summary['cases']} questions: "
        f"{summary['answerable_cases']} answerable, {summary['unanswerable_cases']} unanswerable)",
        "- **Corpus:** `sample_docs/`",
        f"- **LLM provider / model:** {header['llm_provider']} / {header['llm_model']}",
        f"- **Embedding provider / model:** {header['embedding_provider']} / "
        f"{header['embedding_model']}",
        f"- **Chunking:** {header['chunk_size_tokens']} tokens / "
        f"{header['chunk_overlap_tokens']} overlap",
        f"- **Retrieval:** top_k={header['top_k']}, min_score={header['min_score']}, "
        f"hybrid={header['hybrid_search_enabled']}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Retrieval hit rate @{header['top_k']} | "
        f"{_pct(summary['retrieval_hit_rate'])} "
        f"({summary['retrieval_hits']}/{summary['answerable_cases']}) |",
        f"| Refusal correctness (unanswerable) | "
        f"{_pct(summary['refusal_correctness'])} "
        f"({summary['correct_refusals']}/{summary['unanswerable_cases']}) |",
        f"| False refusal rate (answerable) | "
        f"{_pct(summary['false_refusal_rate'])} "
        f"({summary['false_refusals']}/{summary['answerable_cases']}) |",
        f"| Median retrieval latency | {summary['median_retrieval_ms']} ms |",
        f"| Median generation latency | {summary['median_generation_ms']} ms |",
        "",
        "## Per-question results",
        "",
        "| # | Question | Expected | Retrieved | Hit | Grounded | Top score |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for position, result in enumerate(results, start=1):
        retrieved = ", ".join(dict.fromkeys(result.retrieved_documents)) or "—"
        hit = "—" if result.hit is None else ("yes" if result.hit else "no")
        score = "—" if result.top_score is None else f"{result.top_score:.3f}"
        lines.append(
            f"| {position} | {result.question} | {result.expected_document or '— (unanswerable)'} "
            f"| {retrieved} | {hit} | {'yes' if result.grounded else 'no'} | {score} |"
        )
    lines.append("")
    return "\n".join(lines)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def main() -> int:
    cases = load_cases()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    with make_client() as client:
        health = require_api(client)
        retrieval = _retrieval_settings()
        print(
            f"Evaluating {len(cases)} questions against "
            f"llm={health.get('llm_provider')} embeddings={health.get('embedding_provider')}"
        )
        results = []
        for case in cases:
            result = evaluate_case(client, case)
            results.append(result)
            marker = {True: "hit", False: "miss", None: "-"}[result.hit]
            print(f"  {case.id}: grounded={result.grounded} retrieval={marker}")

    summary = summarize(results)
    header = {
        "run_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        # Providers and models are what the API reported about itself.
        "llm_provider": health.get("llm_provider"),
        "llm_model": health.get("llm_model", "unknown"),
        "embedding_provider": health.get("embedding_provider"),
        "embedding_model": health.get("embedding_model", "unknown"),
        **retrieval,
    }

    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = REPORT_DIR / f"eval-{stamp}.json"
    markdown_path = REPORT_DIR / f"eval-{stamp}.md"
    json_path.write_text(
        json.dumps(
            {
                "header": header,
                "summary": summary,
                "results": [asdict(result) for result in results],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(header, summary, results), encoding="utf-8")

    print()
    print(f"retrieval hit rate   : {_pct(summary['retrieval_hit_rate'])}")
    print(f"refusal correctness  : {_pct(summary['refusal_correctness'])}")
    print(f"false refusal rate   : {_pct(summary['false_refusal_rate'])}")
    print(f"reports              : {json_path.name}, {markdown_path.name}")
    return 0


def _retrieval_settings() -> dict[str, Any]:
    """Retrieval knobs as this process sees them.

    Read from the app's own Settings so the defaults can never drift from the
    service. This assumes the API was started with the same environment - which
    is the case for `make up && make eval`. The provider and model names in the
    report are observed from `/health` rather than guessed from here.
    """
    from app.core.config import Settings

    settings = Settings()
    return {
        "top_k": settings.retrieval_top_k,
        "min_score": settings.retrieval_min_score,
        "hybrid_search_enabled": settings.hybrid_search_enabled,
        "chunk_size_tokens": settings.chunk_size_tokens,
        "chunk_overlap_tokens": settings.chunk_overlap_tokens,
    }


if __name__ == "__main__":
    sys.exit(main())
