"use client";

import { LayoutDashboard, MessageSquare } from "lucide-react";
import { useState } from "react";

import { HeadlampPanel } from "@/components/headlamp-panel";
import { Thread } from "@/components/thread";
import { cn } from "@/lib/utils";

type WorkspacePanel = "chat" | "dashboard";

const mobileTabs: Array<{
  id: WorkspacePanel;
  label: string;
  icon: typeof MessageSquare;
}> = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
];

export function InfrastructureWorkspace() {
  const [activePanel, setActivePanel] = useState<WorkspacePanel>("chat");

  return (
    <main className="bg-background flex h-dvh min-h-0 flex-col overflow-hidden">
      <nav
        className="bg-background grid h-12 shrink-0 grid-cols-2 border-b lg:hidden"
        aria-label="Workspace panels"
      >
        {mobileTabs.map(({ id, label, icon: Icon }) => {
          const isActive = activePanel === id;

          return (
            <button
              key={id}
              type="button"
              onClick={() => setActivePanel(id)}
              className={cn(
                "relative flex items-center justify-center gap-2 text-sm font-medium transition-colors",
                isActive
                  ? "text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
              aria-pressed={isActive}
            >
              <Icon className="size-4" />
              {label}
              {isActive && (
                <span className="bg-primary absolute inset-x-6 bottom-0 h-0.5 rounded-full" />
              )}
            </button>
          );
        })}
      </nav>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <section
          className={cn(
            "min-h-0 min-w-0 overflow-hidden",
            activePanel !== "chat" && "hidden lg:block",
          )}
          aria-label="ChatOps assistant"
        >
          <Thread />
        </section>

        <div
          className={cn(
            "min-h-0 min-w-0 overflow-hidden border-l",
            activePanel !== "dashboard" && "hidden lg:block",
          )}
        >
          <HeadlampPanel />
        </div>
      </div>
    </main>
  );
}
