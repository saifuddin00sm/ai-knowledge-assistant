"use client";

import { ArrowRight, FileUp, Quote, ShieldCheck } from "lucide-react";

/** Suggestions that work against the bundled sample documents. */
const SUGGESTIONS = [
  "How many days of paid annual leave do employees get?",
  "What does the Lumen Team plan cost per month?",
  "How long are audit logs retained?",
  "What is the stock option vesting schedule?",
];

export function EmptyState({
  hasDocuments,
  onPick,
}: {
  hasDocuments: boolean;
  onPick: (question: string) => void;
}) {
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col items-center px-4 py-10 text-center sm:py-16">
      <span
        className="inline-flex size-11 items-center justify-center rounded-2xl bg-primary-soft text-primary"
        aria-hidden
      >
        <Quote className="size-5" />
      </span>

      <h1 className="mt-4 text-xl font-semibold text-foreground sm:text-2xl">
        Ask your documents anything
      </h1>
      <p className="mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
        Every answer is built only from the documents you upload, and cites the exact
        passage it came from. If the answer is not in them, you get told so rather than
        guessed at.
      </p>

      {hasDocuments ? (
        <>
          <p className="mt-7 mb-2 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
            Try asking
          </p>
          <ul className="grid w-full gap-1.5 sm:grid-cols-2">
            {SUGGESTIONS.map((question, index) => (
              <li key={question}>
                <button
                  type="button"
                  onClick={() => onPick(question)}
                  className="group flex h-full w-full cursor-pointer items-center justify-between gap-2 rounded-xl border border-border bg-surface px-3 py-2.5 text-left transition-colors duration-200 hover:border-primary/40 hover:bg-surface-2"
                >
                  <span className="text-xs leading-5 text-foreground">{question}</span>
                  <ArrowRight
                    className="size-3.5 shrink-0 text-muted-foreground transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-primary"
                    aria-hidden
                  />
                </button>
                {index === SUGGESTIONS.length - 1 ? (
                  <span className="sr-only">
                    This last question is deliberately not answerable by the sample
                    documents.
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-muted-foreground">
            The last one is not in the sample documents — try it to see the refusal.
          </p>
        </>
      ) : (
        <div className="mt-7 w-full rounded-xl border border-dashed border-border-strong bg-surface-2/60 px-4 py-5">
          <FileUp className="mx-auto size-5 text-muted-foreground" aria-hidden />
          <p className="mt-2 text-sm font-medium text-foreground">No documents yet</p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Upload a PDF, DOCX, TXT or MD file from the sidebar to begin. Or load the
            three bundled samples with{" "}
            <code className="rounded bg-muted px-1 font-mono text-[11px]">make seed</code>.
          </p>
        </div>
      )}

      <ul className="mt-8 grid w-full gap-2 text-left sm:grid-cols-3">
        <Highlight
          icon={<Quote className="size-3.5" />}
          title="Cited"
          body="Click any [1] to jump to the passage behind it."
        />
        <Highlight
          icon={<ShieldCheck className="size-3.5" />}
          title="Grounded"
          body="No supporting passage means no answer, not a guess."
        />
        <Highlight
          icon={<FileUp className="size-3.5" />}
          title="Scoped"
          body="Tick documents in the sidebar to search only those."
        />
      </ul>
    </div>
  );
}

function Highlight({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <li className="rounded-xl border border-border bg-surface px-3 py-2.5">
      <p className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
        <span className="text-primary" aria-hidden>
          {icon}
        </span>
        {title}
      </p>
      <p className="mt-1 text-[11px] leading-4 text-muted-foreground">{body}</p>
    </li>
  );
}
