"use client";

import { Menu, Sparkles } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { ChatThread } from "@/components/chat/chat-thread";
import { Composer } from "@/components/chat/composer";
import { HealthPill } from "@/components/health-pill";
import { Sidebar } from "@/components/sidebar";
import { ThemeToggle } from "@/components/theme/theme-toggle";
import { IconButton } from "@/components/ui/button";
import { useChat } from "@/hooks/use-chat";
import { useDocuments } from "@/hooks/use-documents";

export default function Page() {
  const documents = useDocuments();
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const readyDocuments = useMemo(
    () => documents.documents.filter((document) => document.status === "ready"),
    [documents.documents],
  );

  // A selection can outlive the document it points at (deleted mid-session).
  const activeSelection = useMemo(
    () =>
      selectedDocumentIds.filter((id) =>
        readyDocuments.some((document) => document.id === id),
      ),
    [selectedDocumentIds, readyDocuments],
  );

  const chat = useChat({ documentIds: activeSelection });

  const toggleDocument = useCallback((id: string) => {
    setSelectedDocumentIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  }, []);

  const ask = useCallback(
    (question: string) => {
      setDrawerOpen(false);
      void chat.send(question);
    },
    [chat],
  );

  const scopeLabel =
    activeSelection.length > 0
      ? `Searching ${activeSelection.length} of ${readyDocuments.length} documents`
      : null;

  const sidebar = (
    <Sidebar
      documents={documents}
      conversations={chat.conversations}
      activeConversationId={chat.conversationId}
      selectedDocumentIds={activeSelection}
      onNewChat={() => {
        chat.startNew();
        setDrawerOpen(false);
      }}
      onOpenConversation={(id) => {
        void chat.openConversation(id);
        setDrawerOpen(false);
      }}
      onDeleteConversation={chat.deleteConversation}
      onToggleDocument={toggleDocument}
      onClearDocumentSelection={() => setSelectedDocumentIds([])}
      onClose={() => setDrawerOpen(false)}
    />
  );

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border bg-surface px-3 sm:px-4">
        <IconButton
          label="Open menu"
          onClick={() => setDrawerOpen(true)}
          className="lg:hidden"
        >
          <Menu className="size-4" aria-hidden />
        </IconButton>

        <span
          className="hidden size-7 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground sm:inline-flex"
          aria-hidden
        >
          <Sparkles className="size-4" />
        </span>
        <h1 className="truncate font-display text-sm font-semibold tracking-tight text-foreground sm:text-base">
          AI Knowledge Assistant
        </h1>

        <div className="ml-auto flex items-center gap-2">
          <span className="hidden sm:inline">
            <HealthPill />
          </span>
          <ThemeToggle />
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* Desktop sidebar */}
        <aside className="hidden w-72 shrink-0 border-r border-border bg-surface lg:block xl:w-80">
          {sidebar}
        </aside>

        {/* Mobile drawer */}
        {drawerOpen ? (
          <div className="fixed inset-0 z-40 flex lg:hidden">
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setDrawerOpen(false)}
              className="absolute inset-0 cursor-default bg-black/30 backdrop-blur-[1px]"
            />
            <aside className="animate-rise relative h-full w-[86%] max-w-sm border-r border-border bg-surface shadow-2xl">
              {sidebar}
            </aside>
          </div>
        ) : null}

        <main className="flex min-w-0 flex-1 flex-col">
          <ChatThread
            turns={chat.turns}
            busy={chat.busy}
            loadingHistory={chat.loadingHistory}
            hasDocuments={readyDocuments.length > 0}
            onAsk={ask}
          />
          <Composer
            onSend={ask}
            onStop={chat.stop}
            busy={chat.busy}
            disabled={readyDocuments.length === 0 && documents.documents.length === 0}
            scopeLabel={scopeLabel}
          />
        </main>
      </div>
    </div>
  );
}
