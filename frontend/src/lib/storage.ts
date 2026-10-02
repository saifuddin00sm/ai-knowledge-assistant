/**
 * Local conversation index.
 *
 * The API deliberately has no `GET /conversations` list endpoint - conversations
 * are addressed by id. The list in the sidebar is therefore kept in
 * `localStorage`, which also means one browser's demo never shows another's
 * threads. Messages themselves always come from the API.
 */

import { createBrowserStore } from "@/lib/external-store";

const KEY = "aka.conversations.v1";
const MAX_ENTRIES = 50;

export interface StoredConversation {
  id: string;
  title: string;
  updatedAt: string;
}

const EMPTY: StoredConversation[] = [];

function canUseStorage(): boolean {
  return typeof window !== "undefined" && !!window.localStorage;
}

export function loadConversations(): StoredConversation[] {
  if (!canUseStorage()) return EMPTY;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return EMPTY;
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return EMPTY;
    return parsed
      .filter(
        (item): item is StoredConversation =>
          typeof item === "object" &&
          item !== null &&
          typeof (item as StoredConversation).id === "string",
      )
      .map((item) => ({
        id: item.id,
        title: item.title || "Untitled",
        updatedAt: item.updatedAt || new Date(0).toISOString(),
      }))
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  } catch {
    return EMPTY;
  }
}

/** Subscribe to this from React with `useSyncExternalStore`. */
export const conversationStore = createBrowserStore<StoredConversation[]>(
  loadConversations,
  EMPTY,
);

function persist(entries: StoredConversation[]): void {
  if (!canUseStorage()) return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(entries.slice(0, MAX_ENTRIES)));
  } catch {
    // Quota or private-mode failures are not worth interrupting a demo for.
  }
  conversationStore.notify();
}

/** Insert or update an entry, keeping the list newest-first. */
export function upsertConversation(
  entry: Pick<StoredConversation, "id" | "title">,
): void {
  const existing = loadConversations();
  const previous = existing.find((item) => item.id === entry.id);
  persist([
    {
      id: entry.id,
      // The first question becomes the title; later turns keep it.
      title: previous?.title || entry.title || "Untitled",
      updatedAt: new Date().toISOString(),
    },
    ...existing.filter((item) => item.id !== entry.id),
  ]);
}

export function removeConversation(id: string): void {
  persist(loadConversations().filter((item) => item.id !== id));
}
