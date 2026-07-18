"use client";

import {
  AlertTriangle,
  ExternalLink,
  LoaderCircle,
  RefreshCw,
  Server,
} from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

type FrameStatus = "loading" | "loaded" | "error";

function resolveHeadlampUrl(rawValue: string | undefined): {
  url?: string;
  error?: string;
} {
  const value = rawValue?.trim();
  if (!value) return {};

  if (value.startsWith("/")) return { url: value };

  try {
    const parsedUrl = new URL(value);
    if (!["http:", "https:"].includes(parsedUrl.protocol)) {
      return { error: "Headlamp must use an HTTP or HTTPS URL." };
    }
    if (parsedUrl.username || parsedUrl.password) {
      return { error: "Do not include credentials in the Headlamp URL." };
    }
    return { url: parsedUrl.toString() };
  } catch {
    return { error: "The configured Headlamp URL is invalid." };
  }
}

const headlampConfiguration = resolveHeadlampUrl(
  process.env.NEXT_PUBLIC_HEADLAMP_URL,
);

const statusPresentation = {
  loading: { label: "Loading Headlamp", color: "bg-sky-500" },
  loaded: { label: "Headlamp loaded", color: "bg-emerald-500" },
  error: { label: "Headlamp unavailable", color: "bg-red-500" },
} satisfies Record<FrameStatus, { label: string; color: string }>;

export function HeadlampPanel() {
  const [frameKey, setFrameKey] = useState(0);
  const [frameStatus, setFrameStatus] = useState<FrameStatus>("loading");
  const { url: headlampUrl, error: configurationError } = headlampConfiguration;
  const presentation = headlampUrl
    ? statusPresentation[frameStatus]
    : {
        label: configurationError ? "Invalid configuration" : "Setup required",
        color: configurationError ? "bg-red-500" : "bg-amber-500",
      };

  const reloadFrame = () => {
    setFrameStatus("loading");
    setFrameKey((key) => key + 1);
  };

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
            <p
              className="text-muted-foreground flex items-center gap-1.5 text-xs"
              aria-live="polite"
            >
              <span className={`size-1.5 rounded-full ${presentation.color}`} />
              {presentation.label}
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
              onClick={reloadFrame}
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
        <div className="relative min-h-0 flex-1">
          <iframe
            key={frameKey}
            src={headlampUrl}
            title="Headlamp Kubernetes dashboard"
            className="bg-background absolute inset-0 size-full border-0"
            referrerPolicy="no-referrer"
            onLoad={() => setFrameStatus("loaded")}
            onError={() => setFrameStatus("error")}
          />

          {frameStatus === "loading" && (
            <div className="bg-background/80 pointer-events-none absolute inset-0 flex items-center justify-center backdrop-blur-[1px]">
              <div className="text-muted-foreground flex items-center gap-2 text-sm">
                <LoaderCircle className="size-4 animate-spin" />
                Loading Kubernetes dashboard…
              </div>
            </div>
          )}

          {frameStatus === "error" && (
            <div className="bg-background absolute inset-0 flex items-center justify-center p-6">
              <div className="max-w-sm text-center">
                <AlertTriangle className="text-destructive mx-auto size-9" />
                <h3 className="mt-3 font-semibold">Headlamp did not load</h3>
                <p className="text-muted-foreground mt-2 text-sm leading-6">
                  Confirm that the port-forward is running and the configured
                  URL is reachable.
                </p>
                <Button
                  type="button"
                  variant="outline"
                  className="mt-4"
                  onClick={reloadFrame}
                >
                  <RefreshCw className="size-4" />
                  Try again
                </Button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-1 items-center justify-center p-6">
          <div className="bg-background max-w-md rounded-xl border p-6 text-center shadow-sm">
            {configurationError ? (
              <AlertTriangle className="text-destructive mx-auto mb-4 size-9" />
            ) : (
              <Server className="text-muted-foreground mx-auto mb-4 size-9" />
            )}
            <h2 className="font-semibold">
              {configurationError
                ? "Fix Headlamp configuration"
                : "Connect Headlamp"}
            </h2>
            <p className="text-muted-foreground mt-2 text-sm leading-6">
              {configurationError ??
                "Port-forward Headlamp to localhost, add the URL to your frontend environment, then restart the development server."}
            </p>
            <code className="bg-muted mt-4 block overflow-x-auto rounded-md p-3 text-left text-xs">
              NEXT_PUBLIC_HEADLAMP_URL=http://localhost:4466
            </code>
          </div>
        </div>
      )}
    </section>
  );
}
