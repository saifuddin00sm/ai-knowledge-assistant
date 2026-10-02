/**
 * Server-Sent Events client for `POST /chat/stream`.
 *
 * `EventSource` cannot issue a POST, so this parses the SSE framing off a
 * `fetch` body stream. Event order from the API is:
 *   start -> token* -> sources -> done,  with `error` able to replace 2-4.
 */

import { ApiError, apiUrl, authHeaders } from "@/lib/api";
import type {
  ApiErrorBody,
  ChatRequest,
  StreamSourcesEvent,
  StreamStartEvent,
} from "@/lib/types";

export interface StreamHandlers {
  onStart?: (event: StreamStartEvent) => void;
  onToken?: (text: string) => void;
  onSources?: (event: StreamSourcesEvent) => void;
}

interface Frame {
  event: string;
  data: string;
}

/** Split a raw SSE buffer into complete frames, returning the partial tail. */
function takeFrames(buffer: string): { frames: Frame[]; rest: string } {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  const frames: Frame[] = [];

  for (const part of parts) {
    let event = "message";
    let data = "";
    for (const line of part.split("\n")) {
      if (line.startsWith(":")) continue; // comment / keep-alive
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    if (data) frames.push({ event, data });
  }
  return { frames, rest };
}

/**
 * Stream one answer. Resolves with the final `sources` payload, which carries
 * the authoritative citation-sanitised answer - prefer it over the concatenated
 * tokens when rendering the settled message.
 */
export async function streamChat(
  payload: ChatRequest,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<StreamSourcesEvent> {
  let response: Response;
  try {
    response = await fetch(apiUrl("/chat/stream"), {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
      signal,
    });
  } catch (cause) {
    if (signal?.aborted) throw cause;
    throw new ApiError(0, "network_error", "Cannot reach the API. Is it running?");
  }

  // Errors raised before the stream opens are normal JSON responses.
  if (!response.ok) {
    let code = "http_error";
    let message = `Request failed with status ${response.status}`;
    try {
      const body = (await response.json()) as ApiErrorBody;
      code = body.error?.code ?? code;
      message = body.error?.message ?? message;
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(response.status, code, message);
  }
  if (!response.body) {
    throw new ApiError(0, "empty_stream", "The API returned no response body.");
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  let settled: StreamSourcesEvent | null = null;

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;

      const { frames, rest } = takeFrames(buffer);
      buffer = rest;

      for (const frame of frames) {
        const payloadJson = JSON.parse(frame.data);
        switch (frame.event) {
          case "start":
            handlers.onStart?.(payloadJson as StreamStartEvent);
            break;
          case "token":
            handlers.onToken?.((payloadJson as { text: string }).text);
            break;
          case "sources":
            settled = payloadJson as StreamSourcesEvent;
            handlers.onSources?.(settled);
            break;
          case "error": {
            const body = payloadJson as ApiErrorBody;
            // The HTTP status was already 200, so a mid-stream failure can only
            // arrive as an event. Clients must handle it.
            throw new ApiError(
              200,
              body.error?.code ?? "stream_error",
              body.error?.message ?? "Generation failed mid-stream.",
            );
          }
          case "done":
            break;
          default:
            break;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }

  if (!settled) {
    throw new ApiError(
      0,
      "incomplete_stream",
      "The stream ended before any sources were received.",
    );
  }
  return settled;
}
