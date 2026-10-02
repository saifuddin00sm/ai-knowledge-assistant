/**
 * Mirrors the response models in `app/schemas/` on the API side.
 *
 * Keep this file in sync with the backend, or regenerate it from the live
 * schema: `npx openapi-typescript http://localhost:8000/openapi.json`.
 */

export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export type MessageRole = "user" | "assistant";

export interface ApiErrorBody {
  error: { code: string; message: string };
}

export interface HealthResponse {
  status: string;
  version: string;
  database: string;
  llm_provider: string;
  llm_model: string;
  embedding_provider: string;
  embedding_model: string;
}

export interface DocumentSummary {
  id: string;
  filename: string;
  extension: string;
  size_bytes: number;
  status: DocumentStatus;
  chunk_count: number;
  page_count: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  documents: DocumentSummary[];
  total: number;
}

export interface DocumentChunkPreview {
  chunk_index: number;
  page: number | null;
  token_count: number;
  snippet: string;
}

export interface DocumentDetail extends DocumentSummary {
  content_type: string;
  content_hash: string;
  chunks: DocumentChunkPreview[];
}

export interface DeleteDocumentResponse {
  id: string;
  deleted: boolean;
  chunks_deleted: number;
}

export interface Source {
  index: number;
  document_id: string;
  filename: string;
  page: number | null;
  chunk_index: number;
  snippet: string;
  score: number;
}

export interface Usage {
  input_tokens: number | null;
  output_tokens: number | null;
}

export interface Timings {
  retrieval_ms: number;
  generation_ms: number;
  total_ms: number;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string | null;
  document_ids?: string[] | null;
  top_k?: number | null;
  min_score?: number | null;
}

export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  answer: string;
  sources: Source[];
  grounded: boolean;
  rewritten_query: string | null;
  model: string;
  usage: Usage;
  timings: Timings;
}

export interface ConversationResponse {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface MessageResponse {
  id: string;
  role: MessageRole;
  content: string;
  sources: Source[];
  usage: Usage | null;
  created_at: string;
}

export interface MessageListResponse {
  conversation_id: string;
  messages: MessageResponse[];
}

/* -- SSE payloads from POST /chat/stream ---------------------------------- */

export interface StreamStartEvent {
  conversation_id: string;
  rewritten_query: string | null;
  retrieval_ms: number;
}

export interface StreamTokenEvent {
  text: string;
}

export interface StreamSourcesEvent {
  conversation_id: string;
  message_id: string;
  answer: string;
  grounded: boolean;
  sources: Source[];
  usage: Usage;
  timings: Timings;
}
