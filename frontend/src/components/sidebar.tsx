"use client";

import { MessageSquarePlus, Trash2, X } from "lucide-react";

import { DocumentsPanel } from "@/components/documents/documents-panel";
import { Button, IconButton } from "@/components/ui/button";
import type { DocumentsState } from "@/hooks/use-documents";
import { cn } from "@/lib/cn";
import { formatRelativeTime } from "@/lib/format";
import type { StoredConversation } from "@/lib/storage";

export interface SidebarProps {
  documents: DocumentsState;
  conversations: StoredConversation[];
  activeConversationId: string | null;
  selectedDocumentIds: string[];
  onNewChat: () => void;
  onOpenConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  onToggleDocument: (id: string) => void;
  onClearDocumentSelection: () => void;
  /** Mobile drawer only. */
  onClose?: () => void;
}

export function Sidebar({
  documents,
  conversations,
  activeConversationId,
  selectedDocumentIds,
  onNewChat,
  onOpenConversation,
  onDeleteConversation,
  onToggleDocument,
  onClearDocumentSelection,
  onClose,
}: SidebarProps) {
  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden px-3 py-3">
      <div className="flex items-center gap-2">
        <Button variant="primary" size="md" className="flex-1" onClick={onNewChat}>
          <MessageSquarePlus className="size-4" aria-hidden />
          New chat
        </Button>
        {onClose ? (
          <IconButton label="Close menu" onClick={onClose} className="lg:hidden">
            <X className="size-4" aria-hidden />
          </IconButton>
        ) : null}
      </div>

      <section className="flex min-h-0 shrink-0 flex-col gap-2" aria-labelledby="chats-heading">
        <h2
          id="chats-heading"
          className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase"
        >
          Chats
        </h2>
        {conversations.length === 0 ? (
          <p className="px-1 text-[11px] leading-5 text-muted-foreground">
            Your conversations appear here. They are kept in this browser only.
          </p>
        ) : (
          <ul className="flex max-h-56 flex-col gap-0.5 overflow-y-auto scrollbar-thin">
            {conversations.map((conversation) => {
              const active = conversation.id === activeConversationId;
              return (
                <li key={conversation.id} className="group/row relative">
                  <button
                    type="button"
                    onClick={() => onOpenConversation(conversation.id)}
                    className={cn(
                      "w-full cursor-pointer rounded-lg py-1.5 pr-8 pl-2 text-left transition-colors duration-200",
                      active
                        ? "bg-primary-soft text-primary"
                        : "text-foreground hover:bg-surface-2",
                    )}
                  >
                    <span className="block truncate text-xs font-medium">
                      {conversation.title}
                    </span>
                    <span
                      className={cn(
                        "block text-[10px]",
                        active ? "text-primary/70" : "text-muted-foreground",
                      )}
                    >
                      {formatRelativeTime(conversation.updatedAt)}
                    </span>
                  </button>
                  <IconButton
                    label={`Delete chat: ${conversation.title}`}
                    onClick={() => onDeleteConversation(conversation.id)}
                    className="absolute top-1 right-0.5 size-7 opacity-0 group-hover/row:opacity-100 focus-visible:opacity-100 hover:text-danger"
                  >
                    <Trash2 className="size-3" aria-hidden />
                  </IconButton>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <div className="h-px shrink-0 bg-border" />

      <DocumentsPanel
        state={documents}
        selectedIds={selectedDocumentIds}
        onToggleSelected={onToggleDocument}
        onClearSelection={onClearDocumentSelection}
      />
    </div>
  );
}
