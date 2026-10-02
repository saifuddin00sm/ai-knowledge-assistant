import { AlertTriangle, Check, Clock, Loader2 } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import type { DocumentStatus } from "@/lib/types";

type Tone = "neutral" | "primary" | "accent" | "success" | "warning" | "danger";

const TONES: Record<Tone, string> = {
  neutral: "bg-muted text-muted-foreground",
  primary: "bg-primary-soft text-primary",
  accent: "bg-accent-soft text-accent",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
};

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: Tone;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5",
        "text-[11px] leading-5 font-medium whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

const STATUS_CONFIG: Record<
  DocumentStatus,
  { tone: Tone; label: string; icon: ReactNode }
> = {
  pending: {
    tone: "neutral",
    label: "Queued",
    icon: <Clock className="size-3" aria-hidden />,
  },
  processing: {
    tone: "accent",
    label: "Indexing",
    icon: <Loader2 className="size-3 animate-spin" aria-hidden />,
  },
  ready: {
    tone: "success",
    label: "Ready",
    icon: <Check className="size-3" aria-hidden />,
  },
  failed: {
    tone: "danger",
    label: "Failed",
    icon: <AlertTriangle className="size-3" aria-hidden />,
  },
};

/** Status is carried by icon + text, never by colour alone. */
export function StatusBadge({ status }: { status: DocumentStatus }) {
  const config = STATUS_CONFIG[status];
  return (
    <Badge tone={config.tone}>
      {config.icon}
      {config.label}
    </Badge>
  );
}

/** Horizontal meter for a 0-1 similarity score. */
export function ScoreMeter({ score }: { score: number }) {
  const percent = Math.max(2, Math.min(100, Math.round(score * 100)));
  return (
    <span
      className="inline-flex h-1 w-10 overflow-hidden rounded-full bg-muted"
      role="img"
      aria-label={`Similarity ${percent}%`}
    >
      <span
        className="h-full rounded-full bg-primary"
        style={{ width: `${percent}%` }}
      />
    </span>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <Loader2
      className={cn("size-4 animate-spin text-muted-foreground", className)}
      aria-hidden
    />
  );
}
