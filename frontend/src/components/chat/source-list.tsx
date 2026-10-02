"use client";

import { ChevronRight, FileText } from "lucide-react";

import { ScoreMeter } from "@/components/ui/status";
import { sourceElementId } from "@/lib/citations";
import { cn } from "@/lib/cn";
import { formatScore, sourceLocation } from "@/lib/format";
import type { Source } from "@/lib/types";

/**
 * The citation targets. Each card is addressable by DOM id so a `[n]` chip in
 * the answer can scroll to and flash the exact source it refers to.
 */
export function SourceList({
  messageId,
  sources,
  highlighted,
  onOpen,
}: {
  messageId: string;
  sources: Source[];
  highlighted: number | null;
  onOpen: (source: Source) => void;
}) {
  if (sources.length === 0) return null;

  return (
    <section className="mt-3" aria-label={`${sources.length} sources`}>
      <h4 className="mb-1.5 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
        {sources.length === 1 ? "1 source" : `${sources.length} sources`}
      </h4>
      <ul className="grid gap-1.5 sm:grid-cols-2">
        {sources.map((source) => (
          <li key={`${source.document_id}-${source.chunk_index}`}>
            <button
              type="button"
              id={sourceElementId(messageId, source.index)}
              onClick={() => onOpen(source)}
              className={cn(
                "group flex w-full cursor-pointer items-start gap-2 rounded-lg border px-2 py-2 text-left",
                "transition-colors duration-200",
                highlighted === source.index
                  ? "animate-cite-flash border-primary/50 bg-primary-soft"
                  : "border-border bg-surface hover:bg-surface-2",
              )}
            >
              <span className="mt-px inline-flex size-[18px] shrink-0 items-center justify-center rounded bg-primary-soft font-mono text-[11px] font-semibold text-primary">
                {source.index}
              </span>

              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1">
                  <FileText className="size-3 shrink-0 text-muted-foreground" aria-hidden />
                  <span
                    className="truncate text-xs font-medium text-foreground"
                    title={source.filename}
                  >
                    {sourceLocation(source.filename, source.page)}
                  </span>
                </span>
                <span className="mt-0.5 line-clamp-2 block text-[11px] leading-4 text-muted-foreground">
                  {source.snippet}
                </span>
                <span className="mt-1 flex items-center gap-1.5">
                  <ScoreMeter score={source.score} />
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {formatScore(source.score)} match · chunk {source.chunk_index}
                  </span>
                </span>
              </span>

              <ChevronRight
                className="mt-1 size-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
                aria-hidden
              />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
