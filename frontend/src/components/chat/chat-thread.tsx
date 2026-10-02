"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { EmptyState } from "@/components/chat/empty-state";
import {
  AssistantRow,
  ErrorRow,
  UserRow,
} from "@/components/chat/message-row";
import { SourceSheet } from "@/components/chat/source-sheet";
import { Spinner } from "@/components/ui/status";
import type { Turn } from "@/hooks/use-chat";
import { sourceElementId } from "@/lib/citations";
import type { Source } from "@/lib/types";

const HIGHLIGHT_MS = 1200;
const AT_BOTTOM_SLACK_PX = 120;

export function ChatThread({
  turns,
  busy,
  loadingHistory,
  hasDocuments,
  onAsk,
}: {
  turns: Turn[];
  busy: boolean;
  loadingHistory: boolean;
  hasDocuments: boolean;
  onAsk: (question: string) => void;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const [openSource, setOpenSource] = useState<Source | null>(null);
  const [highlighted, setHighlighted] = useState<{
    messageId: string;
    index: number;
  } | null>(null);
  // Only auto-scroll while the user is already at the bottom, so reading an
  // older answer is not interrupted by new tokens.
  const pinned = useRef(true);

  const handleScroll = useCallback(() => {
    const element = scroller.current;
    if (!element) return;
    const distance =
      element.scrollHeight - element.scrollTop - element.clientHeight;
    pinned.current = distance < AT_BOTTOM_SLACK_PX;
  }, []);

  useEffect(() => {
    if (!pinned.current) return;
    const element = scroller.current;
    if (!element) return;
    element.scrollTop = element.scrollHeight;
  }, [turns]);

  const onCitationClick = useCallback((messageId: string, index: number) => {
    setHighlighted({ messageId, index });
    const target = document.getElementById(sourceElementId(messageId, index));
    target?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    window.setTimeout(() => setHighlighted(null), HIGHLIGHT_MS);
  }, []);

  const empty = turns.length === 0;

  return (
    <>
      <div
        ref={scroller}
        onScroll={handleScroll}
        className="min-h-0 flex-1 overflow-y-auto scrollbar-thin"
        // Streaming answers are announced politely rather than interrupting.
        aria-live="polite"
        aria-busy={busy}
      >
        {loadingHistory ? (
          <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
            <Spinner /> Loading conversation…
          </div>
        ) : empty ? (
          <EmptyState hasDocuments={hasDocuments} onPick={onAsk} />
        ) : (
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-3 py-5 sm:px-6 sm:py-6">
            {turns.map((turn) => {
              if (turn.kind === "user") return <UserRow key={turn.id} turn={turn} />;
              if (turn.kind === "error") {
                return <ErrorRow key={turn.id} turn={turn} onRetry={onAsk} />;
              }
              return (
                <AssistantRow
                  key={turn.id}
                  turn={turn}
                  highlightedCitation={
                    highlighted?.messageId === turn.id ? highlighted.index : null
                  }
                  onCitationClick={onCitationClick}
                  onOpenSource={setOpenSource}
                />
              );
            })}
          </div>
        )}
      </div>

      <SourceSheet source={openSource} onClose={() => setOpenSource(null)} />
    </>
  );
}
