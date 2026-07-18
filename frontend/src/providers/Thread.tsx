import { validate } from "uuid";
import { Thread } from "@langchain/langgraph-sdk";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { createClient } from "./client";

const THREAD_PAGE_SIZE = 30;

interface ThreadContextType {
  threads: Thread[];
  threadsLoading: boolean;
  threadsLoadingMore: boolean;
  threadsError: string | null;
  hasMoreThreads: boolean;
  refreshThreads: () => Promise<Thread[]>;
  loadMoreThreads: () => Promise<void>;
}

const ThreadContext = createContext<ThreadContextType | undefined>(undefined);

function getThreadSearchMetadata(
  assistantId: string,
): { graph_id: string } | { assistant_id: string } {
  return validate(assistantId)
    ? { assistant_id: assistantId }
    : { graph_id: assistantId };
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Unable to load conversations";
}

export function ThreadProvider({ children }: { children: ReactNode }) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL?.trim() ?? "";
  const assistantId = process.env.NEXT_PUBLIC_ASSISTANT_ID?.trim() ?? "";
  const [threads, setThreads] = useState<Thread[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(false);
  const [threadsLoadingMore, setThreadsLoadingMore] = useState(false);
  const [threadsError, setThreadsError] = useState<string | null>(null);
  const [hasMoreThreads, setHasMoreThreads] = useState(false);

  const getThreadPage = useCallback(
    async (offset: number): Promise<Thread[]> => {
      if (!apiUrl || !assistantId) return [];

      const client = createClient(apiUrl);
      return client.threads.search({
        metadata: getThreadSearchMetadata(assistantId),
        limit: THREAD_PAGE_SIZE,
        offset,
        sortBy: "updated_at",
        sortOrder: "desc",
      });
    },
    [apiUrl, assistantId],
  );

  const refreshThreads = useCallback(async (): Promise<Thread[]> => {
    setThreadsLoading(true);
    setThreadsError(null);

    try {
      const firstPage = await getThreadPage(0);
      setThreads(firstPage);
      setHasMoreThreads(firstPage.length === THREAD_PAGE_SIZE);
      return firstPage;
    } catch (error) {
      setThreadsError(getErrorMessage(error));
      throw error;
    } finally {
      setThreadsLoading(false);
    }
  }, [getThreadPage]);

  const loadMoreThreads = useCallback(async (): Promise<void> => {
    if (threadsLoadingMore || !hasMoreThreads) return;

    setThreadsLoadingMore(true);
    setThreadsError(null);

    try {
      const nextPage = await getThreadPage(threads.length);
      setThreads((current) => {
        const knownIds = new Set(current.map((thread) => thread.thread_id));
        return [
          ...current,
          ...nextPage.filter((thread) => !knownIds.has(thread.thread_id)),
        ];
      });
      setHasMoreThreads(nextPage.length === THREAD_PAGE_SIZE);
    } catch (error) {
      setThreadsError(getErrorMessage(error));
      throw error;
    } finally {
      setThreadsLoadingMore(false);
    }
  }, [getThreadPage, hasMoreThreads, threads.length, threadsLoadingMore]);

  const value = useMemo(
    () => ({
      threads,
      threadsLoading,
      threadsLoadingMore,
      threadsError,
      hasMoreThreads,
      refreshThreads,
      loadMoreThreads,
    }),
    [
      hasMoreThreads,
      loadMoreThreads,
      refreshThreads,
      threads,
      threadsError,
      threadsLoading,
      threadsLoadingMore,
    ],
  );

  return (
    <ThreadContext.Provider value={value}>{children}</ThreadContext.Provider>
  );
}

export function useThreads() {
  const context = useContext(ThreadContext);
  if (context === undefined) {
    throw new Error("useThreads must be used within a ThreadProvider");
  }
  return context;
}
