"use client";

import { useRef, useState } from "react";
import { RotateCw, Upload } from "lucide-react";

import { PageHeader } from "@/components/pulso/page-header";
import { Button } from "@/components/ui/button";
import { formatAgo, formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useHost, useRefreshAdmin, useSources } from "./api";
import { Panel, PanelError } from "./atoms";
import { CoveragePanel } from "./coverage";
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
      <ImportPanel />

      <RunDrawer source={sources.data?.find((s) => s.key === openKey) ?? null} now={now} onClose={() => setOpenKey(null)} returnFocusRef={opener} />
    </div>
  );
}

// P1-11b (the import endpoints) isn't merged, so the schema has no import operation: a designed disabled state.
function ImportPanel() {
  return (
    <Panel id="import" title="CSV import" note="Every source has a CSV fallback (§4.2)">
      <div className="m-4 flex flex-col items-center gap-3 rounded-lg border border-dashed border-border-strong px-5 py-4 text-center sm:flex-row sm:text-left">
        <div className="grid size-10 shrink-0 place-items-center rounded-lg border border-border bg-secondary text-muted-foreground">
          <Upload className="size-5" aria-hidden />
        </div>
        <div className="flex flex-col gap-0.5">
          <h3 className="text-body font-medium text-foreground">Import arrives with P1-11b</h3>
          <p className="max-w-[72ch] text-data text-muted-foreground">
            The template, preview and commit endpoints aren&apos;t in this build&apos;s API yet. Once they are, you drop a CSV here and see
            the preview before anything is written.
          </p>
        </div>
        <Button variant="secondary" size="sm" disabled className="sm:ml-auto">
          Choose CSV…
        </Button>
      </div>
    </Panel>
  );
}
