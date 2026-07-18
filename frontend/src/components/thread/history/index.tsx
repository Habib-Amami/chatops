import { Thread } from "@langchain/langgraph-sdk";
import { LoaderCircle, PanelRightClose, Search } from "lucide-react";
import { parseAsBoolean, useQueryState } from "nuqs";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { cn } from "@/lib/utils";
import { useThreads } from "@/providers/Thread";

import { getContentString } from "../utils";

function getThreadLabel(thread: Thread): string {
  if (
    typeof thread.values === "object" &&
    thread.values &&
    "messages" in thread.values &&
    Array.isArray(thread.values.messages) &&
    thread.values.messages.length > 0
  ) {
    const label = getContentString(thread.values.messages[0].content).trim();
    if (label) return label;
  }

  return `Conversation ${thread.thread_id.slice(0, 8)}`;
}

function ThreadList({
  threads,
  onThreadClick,
}: {
  threads: Thread[];
  onThreadClick?: () => void;
}) {
  const [threadId, setThreadId] = useQueryState("threadId");

  if (threads.length === 0) {
    return (
      <p className="text-muted-foreground px-4 py-8 text-center text-sm">
        No conversations found.
      </p>
    );
  }

  return (
    <div className="flex w-full flex-col gap-1">
      {threads.map((thread) => {
        const isActive = thread.thread_id === threadId;

        return (
          <Button
            key={thread.thread_id}
            variant={isActive ? "secondary" : "ghost"}
            className={cn(
              "h-auto w-full justify-start px-3 py-2 text-left font-normal",
              isActive && "font-medium",
            )}
            aria-current={isActive ? "page" : undefined}
            onClick={() => {
              onThreadClick?.();
              if (!isActive) void setThreadId(thread.thread_id);
            }}
          >
            <span className="block min-w-0 truncate">
              {getThreadLabel(thread)}
            </span>
          </Button>
        );
      })}
    </div>
  );
}

function ThreadHistoryLoading() {
  return (
    <div className="flex w-full flex-col gap-2 px-3">
      {Array.from({ length: 8 }).map((_, index) => (
        <Skeleton
          key={`thread-skeleton-${index}`}
          className="h-9 w-full"
        />
      ))}
    </div>
  );
}

function HistoryContent({ onThreadClick }: { onThreadClick?: () => void }) {
  const [searchQuery, setSearchQuery] = useState("");
  const {
    threads,
    threadsLoading,
    threadsLoadingMore,
    threadsError,
    hasMoreThreads,
    refreshThreads,
    loadMoreThreads,
  } = useThreads();

  const filteredThreads = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();
    if (!normalizedQuery) return threads;

    return threads.filter((thread) =>
      getThreadLabel(thread).toLowerCase().includes(normalizedQuery),
    );
  }, [searchQuery, threads]);

  return (
    <div className="flex min-h-0 w-full flex-1 flex-col gap-3 px-3 pb-3">
      <div className="relative">
        <Search className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
        <Input
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder="Search loaded conversations"
          aria-label="Search conversations"
          className="pl-9"
        />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {threadsLoading ? (
          <ThreadHistoryLoading />
        ) : (
          <ThreadList
            threads={filteredThreads}
            onThreadClick={onThreadClick}
          />
        )}
      </div>

      {threadsError && (
        <div className="border-destructive/30 bg-destructive/5 rounded-md border p-3 text-sm">
          <p className="text-destructive">Could not load conversations.</p>
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-auto p-0"
            onClick={() => void refreshThreads().catch(() => undefined)}
          >
            Try again
          </Button>
        </div>
      )}

      {hasMoreThreads && !searchQuery && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={threadsLoadingMore}
          onClick={() => void loadMoreThreads().catch(() => undefined)}
        >
          {threadsLoadingMore && (
            <LoaderCircle className="size-4 animate-spin" />
          )}
          Load more
        </Button>
      )}
    </div>
  );
}

export default function ThreadHistory() {
  const isLargeScreen = useMediaQuery("(min-width: 1024px)");
  const [chatHistoryOpen, setChatHistoryOpen] = useQueryState(
    "chatHistoryOpen",
    parseAsBoolean.withDefault(false),
  );
  const { refreshThreads } = useThreads();

  useEffect(() => {
    void refreshThreads().catch(() => undefined);
  }, [refreshThreads]);

  return (
    <>
      <aside className="bg-background hidden h-full w-[300px] flex-col border-r shadow-xl lg:flex">
        <header className="flex h-14 shrink-0 items-center justify-between border-b px-3">
          <h2 className="font-semibold">Conversations</h2>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Close conversation history"
            onClick={() => setChatHistoryOpen(false)}
          >
            <PanelRightClose className="size-5" />
          </Button>
        </header>
        <HistoryContent />
      </aside>

      <Sheet
        open={Boolean(chatHistoryOpen) && !isLargeScreen}
        onOpenChange={(open) => {
          if (!isLargeScreen) void setChatHistoryOpen(open);
        }}
      >
        <SheetContent
          side="left"
          className="flex w-[min(340px,90vw)] flex-col p-0 lg:hidden"
        >
          <SheetHeader className="border-b px-4 py-4">
            <SheetTitle>Conversations</SheetTitle>
          </SheetHeader>
          <HistoryContent onThreadClick={() => setChatHistoryOpen(false)} />
        </SheetContent>
      </Sheet>
    </>
  );
}
