# AI Knowledge Assistant — Web

The demo frontend for the [AI Knowledge Assistant API](../README.md). It is a
Next.js **static export**: no server, no API routes, no SSR at request time. The
browser talks to the FastAPI backend directly, so the whole thing can be dropped
on any static host or CDN.

```bash
cp .env.local.example .env.local   # optional; defaults point at localhost:8000
npm install
npm run dev                        # http://localhost:3000
```

The API must be running (`docker compose up -d` in the repository root) and its
`CORS_ORIGINS` must include the origin you load this from. The default allows
`http://localhost:3000` and `http://localhost:3001` — `next dev` falls back to
3001 when 3000 is taken.

## What it demonstrates

| | |
| --- | --- |
| **Streaming answers** | Tokens render as they arrive over SSE, coalesced to one React update per animation frame. A stop button aborts mid-stream and keeps what arrived. |
| **Clickable citations** | `[1]` markers in the answer are real controls. Clicking one scrolls to the source card it refers to and flashes it. |
| **Source drill-down** | Clicking a source opens a slide-over with the full retrieved passage, its similarity score, token count and the document's hash — the "prove it" surface. |
| **Visible refusals** | When nothing clears the similarity floor, the answer is rendered as a distinct amber *Not in your documents* state instead of looking like a normal answer. |
| **Document lifecycle** | Drag-and-drop upload, `pending → processing → ready \| failed` status badges polled only while something is in flight, per-file error messages, delete. |
| **Retrieval scoping** | Tick documents in the sidebar to restrict retrieval to them; the composer shows the active scope. |
| **Observability** | Retrieval/generation latency and token usage under each answer; a header pill showing the live provider, model and database status. |

## Architecture

```
src/
  app/
    layout.tsx            fonts, metadata, pre-paint theme script
    page.tsx              composition and top-level state only
    globals.css           design tokens (light + dark), motion, utilities
  components/
    chat/                 thread, message rows, composer, markdown, sources, slide-over
    documents/            upload zone, document list
    theme/                three-way theme control
    ui/                   button, badges, status, score meter
    sidebar.tsx  health-pill.tsx
  hooks/
    use-chat.ts           turns, streaming, conversation switching
    use-documents.ts      list, upload, poll-while-ingesting, delete
  lib/
    api.ts                typed client; parses the API's error envelope
    sse.ts                SSE framing for POST /chat/stream
    types.ts              mirrors the API response models
    citations.ts          `[n]` -> markdown link -> citation chip
    storage.ts            conversation index (localStorage)
    external-store.ts     useSyncExternalStore helper
    theme.ts  format.ts  cn.ts
```

**State.** No state library. `useChat` and `useDocuments` own everything;
`page.tsx` wires them together. Browser-only state (theme, conversation list)
is read through `useSyncExternalStore` rather than a `useEffect` + `setState`,
which keeps it out of the render cascade and syncs across tabs for free.

**Conversation list.** The API addresses conversations by id and has no list
endpoint, so the sidebar index lives in `localStorage`. Messages themselves
always come from `GET /conversations/{id}/messages`.

**Citations.** The answer is markdown. Rather than parsing it by hand, `[n]`
markers are rewritten as links to `#cite-n` and `react-markdown` routes them
through a custom anchor renderer that emits a focusable chip. Markers without a
matching source are left as plain text (the API already strips invalid ones).

**Streaming.** `streamChat` parses SSE frames off the `fetch` body stream —
`EventSource` cannot POST. The final `sources` event carries the authoritative,
citation-sanitised answer, so the streamed tokens are discarded and replaced
when it arrives.

## Design

Minimalism / Swiss: high contrast, grid-based, almost no chrome. Violet primary
with a cyan accent; **the canvas is neutral grey rather than violet-tinted** —
a tinted canvas reads as a marketing page, and this is a working tool. Type is
Space Grotesk for display and DM Sans for body.

Tokens live in `globals.css` as CSS variables mapped into Tailwind v4's
`@theme`. Light and dark are both first-class, selected by a three-way control
(system / light / dark) and applied before first paint so there is no flash.

Accessibility: every colour pair clears WCAG AA for body text; status is carried
by icon **and** text, never colour alone; focus rings are never removed; icon-only
controls all have labels; all motion is behind `prefers-reduced-motion`.

## Scripts

```bash
npm run dev      # dev server
npm run build    # static export into out/
npm run lint     # eslint (flat config, next + react-compiler rules)
npx tsc --noEmit # type check
```

## Deployment

`npm run build` writes a static site to `out/`. Serve it with anything:

```bash
npx serve out
```

Or build the image, which compiles the export and serves it with nginx:

```bash
# from the repository root
docker compose up -d --build web     # http://localhost:3000
```

`NEXT_PUBLIC_API_BASE_URL` is **inlined at build time**, so pointing the app at
a different API means rebuilding (the compose service passes it as a build arg).

## Known limitations

- **Conversations are per-browser.** Clearing site data loses the sidebar list;
  the messages still exist server-side if you have the id.
- **`NEXT_PUBLIC_API_KEY` is not a security boundary.** Anything inlined into a
  static bundle is readable by whoever loads the page. It exists so a demo can
  talk to an API started with `API_KEY` set, nothing more.
- **No virtualisation.** Very long conversations render every turn.
- **No optimistic document state.** An upload appears in the list after the
  server accepts it rather than immediately.
- **Responsive layout is implemented but only verified at desktop widths** — the
  sidebar collapses to a drawer below `lg`, which I could not visually confirm
  because window resizing failed in the browser session used to test it.
