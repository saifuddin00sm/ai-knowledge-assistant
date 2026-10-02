"use client";

import { Upload } from "lucide-react";
import { useId, useRef, useState } from "react";

import { cn } from "@/lib/cn";

const ACCEPTED = ".pdf,.docx,.txt,.md";

export function UploadZone({
  onFiles,
  busy,
}: {
  onFiles: (files: File[]) => void;
  busy: boolean;
}) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  // Nested dragenter/dragleave events fire for children; count them so the
  // highlight does not flicker as the pointer crosses the inner text.
  const depth = useRef(0);

  function handleFiles(list: FileList | null) {
    if (!list || list.length === 0) return;
    onFiles(Array.from(list));
  }

  return (
    <div
      onDragEnter={(event) => {
        event.preventDefault();
        depth.current += 1;
        setDragging(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => {
        event.preventDefault();
        depth.current = Math.max(0, depth.current - 1);
        if (depth.current === 0) setDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        depth.current = 0;
        setDragging(false);
        handleFiles(event.dataTransfer.files);
      }}
      className={cn(
        "rounded-xl border border-dashed transition-colors duration-200",
        dragging
          ? "border-primary bg-primary-soft"
          : "border-border-strong bg-surface-2/60 hover:border-primary/50",
      )}
    >
      <label
        htmlFor={inputId}
        className="flex cursor-pointer flex-col items-center gap-1 px-3 py-4 text-center"
      >
        <Upload
          className={cn("size-4", dragging ? "text-primary" : "text-muted-foreground")}
          aria-hidden
        />
        <span className="text-xs font-medium text-foreground">
          {dragging ? "Drop to upload" : "Add documents"}
        </span>
        <span className="text-[11px] text-muted-foreground">
          PDF, DOCX, TXT or MD · up to 20 MB
        </span>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          multiple
          accept={ACCEPTED}
          disabled={busy}
          className="sr-only"
          onChange={(event) => {
            handleFiles(event.target.files);
            // Allow re-selecting the same file after a failure.
            if (inputRef.current) inputRef.current.value = "";
          }}
        />
      </label>
    </div>
  );
}
