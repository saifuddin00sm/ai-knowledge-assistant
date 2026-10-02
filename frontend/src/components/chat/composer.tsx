"use client";

import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";

const MAX_ROWS_HEIGHT = 160;

export function Composer({
  onSend,
  onStop,
  busy,
  disabled,
  scopeLabel,
}: {
  onSend: (message: string) => void;
  onStop: () => void;
  busy: boolean;
  disabled: boolean;
  /** e.g. "Searching 2 of 3 documents" — shown under the input. */
  scopeLabel: string | null;
}) {
  const [value, setValue] = useState("");
  const textarea = useRef<HTMLTextAreaElement>(null);

  // Grow with the content up to a cap, then scroll.
  useEffect(() => {
    const element = textarea.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, MAX_ROWS_HEIGHT)}px`;
  }, [value]);

  function submit() {
    const message = value.trim();
    if (!message || busy || disabled) return;
    setValue("");
    onSend(message);
  }

  return (
    <div className="border-t border-border bg-background/80 px-3 py-3 backdrop-blur sm:px-6">
      <div className="mx-auto w-full max-w-3xl">
        <div
          className={cn(
            "flex items-end gap-2 rounded-2xl border bg-surface px-3 py-2",
            "transition-colors duration-200",
            "focus-within:border-primary/60",
            disabled ? "border-border opacity-60" : "border-border",
          )}
        >
          <label htmlFor="composer" className="sr-only">
            Ask a question about your documents
          </label>
          <textarea
            id="composer"
            ref={textarea}
            rows={1}
            value={value}
            disabled={disabled}
            placeholder={
              disabled ? "Upload a document to get started…" : "Ask a question…"
            }
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              // Enter sends; Shift+Enter inserts a newline.
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            className="max-h-40 min-h-6 flex-1 resize-none bg-transparent py-1.5 text-sm leading-relaxed text-foreground outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
          />

          {busy ? (
            <button
              type="button"
              onClick={onStop}
              aria-label="Stop generating"
              title="Stop generating"
              className="inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-xl border border-border bg-surface text-foreground transition-colors duration-200 hover:bg-surface-2"
            >
              <Square className="size-3.5 fill-current" aria-hidden />
            </button>
          ) : (
            <button
              type="button"
              onClick={submit}
              disabled={disabled || value.trim().length === 0}
              aria-label="Send question"
              title="Send question"
              className="inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-xl bg-primary text-primary-foreground transition-[filter,opacity] duration-200 hover:brightness-110 disabled:pointer-events-none disabled:opacity-40"
            >
              <ArrowUp className="size-4" aria-hidden />
            </button>
          )}
        </div>

        <p className="mt-1.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-0.5 px-1 text-[11px] text-muted-foreground">
          <span>
            Answers come only from your documents, with citations.{" "}
            <kbd className="rounded border border-border bg-surface-2 px-1 font-mono text-[10px]">
              Enter
            </kbd>{" "}
            to send.
          </span>
          {scopeLabel ? <span className="text-primary">{scopeLabel}</span> : null}
        </p>
      </div>
    </div>
  );
}
