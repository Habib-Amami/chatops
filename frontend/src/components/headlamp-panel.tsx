"use client";

import { ExternalLink, RefreshCw, Server } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

const headlampUrl = process.env.NEXT_PUBLIC_HEADLAMP_URL?.trim();

export function HeadlampPanel() {
  const [frameKey, setFrameKey] = useState(0);

  return (
    <section className="bg-muted/20 flex h-full min-h-0 flex-col">
      <header className="bg-background flex h-14 shrink-0 items-center justify-between gap-3 border-b px-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="bg-primary/10 text-primary flex size-8 shrink-0 items-center justify-center rounded-lg">
            <Server className="size-4" />
          </span>
          <div className="min-w-0 leading-tight">
            <h2 className="truncate text-sm font-semibold">
              Kubernetes Dashboard
            </h2>
            <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
              <span
                className={`size-1.5 rounded-full ${headlampUrl ? "bg-emerald-500" : "bg-amber-500"}`}
              />
              {headlampUrl ? "Headlamp connected" : "Setup required"}
            </p>
          </div>
        </div>

        {headlampUrl && (
          <div className="flex shrink-0 items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Reload Headlamp"
              title="Reload Headlamp"
              onClick={() => setFrameKey((key) => key + 1)}
            >
              <RefreshCw className="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              asChild
            >
              <a
                href={headlampUrl}
                target="_blank"
                rel="noreferrer"
                aria-label="Open Headlamp in a new tab"
                title="Open Headlamp in a new tab"
              >
                <ExternalLink className="size-4" />
              </a>
            </Button>
          </div>
        )}
      </header>

      {headlampUrl ? (
        <iframe
          key={frameKey}
          src={headlampUrl}
          title="Headlamp Kubernetes dashboard"
          className="bg-background min-h-0 flex-1 border-0"
          referrerPolicy="same-origin"
        />
      ) : (
        <div className="flex flex-1 items-center justify-center p-6">
          <div className="bg-background max-w-md rounded-xl border p-6 text-center shadow-sm">
            <Server className="text-muted-foreground mx-auto mb-4 size-9" />
            <h2 className="font-semibold">Connect Headlamp</h2>
            <p className="text-muted-foreground mt-2 text-sm leading-6">
              Add the URL returned by Minikube to your frontend environment,
              then restart the development server.
            </p>
            <code className="bg-muted mt-4 block overflow-x-auto rounded-md p-3 text-left text-xs">
              NEXT_PUBLIC_HEADLAMP_URL=http://192.168.49.2:PORT
            </code>
          </div>
        </div>
      )}
    </section>
  );
}
