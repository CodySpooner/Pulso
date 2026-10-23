"use client";

import { useRef, useState } from "react";
import { RotateCw } from "lucide-react";

import { PageHeader } from "@/components/pulso/page-header";
import { Button } from "@/components/ui/button";
import { formatAgo, formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useHost, useRefreshAdmin, useSources } from "./api";
import { PanelError } from "./atoms";
import { CoveragePanel } from "./coverage";
import { ImportPanel } from "./import-panel";
import { hostState } from "./model";
import { RunDrawer } from "./run-drawer";
import { SourcesPanel } from "./sources-table";
import { BackupCard, HostCard } from "./summary-cards";

// DH-2 (vault Features/Data Health): the collection cockpit. Every panel loads, fails and retries on its own;
// only "API unreachable" replaces the page. Relative times are measured from the fetch ("as of").
export function DataHealth() {
  const sources = useSources();
  const host = useHost();
  const refresh = useRefreshAdmin();
  const [openKey, setOpenKey] = useState<string | null>(null);
  const opener = useRef<HTMLElement | null>(null); // the drawer has no Radix trigger, so focus returns here
  const openRuns = (key: string) => {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setOpenKey(key);
  };
  const now = Math.max(sources.dataUpdatedAt, host.dataUpdatedAt);
  const fetching = sources.isFetching || host.isFetching;

  const header = (
    <PageHeader
      title="Data Health"
      description="Every source's runs, freshness and gaps, the collector host and backups."
      meta={
        now > 0 && (
          <span title="Fetched from GET /v1/admin/* · refetches every 5 min">
            As of <time dateTime={new Date(now).toISOString()}>{formatUtc(new Date(now).toISOString())}</time>
          </span>
        )
      }
      actions={
        <Button variant="secondary" onClick={() => void refresh()} aria-disabled={fetching} className="aria-disabled:pointer-events-auto">
          <RotateCw className={cn(fetching && "motion-safe:animate-spin")} aria-hidden />
          {fetching ? "Refreshing…" : "Refresh"}
        </Button>
      }
    />
  );

  // Both core calls failed without an API answer: the API (on the home PC) is down, not a collector.
  if (sources.isError && host.isError) {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <section className="rounded-xl border border-border bg-card shadow-card">
          <PanelError title="Can't reach the API" error={sources.error} retry={() => void refresh()} className="py-12" />
        </section>
      </div>
    );
  }

  const state = host.data && hostState(host.data, now);
  const heartbeat = host.data?.latest_heartbeat;

  return (
    <div className="flex flex-col gap-6">
      {header}

      {heartbeat && (state === "late" || state === "offline") && (
        <div
          className={cn(
            "rounded-lg border px-4 py-3 text-data",
            state === "offline" ? "border-negative/40 bg-negative-muted text-foreground" : "border-warning/40 bg-warning-muted text-foreground",
          )}
        >
          <span className={cn("font-medium", state === "offline" ? "text-negative" : "text-warning")}>
            Collector host {state === "offline" ? "offline" : "late"}
          </span>
          : last heartbeat {formatAgo(heartbeat.at, now)} ({formatUtc(heartbeat.at)}). Scheduled runs are being missed and show as gaps below.
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <HostCard now={now} />
        <BackupCard now={now} />
      </div>

      <SourcesPanel now={now} onOpen={openRuns} />
      <CoveragePanel now={now} />
      <ImportPanel onOpen={openRuns} />

      <RunDrawer source={sources.data?.find((s) => s.key === openKey) ?? null} now={now} onClose={() => setOpenKey(null)} returnFocusRef={opener} />
    </div>
  );
}
