/**
 * Typed client for the AI Knowledge Assistant API.
 *
 * Every non-2xx response from the API is `{ "error": { code, message } }`, so
 * failures are surfaced as `ApiError` with the server's own message rather than
 * a bare status code.
 */

import type {
  ChatRequest,
  ChatResponse,
  ConversationResponse,
  DeleteDocumentResponse,
  DocumentDetail,
  DocumentListResponse,
  DocumentSummary,
  HealthResponse,
  MessageListResponse,
} from "@/lib/types";

const BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

export const API_PREFIX = "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export function apiUrl(path: string): string {
  return `${BASE_URL}${API_PREFIX}${path}`;
}

export function authHeaders(): Record<string, string> {
  return API_KEY ? { "X-API-Key": API_KEY } : {};
}

/** The server is reachable only from the browser in this setup. */
export function apiBaseUrl(): string {
  return BASE_URL;
}

async function toApiError(response: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `Request failed with status ${response.status}`;
  try {
    const body = await response.json();
    if (body?.error?.message) {
      code = body.error.code ?? code;
      message = body.error.message;
    }
  } catch {
    // Not JSON (a proxy error page, say) - keep the generic message.
  }
  return new ApiError(response.status, code, message);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...init,
      headers: { ...authHeaders(), ...(init.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      0,
      "network_error",
      `Cannot reach the API at ${BASE_URL}. Is it running?`,
    );
  }

  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function json(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

/* -- health ---------------------------------------------------------------- */

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

/* -- documents ------------------------------------------------------------- */

export function listDocuments(limit = 100): Promise<DocumentListResponse> {
  return request<DocumentListResponse>(`/documents?limit=${limit}`);
}

export function getDocument(id: string): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${id}`);
}

export function deleteDocument(id: string): Promise<DeleteDocumentResponse> {
  return request<DeleteDocumentResponse>(`/documents/${id}`, {
    method: "DELETE",
  });
}

export function uploadDocument(file: File): Promise<DocumentSummary> {
  const form = new FormData();
  form.append("file", file);
  // Content-Type is left to the browser so it can set the multipart boundary.
  return request<DocumentSummary>("/documents", { method: "POST", body: form });
}

/* -- conversations --------------------------------------------------------- */

export function createConversation(
  title?: string | null,
): Promise<ConversationResponse> {
  return request<ConversationResponse>("/conversations", json({ title: title ?? null }));
}

export function listMessages(id: string): Promise<MessageListResponse> {
  return request<MessageListResponse>(`/conversations/${id}/messages`);
}

export function deleteConversation(id: string): Promise<void> {
  return request<void>(`/conversations/${id}`, { method: "DELETE" });
}

/* -- chat ------------------------------------------------------------------ */

export function chat(payload: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", json(payload));
}
