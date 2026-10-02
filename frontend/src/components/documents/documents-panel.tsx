"use client";

import { AlertTriangle, FileText, Trash2, X } from "lucide-react";

import { UploadZone } from "@/components/documents/upload-zone";
import { IconButton } from "@/components/ui/button";
import { Badge, Spinner, StatusBadge } from "@/components/ui/status";
import type { DocumentsState } from "@/hooks/use-documents";
import { cn } from "@/lib/cn";
import { formatBytes } from "@/lib/format";
import type { DocumentSummary } from "@/lib/types";

export function DocumentsPanel({
  state,
  selectedIds,
  onToggleSelected,
  onClearSelection,
}: {
  state: DocumentsState;
  selectedIds: string[];
  onToggleSelected: (id: string) => void;
  onClearSelection: () => void;
}) {
  const { documents, loading, loadError, uploading, uploadFailures } = state;
  const readyCount = documents.filter((item) => item.status === "ready").length;

  return (
    <section className="flex min-h-0 flex-col gap-2" aria-labelledby="documents-heading">
      <header className="flex items-center justify-between gap-2">
        <h2
          id="documents-heading"
          className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase"
        >
          Documents
        </h2>
        {documents.length > 0 ? (
          <Badge tone="neutral">{readyCount} indexed</Badge>
        ) : null}
      </header>

      <UploadZone onFiles={state.upload} busy={uploading.length > 0} />

      {uploadFailures.length > 0 ? (
        <ul className="flex flex-col gap-1">
          {uploadFailures.map((failure) => (
            <li
              key={failure.filename}
              className="flex items-start gap-1.5 rounded-lg border border-danger/30 bg-danger-soft px-2 py-1.5"
            >
              <AlertTriangle className="mt-0.5 size-3 shrink-0 text-danger" aria-hidden />
              <span className="min-w-0 flex-1 text-[11px] leading-4 text-danger">
                <span className="font-medium break-all">{failure.filename}</span>
                <br />
                {failure.message}
              </span>
              <button
                type="button"
                onClick={() => state.dismissFailure(failure.filename)}
                aria-label={`Dismiss error for ${failure.filename}`}
                className="cursor-pointer text-danger/70 hover:text-danger"
              >
                <X className="size-3" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {loadError ? (
        <p className="rounded-lg border border-danger/30 bg-danger-soft px-2 py-1.5 text-[11px] text-danger">
          {loadError}
        </p>
      ) : null}

      {selectedIds.length > 0 ? (
        <div className="flex items-center justify-between gap-2 rounded-lg bg-primary-soft px-2 py-1.5">
          <span className="text-[11px] font-medium text-primary">
            Searching {selectedIds.length} of {readyCount}
          </span>
          <button
            type="button"
            onClick={onClearSelection}
            className="cursor-pointer text-[11px] font-medium text-primary underline-offset-2 hover:underline"
          >
            Search all
          </button>
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">
        {loading && documents.length === 0 ? (
          <ul className="flex flex-col gap-1" aria-busy>
            {[0, 1, 2].map((index) => (
              <li key={index} className="h-[52px] animate-pulse rounded-lg bg-muted" />
            ))}
          </ul>
        ) : documents.length === 0 ? (
          <p className="px-1 py-3 text-[11px] leading-5 text-muted-foreground">
            No documents yet. Upload one above, or run{" "}
            <code className="rounded bg-muted px-1 font-mono">make seed</code> to load the
            three sample documents.
          </p>
        ) : (
          <ul className="flex flex-col gap-1">
            {uploading.map((filename) => (
              <li
                key={`uploading-${filename}`}
                className="flex items-center gap-2 rounded-lg border border-border bg-surface px-2 py-2"
              >
                <Spinner className="size-3.5" />
                <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                  {filename}
                </span>
                <Badge tone="accent">Uploading</Badge>
              </li>
            ))}
            {documents.map((document) => (
              <DocumentRow
                key={document.id}
                document={document}
                selected={selectedIds.includes(document.id)}
                selectable={document.status === "ready"}
                onToggle={() => onToggleSelected(document.id)}
                onRemove={() => void state.remove(document.id)}
              />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function DocumentRow({
  document,
  selected,
  selectable,
  onToggle,
  onRemove,
}: {
  document: DocumentSummary;
  selected: boolean;
  selectable: boolean;
  onToggle: () => void;
  onRemove: () => void;
}) {
  const chunkLabel =
    document.chunk_count === 1 ? "1 chunk" : `${document.chunk_count} chunks`;

  return (
    <li
      className={cn(
        "group rounded-lg border px-2 py-2 transition-colors duration-200",
        selected
          ? "border-primary/40 bg-primary-soft"
          : "border-border bg-surface hover:bg-surface-2",
      )}
    >
      <div className="flex items-start gap-2">
        {selectable ? (
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            // Visible label text is the filename next to it; this names the control.
            aria-label={`Restrict search to ${document.filename}`}
            className="mt-0.5 size-3.5 cursor-pointer accent-[var(--primary)]"
          />
        ) : (
          <FileText className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden />
        )}

        <div className="min-w-0 flex-1">
          <p
            className="truncate text-xs font-medium text-foreground"
            title={document.filename}
          >
            {document.filename}
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] text-muted-foreground">
            <StatusBadge status={document.status} />
            {document.status === "ready" ? <span>{chunkLabel}</span> : null}
            {document.page_count ? <span>· {document.page_count}p</span> : null}
            <span>· {formatBytes(document.size_bytes)}</span>
          </p>
          {document.error_message ? (
            <p className="mt-1 text-[11px] leading-4 break-words text-danger">
              {document.error_message}
            </p>
          ) : null}
        </div>

        <IconButton
          label={`Delete ${document.filename}`}
          onClick={onRemove}
          className="size-7 shrink-0 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 hover:text-danger"
        >
          <Trash2 className="size-3.5" aria-hidden />
        </IconButton>
      </div>
    </li>
  );
}
