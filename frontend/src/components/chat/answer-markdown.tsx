"use client";

import { memo } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { citationIndexFromHref, linkifyCitations } from "@/lib/citations";

/**
 * Renders an answer as markdown, turning `[1]`-style markers into focusable
 * citation chips. The markers are rewritten as links to `#cite-n` first so
 * react-markdown routes them through the anchor renderer below.
 */
export const AnswerMarkdown = memo(function AnswerMarkdown({
  answer,
  sourceCount,
  onCitationClick,
}: {
  answer: string;
  sourceCount: number;
  onCitationClick: (index: number) => void;
}) {
  const components: Components = {
    a({ href, children, ...rest }) {
      const citation = citationIndexFromHref(href);
      if (citation === null) {
        return (
          <a
            {...rest}
            href={href}
            target="_blank"
            rel="noreferrer noopener"
            className="text-primary underline decoration-primary/40 underline-offset-2 hover:decoration-primary"
          >
            {children}
          </a>
        );
      }
      return (
        <button
          type="button"
          onClick={() => onCitationClick(citation)}
          aria-label={`Jump to source ${citation}`}
          className="mx-0.5 inline-flex h-[18px] min-w-[18px] cursor-pointer items-center justify-center rounded bg-primary-soft px-1 align-[1px] font-mono text-[11px] font-semibold text-primary transition-[filter,background-color] duration-150 hover:brightness-95"
        >
          {citation}
        </button>
      );
    },
    p({ children }) {
      return <p className="my-2 first:mt-0 last:mb-0">{children}</p>;
    },
    ul({ children }) {
      return <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>;
    },
    ol({ children }) {
      return <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>;
    },
    strong({ children }) {
      return <strong className="font-semibold text-foreground">{children}</strong>;
    },
    code({ children, className }) {
      const block = typeof className === "string" && className.includes("language-");
      if (block) {
        return (
          <code className="font-mono text-[12.5px] leading-relaxed">{children}</code>
        );
      }
      return (
        <code className="rounded bg-muted px-1 py-px font-mono text-[12.5px]">
          {children}
        </code>
      );
    },
    pre({ children }) {
      return (
        <pre className="my-2 overflow-x-auto rounded-lg border border-border bg-surface-2 p-3 scrollbar-thin">
          {children}
        </pre>
      );
    },
    h1({ children }) {
      return <h4 className="mt-3 mb-1 text-sm font-semibold first:mt-0">{children}</h4>;
    },
    h2({ children }) {
      return <h4 className="mt-3 mb-1 text-sm font-semibold first:mt-0">{children}</h4>;
    },
    h3({ children }) {
      return <h5 className="mt-3 mb-1 text-sm font-semibold first:mt-0">{children}</h5>;
    },
    blockquote({ children }) {
      return (
        <blockquote className="my-2 border-l-2 border-border-strong pl-3 text-muted-foreground">
          {children}
        </blockquote>
      );
    },
    // Tables appear in the sample documents, so they have to look deliberate.
    table({ children }) {
      return (
        <div className="my-2 overflow-x-auto scrollbar-thin">
          <table className="w-full border-collapse text-[12.5px]">{children}</table>
        </div>
      );
    },
    th({ children }) {
      return (
        <th className="border border-border bg-surface-2 px-2 py-1 text-left font-semibold">
          {children}
        </th>
      );
    },
    td({ children }) {
      return <td className="border border-border px-2 py-1 align-top">{children}</td>;
    },
    hr() {
      return <hr className="my-3 border-border" />;
    },
  };

  return (
    <div className="text-sm leading-relaxed text-foreground">
      <Markdown remarkPlugins={[remarkGfm]} components={components}>
        {linkifyCitations(answer, sourceCount)}
      </Markdown>
    </div>
  );
});
