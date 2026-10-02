"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { deleteDocument, listDocuments, uploadDocument } from "@/lib/api";
import type { DocumentSummary } from "@/lib/types";

/** Ingestion runs in a background task, so unfinished documents need polling. */
const POLL_INTERVAL_MS = 1500;

export interface UploadFailure {
  filename: string;
  message: string;
}

export interface DocumentsState {
  documents: DocumentSummary[];
  loading: boolean;
  /** Error from loading the list, not from a single upload. */
  loadError: string | null;
  uploading: string[];
  uploadFailures: UploadFailure[];
  upload: (files: File[]) => Promise<void>;
  remove: (id: string) => Promise<void>;
  refresh: () => Promise<void>;
  dismissFailure: (filename: string) => void;
}

function isUnfinished(document: DocumentSummary): boolean {
  return document.status === "pending" || document.status === "processing";
}

export function useDocuments(): DocumentsState {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState<string[]>([]);
  const [uploadFailures, setUploadFailures] = useState<UploadFailure[]>([]);
  const timer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const response = await listDocuments();
      setDocuments(response.documents);
      setLoadError(null);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Could not load documents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll only while something is mid-ingestion, then stop.
  useEffect(() => {
    const busy = documents.some(isUnfinished) || uploading.length > 0;
    if (!busy) {
      if (timer.current !== null) {
        window.clearInterval(timer.current);
        timer.current = null;
      }
      return;
    }
    if (timer.current !== null) return;
    timer.current = window.setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => {
      if (timer.current !== null) {
        window.clearInterval(timer.current);
        timer.current = null;
      }
    };
  }, [documents, uploading.length, refresh]);

  const upload = useCallback(
    async (files: File[]) => {
      if (files.length === 0) return;
      const names = files.map((file) => file.name);
      setUploading((current) => [...current, ...names]);
      setUploadFailures((current) =>
        current.filter((failure) => !names.includes(failure.filename)),
      );

      // Sequential: it keeps the per-file error attribution simple and a demo
      // never uploads enough files for the round trips to matter.
      for (const file of files) {
        try {
          await uploadDocument(file);
        } catch (error) {
          setUploadFailures((current) => [
            ...current,
            {
              filename: file.name,
              message: error instanceof Error ? error.message : "Upload failed",
            },
          ]);
        } finally {
          setUploading((current) => current.filter((name) => name !== file.name));
        }
      }
      await refresh();
    },
    [refresh],
  );

  const remove = useCallback(
    async (id: string) => {
      const previous = documents;
      setDocuments((current) => current.filter((document) => document.id !== id));
      try {
        await deleteDocument(id);
      } catch (error) {
        setDocuments(previous); // put it back; the delete did not happen
        setLoadError(error instanceof Error ? error.message : "Could not delete document");
      }
    },
    [documents],
  );

  const dismissFailure = useCallback((filename: string) => {
    setUploadFailures((current) =>
      current.filter((failure) => failure.filename !== filename),
    );
  }, []);

  return {
    documents,
    loading,
    loadError,
    uploading,
    uploadFailures,
    upload,
    remove,
    refresh,
    dismissFailure,
  };
}
