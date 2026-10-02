"use client";

import { AlertTriangle, RotateCcw, Search, Sparkles, User } from "lucide-react";

import { AnswerMarkdown } from "@/components/chat/answer-markdown";
import { SourceList } from "@/components/chat/source-list";
import { Button } from "@/components/ui/button";
import type { AssistantTurn, ErrorTurn, UserTurn } from "@/hooks/use-chat";
import { formatMilliseconds } from "@/lib/format";
import type { Source } from "@/lib/types";

export function UserRow({ turn }: { turn: UserTurn }) {
  return (
    <article className="animate-rise flex justify-end gap-3">
      <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap text-primary-foreground">
        {turn.content}
      </div>
      <Avatar tone="user" />
    </article>
  );
}

export function AssistantRow({
  turn,
  highlightedCitation,
  onCitationClick,
  onOpenSource,
}: {
  turn: AssistantTurn;
  highlightedCitation: number | null;
  onCitationClick: (messageId: string, index: number) => void;
  onOpenSource: (source: Source) => void;
}) {
  const refused = !turn.streaming && !turn.grounded && turn.sources.length === 0;

  return (
    <article className="animate-rise flex gap-3">
      <Avatar tone="assistant" />
      <div className="min-w-0 flex-1">
        {turn.rewrittenQuery ? (
          <p className="mb-1.5 flex items-start gap-1.5 text-[11px] leading-4 text-muted-foreground">
            <Search className="mt-px size-3 shrink-0" aria-hidden />
            <span>
              Searched for{" "}
              <span className="text-foreground italic">“{turn.rewrittenQuery}”</span>
            </span>
          </p>
        ) : null}

        <div
          className={
            refused
              ? "rounded-2xl rounded-tl-md border border-warning/30 bg-warning-soft px-3.5 py-2.5"
              : "rounded-2xl rounded-tl-md border border-border bg-surface px-3.5 py-2.5"
          }
        >
          {turn.streaming && turn.content.length === 0 ? (
            <ThinkingIndicator />
          ) : (
            <>
              {refused ? (
                <p className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-warning uppercase">
                  <AlertTriangle className="size-3" aria-hidden />
                  Not in your documents
                </p>
              ) : null}
              <div className={turn.streaming ? "streaming-caret" : undefined}>
                <AnswerMarkdown
                  answer={turn.content}
                  sourceCount={turn.sources.length}
                  onCitationClick={(index) => onCitationClick(turn.id, index)}
                />
              </div>
            </>
          )}
        </div>

        <SourceList
          messageId={turn.id}
          sources={turn.sources}
          highlighted={highlightedCitation}
          onOpen={onOpenSource}
        />

        {turn.timings || turn.usage ? (
          <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-[10px] text-muted-foreground">
            {turn.timings ? (
              <>
                <span>retrieval {formatMilliseconds(turn.timings.retrieval_ms)}</span>
                <span>· generation {formatMilliseconds(turn.timings.generation_ms)}</span>
              </>
            ) : null}
            {turn.usage?.input_tokens ? (
              <span>
                · {turn.usage.input_tokens} in / {turn.usage.output_tokens ?? 0} out
              </span>
            ) : null}
          </p>
        ) : null}
      </div>
    </article>
  );
}

export function ErrorRow({
  turn,
  onRetry,
}: {
  turn: ErrorTurn;
  onRetry: (question: string) => void;
}) {
  return (
    <article className="animate-rise flex gap-3">
      <Avatar tone="error" />
      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-md border border-danger/30 bg-danger-soft px-3.5 py-2.5">
        <p className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-danger uppercase">
          <AlertTriangle className="size-3" aria-hidden />
          Request failed
        </p>
        <p className="mt-1 text-sm leading-relaxed text-foreground">{turn.message}</p>
        {turn.question ? (
          <Button
            variant="secondary"
            size="sm"
            className="mt-2"
            onClick={() => onRetry(turn.question)}
          >
            <RotateCcw className="size-3.5" aria-hidden />
            Try again
          </Button>
        ) : null}
      </div>
    </article>
  );
}

function Avatar({ tone }: { tone: "user" | "assistant" | "error" }) {
  if (tone === "user") {
    return (
      <span
        className="mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-surface-2 text-muted-foreground"
        aria-hidden
      >
        <User className="size-3.5" />
      </span>
    );
  }
  return (
    <span
      className={
        tone === "error"
          ? "mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-danger-soft text-danger"
          : "mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary"
      }
      aria-hidden
    >
      {tone === "error" ? (
        <AlertTriangle className="size-3.5" />
      ) : (
        <Sparkles className="size-3.5" />
      )}
    </span>
  );
}

/** Shown between send and first token: retrieval is happening. */
function ThinkingIndicator() {
  return (
    <p
      className="flex items-center gap-2 text-sm text-muted-foreground"
      aria-live="polite"
    >
      <span className="flex gap-1" aria-hidden>
        {[0, 1, 2].map((index) => (
          <span
            key={index}
            className="size-1.5 animate-bounce rounded-full bg-muted-foreground/60"
            style={{ animationDelay: `${index * 120}ms`, animationDuration: "900ms" }}
          />
        ))}
      </span>
      Searching your documents…
    </p>
  );
}
