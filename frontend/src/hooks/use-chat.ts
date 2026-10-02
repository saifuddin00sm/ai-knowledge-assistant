"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { ApiError, deleteConversation as deleteConversationRequest, listMessages } from "@/lib/api";
import { streamChat } from "@/lib/sse";
import {
  conversationStore,
  removeConversation,
  type StoredConversation,
  upsertConversation,
} from "@/lib/storage";
import { truncate } from "@/lib/format";
import type { Source, Timings, Usage } from "@/lib/types";

export interface UserTurn {
  kind: "user";
  id: string;
  content: string;
}

export interface AssistantTurn {
  kind: "assistant";
  id: string;
  content: string;
  sources: Source[];
  grounded: boolean;
  rewrittenQuery: string | null;
  usage: Usage | null;
  timings: Timings | null;
  streaming: boolean;
}

export interface ErrorTurn {
  kind: "error";
  id: string;
  message: string;
  /** The question that failed, so it can be retried verbatim. */
  question: string;
}

export type Turn = UserTurn | AssistantTurn | ErrorTurn;

export interface ChatState {
  turns: Turn[];
  conversationId: string | null;
  conversations: StoredConversation[];
  busy: boolean;
  loadingHistory: boolean;
  send: (message: string) => Promise<void>;
  stop: () => void;
  startNew: () => void;
  openConversation: (id: string) => Promise<void>;
  deleteConversation: (id: string) => void;
}

let localIdCounter = 0;
function localId(prefix: string): string {
  localIdCounter += 1;
  return `${prefix}-${Date.now()}-${localIdCounter}`;
}

export interface ChatOptions {
  /** Restrict retrieval to these documents; empty means search everything. */
  documentIds: string[];
}

export function useChat({ documentIds }: ChatOptions): ChatState {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // The sidebar list lives in localStorage, not React state.
  const conversations = useSyncExternalStore(
    conversationStore.subscribe,
    conversationStore.getSnapshot,
    conversationStore.getServerSnapshot,
  );

  const abort = useRef<AbortController | null>(null);
  // Tokens arrive faster than it is worth re-rendering for, so they are
  // coalesced into one state update per animation frame.
  const buffered = useRef("");
  const frame = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      abort.current?.abort();
      if (frame.current !== null) cancelAnimationFrame(frame.current);
    };
  }, []);

  const flushTokens = useCallback(() => {
    frame.current = null;
    const chunk = buffered.current;
    buffered.current = "";
    if (!chunk) return;
    setTurns((current) =>
      current.map((turn, index) =>
        index === current.length - 1 && turn.kind === "assistant"
          ? { ...turn, content: turn.content + chunk }
          : turn,
      ),
    );
  }, []);

  const pushToken = useCallback(
    (text: string) => {
      buffered.current += text;
      if (frame.current !== null) return;
      frame.current = requestAnimationFrame(flushTokens);
    },
    [flushTokens],
  );

  const send = useCallback(
    async (message: string) => {
      const question = message.trim();
      if (!question || busy) return;

      const placeholderId = localId("assistant");
      setBusy(true);
      setTurns((current) => [
        ...current,
        { kind: "user", id: localId("user"), content: question },
        {
          kind: "assistant",
          id: placeholderId,
          content: "",
          sources: [],
          grounded: false,
          rewrittenQuery: null,
          usage: null,
          timings: null,
          streaming: true,
        },
      ]);

      const controller = new AbortController();
      abort.current = controller;

      try {
        const settled = await streamChat(
          {
            message: question,
            conversation_id: conversationId,
            document_ids: documentIds.length > 0 ? documentIds : null,
          },
          {
            onStart: (event) => {
              setConversationId(event.conversation_id);
              upsertConversation({
                id: event.conversation_id,
                title: truncate(question, 60),
              });
              setTurns((current) =>
                current.map((turn) =>
                  turn.id === placeholderId && turn.kind === "assistant"
                    ? { ...turn, rewrittenQuery: event.rewritten_query }
                    : turn,
                ),
              );
            },
            onToken: pushToken,
          },
          controller.signal,
        );

        // Discard any buffered tokens: the sources event carries the final,
        // citation-sanitised answer, which is what gets persisted server-side.
        buffered.current = "";
        if (frame.current !== null) {
          cancelAnimationFrame(frame.current);
          frame.current = null;
        }

        setTurns((current) =>
          current.map((turn) =>
            turn.id === placeholderId && turn.kind === "assistant"
              ? {
                  ...turn,
                  id: settled.message_id,
                  content: settled.answer,
                  sources: settled.sources,
                  grounded: settled.grounded,
                  usage: settled.usage,
                  timings: settled.timings,
                  streaming: false,
                }
              : turn,
          ),
        );
      } catch (error) {
        const aborted =
          controller.signal.aborted ||
          (error instanceof DOMException && error.name === "AbortError");

        setTurns((current) => {
          const index = current.findIndex((turn) => turn.id === placeholderId);
          if (index === -1) return current;
          const partial = current[index];
          const streamed =
            partial.kind === "assistant" ? partial.content.trim() : "";

          // A stopped stream keeps whatever arrived; a failure becomes a
          // retryable error row so the question is not lost.
          const replacement: Turn = aborted
            ? {
                kind: "assistant",
                id: localId("stopped"),
                content: streamed || "_Stopped before any text arrived._",
                sources: partial.kind === "assistant" ? partial.sources : [],
                grounded: false,
                rewrittenQuery:
                  partial.kind === "assistant" ? partial.rewrittenQuery : null,
                usage: null,
                timings: null,
                streaming: false,
              }
            : {
                kind: "error",
                id: localId("error"),
                message:
                  error instanceof ApiError
                    ? error.message
                    : error instanceof Error
                      ? error.message
                      : "Something went wrong.",
                question,
              };

          return [...current.slice(0, index), replacement];
        });
      } finally {
        abort.current = null;
        setBusy(false);
      }
    },
    [busy, conversationId, documentIds, pushToken],
  );

  const stop = useCallback(() => {
    abort.current?.abort();
  }, []);

  const startNew = useCallback(() => {
    abort.current?.abort();
    setTurns([]);
    setConversationId(null);
  }, []);

  const openConversation = useCallback(async (id: string) => {
    abort.current?.abort();
    setLoadingHistory(true);
    setConversationId(id);
    try {
      const response = await listMessages(id);
      setTurns(
        response.messages.map<Turn>((message) =>
          message.role === "user"
            ? { kind: "user", id: message.id, content: message.content }
            : {
                kind: "assistant",
                id: message.id,
                content: message.content,
                sources: message.sources,
                // `grounded` is not persisted; derive it the same way the API
                // does - an answer with no sources cannot be grounded.
                grounded: message.sources.length > 0,
                rewrittenQuery: null,
                usage: message.usage,
                timings: null,
                streaming: false,
              },
        ),
      );
    } catch (error) {
      setTurns([
        {
          kind: "error",
          id: localId("error"),
          message:
            error instanceof Error ? error.message : "Could not load that conversation.",
          question: "",
        },
      ]);
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  const deleteConversation = useCallback(
    (id: string) => {
      removeConversation(id);
      if (id === conversationId) {
        setTurns([]);
        setConversationId(null);
      }
      // The local index is already updated; a failed server delete only leaves
      // an orphaned row behind, which is not worth blocking the UI for.
      void deleteConversationRequest(id).catch(() => undefined);
    },
    [conversationId],
  );

  return {
    turns,
    conversationId,
    conversations,
    busy,
    loadingHistory,
    send,
    stop,
    startNew,
    openConversation,
    deleteConversation,
  };
}
