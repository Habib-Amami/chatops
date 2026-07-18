import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useStream } from "@langchain/langgraph-sdk/react";
import { type Message } from "@langchain/langgraph-sdk";
import {
  isRemoveUIMessage,
  isUIMessage,
  uiMessageReducer,
  type RemoveUIMessage,
  type UIMessage,
} from "@langchain/langgraph-sdk/react-ui";
import { useQueryState } from "nuqs";
import { toast } from "sonner";

import { BrandLogo } from "@/components/brand-logo";
import { useThreads } from "./Thread";

export type StateType = { messages: Message[]; ui?: UIMessage[] };

const useTypedStream = useStream<
  StateType,
  {
    UpdateType: {
      messages?: Message[] | Message | string;
      ui?: (UIMessage | RemoveUIMessage)[] | UIMessage | RemoveUIMessage;
      context?: Record<string, unknown>;
    };
    CustomEventType: UIMessage | RemoveUIMessage;
  }
>;

type StreamContextType = ReturnType<typeof useTypedStream>;
const StreamContext = createContext<StreamContextType | undefined>(undefined);

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function checkGraphStatus(apiUrl: string): Promise<boolean> {
  try {
    const response = await fetch(`${apiUrl.replace(/\/$/, "")}/info`);
    return response.ok;
  } catch {
    return false;
  }
}

const StreamSession = ({
  children,
  apiUrl,
  assistantId,
}: {
  children: ReactNode;
  apiUrl: string;
  assistantId: string;
}) => {
  const [threadId, setThreadId] = useQueryState("threadId");
  const { refreshThreads } = useThreads();

  const streamValue = useTypedStream({
    apiUrl,
    assistantId,
    threadId: threadId ?? null,
    fetchStateHistory: true,
    onCustomEvent: (event, options) => {
      if (isUIMessage(event) || isRemoveUIMessage(event)) {
        options.mutate((previous) => ({
          ...previous,
          ui: uiMessageReducer(previous.ui ?? [], event),
        }));
      }
    },
    onThreadId: (id) => {
      void setThreadId(id);

      void (async () => {
        for (let attempt = 0; attempt < 3; attempt += 1) {
          const refreshedThreads = await refreshThreads();
          if (refreshedThreads.some((thread) => thread.thread_id === id))
            return;
          if (attempt < 2) await delay(500);
        }
      })().catch(() => undefined);
    },
  });

  useEffect(() => {
    void checkGraphStatus(apiUrl).then((connected) => {
      if (!connected) {
        toast.error("Failed to connect to the LangGraph server", {
          description: () => (
            <p>
              Confirm that the graph is running and reachable at{" "}
              <code>{apiUrl}</code>.
            </p>
          ),
          duration: 10000,
          richColors: true,
          closeButton: true,
        });
      }
    });
  }, [apiUrl]);

  return (
    <StreamContext.Provider value={streamValue}>
      {children}
    </StreamContext.Provider>
  );
};

function ConfigurationError() {
  return (
    <main className="bg-muted/30 flex min-h-screen w-full items-center justify-center p-4">
      <section className="bg-background w-full max-w-lg rounded-xl border p-6 shadow-sm">
        <BrandLogo
          className="h-9"
          priority
        />
        <h1 className="mt-5 text-xl font-semibold">
          ChatOps frontend is not configured
        </h1>
        <p className="text-muted-foreground mt-2 text-sm leading-6">
          Configure the LangGraph endpoint and graph ID in an untracked frontend{" "}
          <code>.env</code> file, then restart the frontend.
        </p>
        <pre className="bg-muted mt-4 overflow-x-auto rounded-md p-4 text-xs">
          <code>{`NEXT_PUBLIC_API_URL=http://localhost:2024\nNEXT_PUBLIC_ASSISTANT_ID=agent`}</code>
        </pre>
        <p className="text-muted-foreground mt-4 text-xs leading-5">
          For production, point the public URL to the server-side API proxy so
          deployment credentials are never stored in the browser.
        </p>
      </section>
    </main>
  );
}

export function StreamProvider({ children }: { children: ReactNode }) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL?.trim();
  const assistantId = process.env.NEXT_PUBLIC_ASSISTANT_ID?.trim();

  if (!apiUrl || !assistantId) return <ConfigurationError />;

  return (
    <StreamSession
      apiUrl={apiUrl}
      assistantId={assistantId}
    >
      {children}
    </StreamSession>
  );
}

export function useStreamContext(): StreamContextType {
  const context = useContext(StreamContext);
  if (context === undefined) {
    throw new Error("useStreamContext must be used within a StreamProvider");
  }
  return context;
}
