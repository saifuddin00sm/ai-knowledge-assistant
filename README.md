# AI Knowledge Assistant

A document-grounded question answering API. You upload PDF, DOCX, TXT or MD
files; they are parsed, split into token-aware overlapping chunks, embedded, and
stored in PostgreSQL with pgvector. A question is embedded and matched against
those chunks by cosine similarity, the best chunks are assembled into a
token-budgeted context, and the model is instructed to answer **only** from that
context and cite excerpts inline as `[1]`, `[2]`. When the retrieved context does
not support an answer, the API says so instead of guessing. Follow-up questions
are rewritten into standalone queries before retrieval, so conversation history
is used for retrieval and not just for prompt padding. Answers are available as
one JSON response or as a Server-Sent Events stream that ends with a `sources`
event. The LLM and embedding providers sit behind interfaces and are selected by
environment variable; the defaults need no API key, so the whole thing runs,
tests and evaluates offline.

```
docker compose up -d        # Postgres + API, migrations applied on start
make seed                   # ingest sample_docs/
make smoke                  # ask one answerable and one unanswerable question
```

- **Stack:** Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 (async) · Alembic ·
  PostgreSQL 16 + pgvector · uv · Ruff · mypy (strict) · pytest
- **Interactive docs:** <http://localhost:8000/docs>

---

## Contents

- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Frontend integration](#frontend-integration)
- [Project layout](#project-layout)
- [Development](#development)
- [Evaluation results](#evaluation-results)
- [Design decisions](#design-decisions)
- [Limitations and next steps](#limitations-and-next-steps)

---

## Architecture

### Ingestion flow

```mermaid
flowchart TD
    A["POST /api/v1/documents<br/>multipart upload"] --> B{"Validate<br/>type and size"}
    B -- "rejected" --> B1["4xx<br/>415 / 413 / 422"]
    B -- "ok" --> C{"SHA-256 content hash<br/>already seen?"}
    C -- "yes, already ready" --> C1["200 + existing document"]
    C -- "yes, never finished" --> D
    C -- "no" --> D["Insert document<br/>status = pending"]
    D --> E["201 + document id<br/>response returns now"]
    D -. "FastAPI background task" .-> F["status = processing"]
    F --> G["Parse<br/>PyMuPDF / python-docx / text<br/>page numbers preserved"]
    G --> H["Chunk<br/>recursive, token-aware<br/>headings then paragraphs"]
    H --> I["Embed in batches<br/>retry with exponential backoff"]
    I --> J[("chunks<br/>embedding vector(1536)<br/>+ generated tsvector")]
    J --> K["status = ready<br/>chunk_count, page_count"]
    G -- "unreadable / empty" --> L["status = failed<br/>error_message stored"]
    I -- "provider failure" --> L
```

### Query flow

```mermaid
flowchart TD
    A["POST /api/v1/chat<br/>or /chat/stream"] --> B["Load conversation<br/>last N turns, token-trimmed"]
    B --> C{"Looks like<br/>a follow-up?"}
    C -- "yes" --> D["Rewrite into a<br/>standalone query (LLM)"]
    C -- "no" --> E
    D --> E["Embed the query"]
    E --> F["Cosine search over pgvector<br/>HNSW, top_k, min_score"]
    F -- "HYBRID_SEARCH_ENABLED" --> G["Postgres full-text search<br/>fused with vector by RRF"]
    F --> H["Select context<br/>best first, within token budget"]
    G --> H
    H --> I["Build grounded prompt<br/>numbered excerpts + citation rules"]
    I --> J["Generate<br/>Anthropic or offline fake"]
    J --> K["Sanitise citations<br/>drop markers with no source"]
    K --> L[("Persist message<br/>+ sources + token usage")]
    L --> M["Answer + sources[]<br/>+ grounded + timings"]
    H -- "nothing above min_score" --> N["Refuse:<br/>documents do not contain it"]
```

The three layers a reviewer usually wants to find first:

| Concern | Where |
| --- | --- |
| Ingestion | `app/services/ingestion/` — `parsers.py`, `chunker.py`, `pipeline.py` |
| Retrieval | `app/services/retrieval.py` |
| Generation | `app/services/generation.py` + `app/services/prompts.py` |

---

## Quick start

### With Docker (recommended)

```bash
cp .env.example .env          # optional: every value is already the default
docker compose up -d --build  # Postgres 16 + pgvector, API on :8000
make seed                     # ingest the three documents in sample_docs/
```

The API container waits for Postgres, runs `alembic upgrade head`, then starts
uvicorn — there is no separate migration step. `docker compose logs -f api`
follows structured JSON logs.

Published ports: API `8000`, Postgres `55432` (55432 rather than 5432 so the
container never collides with a PostgreSQL already installed on the host).

### Without Docker

```bash
uv sync                                   # create .venv and install
docker compose up -d db                   # or point DATABASE_URL at your own Postgres
make migrate                              # alembic upgrade head
make dev                                  # uvicorn with autoreload
```

Postgres must have the `vector` extension available (the migration runs
`CREATE EXTENSION IF NOT EXISTS vector`); the `pgvector/pgvector:pg16` image in
`docker-compose.yml` has it.

### Using real providers

The defaults are deliberately key-free. To get real answers:

```bash
# in .env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-opus-5

EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
OPENAI_API_KEY=sk-...
```

Then recreate the stack and re-ingest: changing the embedding provider changes
the vector space, so existing chunks must be re-embedded.

```bash
docker compose down -v && docker compose up -d --build && make seed
```

`EMBEDDING_DIM` must match the vector column width (1536). Switching to a model
with a different dimensionality needs a new migration.

---

## Configuration

Everything is an environment variable; see `.env.example` for the annotated
version. No secret is ever read from anywhere but the environment.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://rag:rag@localhost:55432/rag` | Async Postgres DSN. Compose overrides the host to `db`. |
| `APP_ENV` | `local` | `local` / `test` / `production`. |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / `true` | Structured JSON logs with request id and latencies. |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated or a JSON array. |
| `API_KEY` | *(empty)* | When set, every `/api/v1` route except `/health` requires `X-API-Key`. |
| `MAX_UPLOAD_MB` | `20` | Upload size limit; over it is a 413. |
| `ALLOWED_EXTENSIONS` | `pdf,docx,txt,md` | Anything else is a 415. |
| `CHUNK_SIZE_TOKENS` | `600` | Max tokens per chunk. |
| `CHUNK_OVERLAP_TOKENS` | `100` | Token overlap between adjacent chunks. |
| `EMBEDDING_PROVIDER` | `hashing` | `hashing` (offline, lexical) or `openai` (semantic). |
| `EMBEDDING_MODEL` | `local-hashing-v1` | e.g. `text-embedding-3-small` for OpenAI. |
| `EMBEDDING_DIM` | `1536` | Must match the `vector(n)` column. |
| `EMBEDDING_BATCH_SIZE` | `64` | Texts per provider call. |
| `EMBEDDING_MAX_RETRIES` | `5` | Retries on rate limits / transient errors. |
| `LLM_PROVIDER` | `fake` | `fake` (offline stub) or `anthropic`. |
| `LLM_MODEL` | `claude-opus-5` | Used when `LLM_PROVIDER=anthropic`. |
| `LLM_MAX_TOKENS` | `4096` | Output cap per answer. |
| `LLM_EFFORT` | `low` | Anthropic `output_config.effort`: `low`…`max`. |
| `LLM_THINKING` | `adaptive` | `adaptive` or `disabled` (rejected above `high` effort). |
| `RETRIEVAL_TOP_K` | `5` | Chunks retrieved per question. |
| `RETRIEVAL_MIN_SCORE` | `0.15` | Cosine-similarity floor. Below it, a chunk is dropped — this is the dial that turns an off-topic question into a refusal. |
| `CONTEXT_TOKEN_BUDGET` | `3000` | Token budget for assembled context. |
| `HYBRID_SEARCH_ENABLED` | `false` | Fuse vector + Postgres full-text results with RRF. |
| `HYBRID_RRF_K` | `60` | RRF constant. |
| `HISTORY_TURNS` | `4` | Conversation turns included in the prompt. |
| `HISTORY_TOKEN_BUDGET` | `800` | Token budget for that history. |
| `QUERY_REWRITE_ENABLED` | `true` | Rewrite follow-ups into standalone queries. |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | *(empty)* | Provider credentials. |
| `TEST_DATABASE_URL` | *(empty)* | Integration tests are skipped unless set. |

---

## API reference

Base path `/api/v1`. Every non-2xx response is:

```json
{ "error": { "code": "not_found", "message": "Document 7a1f… not found." } }
```

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | App + database health, active providers and models. Never requires a key. |
| `POST` | `/documents` | Upload a document (multipart). 201 new, 200 if the same bytes were already ingested. |
| `GET` | `/documents` | List documents with status (`limit`, `offset`). |
| `GET` | `/documents/{id}` | Document detail plus per-chunk metadata. |
| `DELETE` | `/documents/{id}` | Delete the document and its chunks. |
| `POST` | `/conversations` | Create an empty conversation. |
| `GET` | `/conversations/{id}/messages` | Message history with the sources cited by each answer. |
| `DELETE` | `/conversations/{id}` | Delete a conversation and its messages. |
| `POST` | `/chat` | Grounded answer as one JSON response. |
| `POST` | `/chat/stream` | The same answer as Server-Sent Events. |

Add `-H "X-API-Key: $API_KEY"` to every example below when the server was
started with `API_KEY` set.

### Health

```bash
curl -s http://localhost:8000/api/v1/health
```

```json
{
  "status": "ok",
  "version": "0.1.0",
  "database": "ok",
  "llm_provider": "fake",
  "llm_model": "fake-deterministic-v1",
  "embedding_provider": "hashing",
  "embedding_model": "local-hashing-v1"
}
```

### Upload a document

```bash
curl -s -X POST http://localhost:8000/api/v1/documents \
  -F "file=@sample_docs/employee-handbook.md"
```

```json
{
  "id": "93f7826e-9023-4f5f-8771-d76ecdf02ba8",
  "filename": "employee-handbook.md",
  "extension": "md",
  "size_bytes": 3696,
  "status": "pending",
  "chunk_count": 0,
  "page_count": null,
  "error_message": null,
  "created_at": "2026-10-02T10:43:01Z",
  "updated_at": "2026-10-02T10:43:01Z"
}
```

Ingestion happens in a background task. Poll until the status is terminal:

```bash
curl -s http://localhost:8000/api/v1/documents/93f7826e-9023-4f5f-8771-d76ecdf02ba8
# status: pending -> processing -> ready | failed
```

On `failed`, `error_message` carries the reason (unreadable file, provider
failure). Re-uploading the same file requeues a document that never reached
`ready`.

### Ask a question

```bash
curl -s -X POST http://localhost:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "How many days of paid annual leave do employees get?"}'
```

```json
{
  "conversation_id": "d3f4a718-18f5-4b57-bd3f-b603566d2ef1",
  "message_id": "83767878-e518-41d4-be99-12375163f419",
  "answer": "Every full-time employee receives **28 days of paid annual leave** per calendar\nyear, in addition to public holidays in their country of residence. [1]",
  "sources": [
    {
      "index": 1,
      "document_id": "93f7826e-9023-4f5f-8771-d76ecdf02ba8",
      "filename": "employee-handbook.md",
      "page": null,
      "chunk_index": 0,
      "snippet": "# Northwind Labs — Employee Handbook … ## 1. Working hours and core overlap …",
      "score": 0.1709
    }
  ],
  "grounded": true,
  "rewritten_query": null,
  "model": "fake-deterministic-v1",
  "usage": { "input_tokens": 807, "output_tokens": 37 },
  "timings": { "retrieval_ms": 3, "generation_ms": 0, "total_ms": 34 }
}
```

`[1]` in `answer` is `sources[0]`. Markers that do not map to a returned source
are stripped before the answer is persisted, so a citation can never point at
nothing.

Useful request fields: `conversation_id` (omit to start a new conversation),
`document_ids` (restrict retrieval), `top_k`, `min_score`.

An unanswerable question:

```bash
curl -s -X POST http://localhost:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "What is the stock option vesting schedule?"}'
```

```json
{
  "answer": "The provided documents don't contain the answer to that question.",
  "sources": [],
  "grounded": false
}
```

### Follow-up questions

Pass the `conversation_id` back. A short, referential message is rewritten into a
standalone query before retrieval, and the rewrite is reported in
`rewritten_query`:

```bash
curl -s -X POST http://localhost:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "How much ingest does it include?",
       "conversation_id": "d3f4a718-18f5-4b57-bd3f-b603566d2ef1"}'
```

```json
{ "rewritten_query": "What does the Lumen Team plan include in monthly ingest?" }
```

> Rewriting needs a real model. With the default `LLM_PROVIDER=fake` the stub
> echoes the question back unchanged, which counts as "no rewrite", so
> `rewritten_query` is `null`. The response above is the shape produced with
> `LLM_PROVIDER=anthropic`; the same path is asserted end to end in
> `tests/integration/test_chat.py` with a stub that does rewrite.

### Streaming (SSE)

```bash
curl -sN -X POST http://localhost:8000/api/v1/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message": "What is the one-time home office budget?"}'
```

```
event: start
data: {"conversation_id":"d4d994c0-5a4d-4524-b54c-cb96d4fa9ae6","rewritten_query":null,"retrieval_ms":3}

event: token
data: {"text":"On"}

event: token
data: {"text":" top"}

event: sources
data: {"conversation_id":"1ef9b5f6-…","message_id":"9d168c9e-…","answer":"On top of that, there is a one-time home office\nbudget of **EUR 1,200**, which can be spent on a desk, chair, monitor, lighting,\nor anything else that improves the workspace. [1]","grounded":true,"sources":[{"index":1,"document_id":"93f7826e-…","filename":"employee-handbook.md","page":null,"chunk_index":0,"snippet":"# Northwind Labs — Employee Handbook …","score":0.2387}],"usage":{"input_tokens":804,"output_tokens":44},"timings":{"retrieval_ms":11,"generation_ms":6,"total_ms":71}}

event: done
data: {}
```

Event contract:

| Event | When | Payload |
| --- | --- | --- |
| `start` | once, after retrieval | `conversation_id`, `rewritten_query`, `retrieval_ms` |
| `token` | repeatedly | `text` — concatenate to build the answer |
| `sources` | once, before `done` | `conversation_id`, `message_id`, `answer` (final, citation-sanitised), `grounded`, `sources`, `usage`, `timings` |
| `done` | once, last | `{}` |
| `error` | instead of `token`/`sources`/`done` | `{"error": {"code", "message"}}` |

The HTTP status is 200 as soon as the stream opens, so a failure during
generation arrives as an `error` event rather than an error status. A bad
`conversation_id` is validated before the stream opens and is a real 404.

---

## Frontend integration

CORS origins come from `CORS_ORIGINS`. The response shapes above are the
contract; `openapi.json` can generate client types (`npx openapi-typescript
http://localhost:8000/openapi.json -o src/lib/api.d.ts`).

Consuming the SSE stream with `fetch` (not `EventSource`, which cannot POST):

```ts
export type Source = {
  index: number;
  document_id: string;
  filename: string;
  page: number | null;
  chunk_index: number;
  snippet: string;
  score: number;
};

export type StreamResult = {
  conversationId: string;
  messageId: string;
  answer: string;
  grounded: boolean;
  sources: Source[];
};

export async function streamChat(
  message: string,
  conversationId: string | null,
  onToken: (text: string) => void,
  signal?: AbortSignal,
): Promise<StreamResult> {
  const response = await fetch("http://localhost:8000/api/v1/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      // ...(apiKey ? { "X-API-Key": apiKey } : {}),
    },
    body: JSON.stringify({ message, conversation_id: conversationId }),
    signal,
  });

  if (!response.ok || !response.body) {
    const { error } = await response.json().catch(() => ({ error: null }));
    throw new Error(error?.message ?? `Request failed: ${response.status}`);
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  let result: StreamResult | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;

    // SSE frames are separated by a blank line; keep any partial tail.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      let event = "message";
      let data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      const payload = JSON.parse(data);

      if (event === "token") {
        onToken(payload.text);
      } else if (event === "sources") {
        result = {
          conversationId: payload.conversation_id,
          messageId: payload.message_id,
          answer: payload.answer,
          grounded: payload.grounded,
          sources: payload.sources,
        };
      } else if (event === "error") {
        throw new Error(payload.error.message);
      }
    }
  }

  if (!result) throw new Error("Stream ended without a sources event");
  return result;
}
```

Two things worth handling in the UI: render `onToken` text optimistically but
replace it with `result.answer` when the `sources` event arrives (that is the
citation-sanitised text), and show a distinct state when `grounded` is `false`
— the answer is a refusal, not a result.

---

## Project layout

```
app/
  main.py                      app factory: CORS, request ids, routers, error handlers
  core/
    config.py                  all settings, typed, from the environment
    logging.py                 JSON formatter, request-id context, extra-key guard
    errors.py                  AppError hierarchy -> the single error envelope
    security.py                optional X-API-Key dependency
  api/
    deps.py                    dependency wiring
    v1/
      router.py                /health open, everything else behind auth
      documents.py chat.py conversations.py health.py
  schemas/                     request/response models with OpenAPI examples
  db/
    models.py                  documents, chunks, conversations, messages
    session.py                 async engine, pgvector codec, session dependency
  services/
    ingestion/
      parsers.py               PDF (PyMuPDF), DOCX, TXT/MD; page numbers preserved
      chunker.py               recursive token-aware splitter, heading-aware
      pipeline.py              validate, dedupe, status transitions, batched embedding
      tokenizer.py             tiktoken with an offline fallback
    embeddings/                base.py (+ retry/backoff), hashing.py, openai_embedder.py
    llm/                       base.py, anthropic_client.py, fake.py
    retrieval.py               cosine search, optional hybrid RRF
    generation.py              context budget, prompt, citations, grounding, streaming
    conversation.py            history trimming, query rewriting, persistence
    prompts.py                 prompt text and the context-block format
alembic/versions/              schema + HNSW and GIN indexes
tests/unit/                    parsers, chunker, prompts, citations, rewriting, providers
tests/integration/             upload -> ingest -> chat -> stream against real Postgres
evals/                         dataset.jsonl + run_eval.py + generated reports
sample_docs/                   three original demo documents
scripts/                       seed.py, smoke.py
```

### Database schema

```mermaid
erDiagram
    documents ||--o{ chunks : "cascade delete"
    conversations ||--o{ messages : "cascade delete"

    documents {
        uuid id PK
        string filename
        string content_type
        string extension
        int size_bytes
        string content_hash UK "sha256, dedupe key"
        string status "pending|processing|ready|failed"
        text error_message
        int page_count
        int chunk_count
        timestamptz created_at
        timestamptz updated_at
    }
    chunks {
        uuid id PK
        uuid document_id FK
        int chunk_index "unique per document"
        int page "PDF page, else null"
        text content
        int token_count
        vector embedding "1536, HNSW cosine"
        tsvector content_tsv "generated, GIN"
        timestamptz created_at
    }
    conversations {
        uuid id PK
        string title
        timestamptz created_at
        timestamptz updated_at
    }
    messages {
        uuid id PK
        uuid conversation_id FK
        string role "user|assistant"
        text content
        jsonb sources "citation -> chunk mapping"
        jsonb usage "token counts"
        timestamptz created_at
    }
```

---

## Development

```bash
make help        # list targets
make install     # uv sync
make dev         # uvicorn --reload
make lint        # ruff check + ruff format --check
make format      # ruff check --fix + ruff format
make typecheck   # mypy (strict) over app, evals, scripts
make test        # full suite
make test-unit   # unit tests only, no database needed
make migrate     # alembic upgrade head
make revision m="…"
make seed        # ingest sample_docs/ through the running API
make smoke       # end-to-end check against the running API
make eval        # retrieval + refusal evaluation, writes evals/reports/
make up / down / logs
```

`make` is not required: every target is a one-line `uv run …` command (for
example `uv run pytest -q`, `uv run python -m scripts.seed`), which is what to
use on Windows without `make`.

### Tests

132 tests. Unit tests need nothing but the package. Integration tests need
PostgreSQL with pgvector and are **skipped** unless `TEST_DATABASE_URL` is set;
`make test` points it at the compose database, creates the test database if
needed, and applies the real Alembic migration so the migration is covered too.

No test touches the network: `LLM_PROVIDER=fake` and
`EMBEDDING_PROVIDER=hashing` are deterministic and local. A `RewritingLLM` stub
makes query rewriting observable end to end, and `app.dependency_overrides` is
used to exercise the API-key and hybrid-search paths.

```bash
docker compose up -d db
make test
```

---

## Evaluation results

`make eval` asks every question in `evals/dataset.jsonl` through `POST /chat`
against a running API and writes a timestamped JSON + Markdown report to
`evals/reports/`. The dataset holds **20 questions about `sample_docs/`: 15
answerable with an expected source document, and 5 deliberately unanswerable**.

- **Retrieval hit rate @k** — share of answerable questions where the expected
  document appears in the returned `sources`.
- **Refusal correctness** — share of unanswerable questions where `grounded` is
  `false`.
- **False refusal rate** — share of answerable questions wrongly refused. Shown
  because refusal behaviour is only useful if it is not achieved by refusing
  everything.

Measured on **2026-10-02** with `LLM_PROVIDER=fake` (the deterministic offline
stub) and `EMBEDDING_PROVIDER=hashing` (the local lexical embedder), on a clean
database seeded from `sample_docs/`:

| Configuration | Retrieval hit rate @5 | Refusal correctness | False refusal rate | Median retrieval |
| --- | --- | --- | --- | --- |
| Defaults — 600-token chunks, vector only | 67% (10/15) | 80% (4/5) | 33% (5/15) | 3 ms |
| 300-token chunks, hybrid search on | **93% (14/15)** | 80% (4/5) | **7% (1/15)** | 7 ms |

Both rows come from committed reports — `evals/reports/eval-20261002T104320Z.md`
(defaults) and `evals/reports/eval-20261002T104352Z.md` (tuned) — each with the
full per-question table. Reproduce the second row with:

```bash
cp .env.eval-tuned .env
docker compose down -v && docker compose up -d --build
make seed && make eval
```

**What these numbers are and are not.** They describe this dataset, this
three-document corpus and these providers — nothing else, and they are not
comparable to any published benchmark. Specifically:

- The retrieval numbers are a genuine measurement of the retrieval stack
  (chunking, embedding, pgvector search, threshold).
- The refusal numbers are **not** a measurement of model judgement. With
  `LLM_PROVIDER=fake` there is no model, so refusal is decided entirely by
  whether any chunk cleared `RETRIEVAL_MIN_SCORE`. The single refusal failure in
  both rows is "Does Lumen ship a first-party integration for Google BigQuery?",
  where the product FAQ's integrations section is lexically close enough to clear
  the floor; a real model reading that context would see BigQuery is not listed
  and refuse. Re-run with `LLM_PROVIDER=anthropic` to measure the model.
- No latency or cost claim is made about real providers: the generation latency
  in the reports is the offline stub's, and is 0 ms.

The comparison table is also the reason the eval exists: the 600-token default
is a reasonable general setting, but on a short, heavily sectioned corpus it puts
several topics in one chunk and dilutes the lexical signal. The eval made that
visible and quantified the fix instead of leaving it to taste.

---

## Design decisions

**Chunking: recursive, token-aware, heading-first.** The splitter walks a
separator list from coarse to fine — markdown headings, then paragraphs, lines,
sentence boundaries, and finally words — and only splits as finely as it must to
fit the token budget. Headings come first because cutting a structured document
at its section boundaries keeps each chunk about one topic, which mattered more
for retrieval quality than anything else measured here. Headings attach to the
section they introduce rather than trailing the previous one. Adjacent chunks
overlap by `CHUNK_OVERLAP_TOKENS` so a fact spanning a boundary is still
retrievable, and the overlap is clamped below half the budget so a large overlap
cannot stall the splitter. Token counting uses tiktoken, with a character-ratio
fallback so no-network environments still work.

**Why pgvector.** The corpus already needs a relational store: documents have
status, ownership and lifecycle; conversations have messages; everything needs
cascade deletes and transactions. pgvector keeps vectors in the same database and
the same transaction as that metadata, so a document and its chunks can never
drift apart, filtered search (`document_ids`, `status = 'ready'`) is a plain
`WHERE` clause rather than a metadata filter bolted onto a vector index, and
operations is one database instead of two. The cost is losing a dedicated vector
store's scale and index variety; at this size that is not the binding
constraint. The HNSW index with `vector_cosine_ops` is created in the migration,
not at runtime.

**Query rewriting before retrieval.** Conversation history helps generation, but
retrieval is where a follow-up actually breaks: "what about its pricing?"
embedded as-is matches nothing useful. A cheap heuristic gate (short message,
referential pronoun or a fragment opener) decides whether to spend a model call
rewriting it into a standalone question; the rewritten query is used for
retrieval and returned as `rewritten_query` so the behaviour is visible rather
than magic. If the model echoes the question back unchanged, that counts as no
rewrite.

**Grounding is enforced in three places, not just the prompt.** The system
prompt instructs the model to answer only from numbered excerpts, cite them
inline, and reply with one exact sentence when the context does not contain the
answer. That alone is not enough, so: context assembly fills a token budget best
chunk first and tells the model explicitly when nothing was retrieved;
`RETRIEVAL_MIN_SCORE` drops weak matches so an off-topic question arrives with
empty context and the refusal path is taken deterministically; and
`sanitize_citations` strips any `[n]` marker that does not map to a returned
source before the answer is persisted — so a hallucinated citation number cannot
reach the client. `grounded` in the response is derived from the final answer and
the sources, and is the field a frontend should branch on.

**Providers behind interfaces, offline by default.** `Embedder` and `LLMClient`
are abstract; business logic never imports a vendor SDK, and `factory.py` is the
only place a provider name is resolved. Retry with exponential backoff and jitter
lives in the `Embedder` base class, so every provider inherits it. The defaults
(`hashing` embeddings, `fake` LLM) are deterministic, offline and need no key,
which is what lets `docker compose up && make seed && make test && make eval` all
work on a clean clone. Both defaults are documented as stand-ins, not as
quality: the hashing embedder is lexical with no IDF, and the fake LLM is string
matching with no inference.

**Anthropic specifics.** Claude Opus 5 does not accept `temperature` / `top_p` /
`top_k` at all, so generation is steered by the prompt plus
`output_config.effort` (`LLM_EFFORT`, default `low` for a short extractive task).
Thinking is left adaptive by default; `LLM_THINKING=disabled` is available for
lower latency and is only valid at `high` effort or below. Streaming uses the
SDK's own stream helper and ends by reading the final message for token usage.

**Operational choices.** Ingestion runs in a FastAPI background task so an
upload returns immediately, with status tracked on the row and the failure
reason stored; uploads are idempotent by SHA-256 content hash, and a document
that never reached `ready` is requeued on re-upload rather than being
permanently stuck. `/chat/stream` opens its own database session inside the
response generator because FastAPI tears down `yield` dependencies before a
streaming body is consumed. Logs are JSON with a request id, retrieval and
generation latency, and token usage where the provider reports it; `log_fields()`
guards the `extra` dict against keys that shadow `LogRecord` attributes, after
exactly that bug turned a log line into a 500.

---

## Limitations and next steps

Known limitations, as built:

- **The default embedder is lexical, not semantic.** The hashing vectorizer
  matches word overlap, has no corpus IDF, and penalises a short question
  against a long chunk. A question phrased in different vocabulary than the
  source text will miss. It exists for offline reproducibility;
  `EMBEDDING_PROVIDER=openai` is the semantic path, and the numbers above were
  *not* measured with it.
- **The default LLM is a stub.** `LLM_PROVIDER=fake` quotes the best-matching
  sentence from the top excerpt. It is enough to exercise and test the citation
  and streaming paths, and it is not an answer-quality system. Anything about
  answer quality requires `LLM_PROVIDER=anthropic`.
- **No evaluation of answer quality or citation correctness.** The eval measures
  retrieval hit rate and refusal behaviour. It does not check whether an answer
  is factually right, or whether `[1]` is the chunk that actually supports the
  claim — only that it maps to a real retrieved chunk.
- **No OCR.** A scanned PDF with no text layer is rejected as unreadable rather
  than silently ingested empty.
- **Single-tenant.** There is no user model and no per-document authorization;
  `API_KEY` is one shared key for the whole service.
- **Ingestion is in-process.** A background task dies with the container, which
  is why re-upload requeues. There is no retry queue, no progress percentage and
  no cancellation.
- **Whole file in memory.** Uploads are read fully before validation, bounded
  only by `MAX_UPLOAD_MB`.
- **No rate limiting and no pagination cursors.** Listing is `limit`/`offset`.
- **`EMBEDDING_DIM` is baked into the migration.** Changing embedding model
  dimensionality needs a new migration and a full re-embed.

Next steps, roughly in the order I would do them:

1. Move ingestion to a real worker (ARQ or Celery) with retries, a dead-letter
   path and a progress field, so ingestion survives a restart.
2. Add citation-level evaluation: for each answer, check that the cited chunk
   contains the supporting span. That is the metric this project most lacks.
3. Add a reranker (cross-encoder or a provider rerank endpoint) over the top ~20
   candidates — the cheapest large win on retrieval quality after embeddings.
4. Run the eval with `anthropic` + `openai` providers in CI on a schedule, and
   track the four metrics over time instead of in a README table.
5. Users, per-document authorization and audit logging; `API_KEY` is a stopgap.
6. Streaming ingestion to disk or object storage, and parsing from a stream, to
   lift the in-memory file-size ceiling.
7. Return the matched span offsets inside each chunk so a frontend can highlight
   the exact supporting text.

---

## Sample documents

`sample_docs/` contains three short original documents written for this
repository — an employee handbook, a product FAQ and a security overview for a
fictional company (Northwind Labs) and a fictional product (Lumen). They are
demo data, not real policies, and nothing in them is copied from elsewhere.
