"use client";

import { FileText, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Badge, ScoreMeter, Spinner } from "@/components/ui/status";
import { getDocument } from "@/lib/api";
import { formatBytes, formatScore, sourceLocation } from "@/lib/format";
import type { DocumentDetail, Source } from "@/lib/types";

/**
 * Slide-over showing the full retrieved passage plus where it sits in the
 * document. This is the "prove it" surface: it closes the loop from an inline
 * citation to the actual indexed text.
 */
export function SourceSheet({
  source,
  onClose,
}: {
  source: Source | null;
  onClose: () => void;
}) {
  if (!source) return null;
  // Keyed so opening a different source resets the panel's fetch state rather
  // than needing an effect to clear it.
  return (
    <SheetBody
      key={`${source.document_id}:${source.chunk_index}`}
      source={source}
      onClose={onClose}
    />
  );
}

type Detail = { kind: "loading" } | { kind: "ready"; document: DocumentDetail } | { kind: "error" };

function SheetBody({ source, onClose }: { source: Source; onClose: () => void }) {
  const [detail, setDetail] = useState<Detail>({ kind: "loading" });
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    getDocument(source.document_id)
      .then((document) => {
        if (!cancelled) setDetail({ kind: "ready", document });
      })
      .catch(() => {
        if (!cancelled) setDetail({ kind: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [source.document_id]);

  const document = detail.kind === "ready" ? detail.document : null;
  const chunk = document?.chunks.find((item) => item.chunk_index === source.chunk_index);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="Close source details"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-black/30 backdrop-blur-[1px]"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`Source ${source.index}: ${source.filename}`}
        className="animate-slide-over relative flex h-full w-full max-w-md flex-col border-l border-border bg-surface shadow-2xl"
      >
        <header className="flex items-start gap-2 border-b border-border px-4 py-3">
          <span className="mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded bg-primary-soft font-mono text-xs font-semibold text-primary">
            {source.index}
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-sm font-semibold text-foreground">
              {source.filename}
            </h2>
            <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-[11px] text-muted-foreground">
              <span>chunk {source.chunk_index}</span>
              {source.page !== null ? <span>· page {source.page}</span> : null}
              {chunk ? <span>· {chunk.token_count} tokens</span> : null}
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Close source details"
            className="inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted-foreground transition-colors duration-200 hover:bg-surface-2 hover:text-foreground"
          >
            <X className="size-4" aria-hidden />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 scrollbar-thin">
          <div className="mb-3 flex items-center gap-2">
            <ScoreMeter score={source.score} />
            <span className="font-mono text-[11px] text-muted-foreground">
              {formatScore(source.score)} cosine similarity
            </span>
          </div>

          <h3 className="mb-1.5 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
            Retrieved passage
          </h3>
          <blockquote className="rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-[13px] leading-relaxed whitespace-pre-wrap text-foreground">
            {chunk?.snippet ?? source.snippet}
          </blockquote>
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            Shown truncated. This is the passage the answer was generated from.
          </p>

          <h3 className="mt-5 mb-1.5 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
            Document
          </h3>
          {detail.kind === "loading" ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Spinner className="size-3.5" /> Loading document…
            </div>
          ) : document ? (
            <div className="rounded-lg border border-border bg-surface px-3 py-2.5">
              <p className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <FileText className="size-3.5 text-muted-foreground" aria-hidden />
                {sourceLocation(document.filename, source.page)}
              </p>
              <p className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                <Badge tone="neutral">{document.extension.toUpperCase()}</Badge>
                <span>{document.chunk_count} chunks</span>
                {document.page_count ? <span>· {document.page_count} pages</span> : null}
                <span>· {formatBytes(document.size_bytes)}</span>
              </p>
              <p className="mt-2 font-mono text-[10px] break-all text-muted-foreground">
                sha256 {document.content_hash.slice(0, 24)}…
              </p>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              Document details unavailable — it may have been deleted since this answer
              was generated.
            </p>
          )}
        </div>
      </aside>
    </div>
  );
}
