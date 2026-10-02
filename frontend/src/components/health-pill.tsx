"use client";

import { useEffect, useState } from "react";

import { apiBaseUrl, getHealth } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { HealthResponse } from "@/lib/types";

const POLL_INTERVAL_MS = 20_000;

type State =
  | { kind: "loading" }
  | { kind: "online"; health: HealthResponse }
  | { kind: "offline"; message: string };

/**
 * Shows which providers are actually serving requests. It earns its place in a
 * demo: it is the difference between "a chat box" and "a system wired to a
 * specific model and a live database".
 */
export function HealthPill() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const health = await getHealth();
        if (!cancelled) setState({ kind: "online", health });
      } catch (error) {
        if (!cancelled) {
          setState({
            kind: "offline",
            message: error instanceof Error ? error.message : "API unreachable",
          });
        }
      }
    }

    void poll();
    const timer = window.setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  if (state.kind === "loading") {
    return (
      <span className="inline-flex h-7 w-44 animate-pulse rounded-full bg-muted" aria-hidden />
    );
  }

  if (state.kind === "offline") {
    return (
      <span
        className="inline-flex items-center gap-2 rounded-full border border-danger/30 bg-danger-soft px-2.5 py-1 text-xs font-medium text-danger"
        title={`${state.message} (${apiBaseUrl()})`}
      >
        <Dot tone="danger" />
        API offline
      </span>
    );
  }

  const { health } = state;
  const dbHealthy = health.database === "ok";
  const usingStubs =
    health.llm_provider === "fake" || health.embedding_provider === "hashing";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs",
        dbHealthy
          ? "border-border bg-surface text-muted-foreground"
          : "border-warning/30 bg-warning-soft text-warning",
      )}
      title={[
        `LLM: ${health.llm_provider} / ${health.llm_model}`,
        `Embeddings: ${health.embedding_provider} / ${health.embedding_model}`,
        `Database: ${health.database}`,
        `API: ${apiBaseUrl()}`,
      ].join("\n")}
    >
      <Dot tone={dbHealthy ? "success" : "warning"} />
      <span className="font-mono text-[11px]">{health.llm_model}</span>
      {usingStubs ? (
        <span className="rounded bg-muted px-1 py-px text-[10px] font-medium text-muted-foreground">
          offline mode
        </span>
      ) : null}
    </span>
  );
}

function Dot({ tone }: { tone: "success" | "warning" | "danger" }) {
  const colour =
    tone === "success" ? "bg-success" : tone === "warning" ? "bg-warning" : "bg-danger";
  return <span className={cn("size-1.5 rounded-full", colour)} aria-hidden />;
}
