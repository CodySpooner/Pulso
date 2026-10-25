"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Download, LoaderCircle, TriangleAlert } from "lucide-react";

import { TapTooltip } from "@/components/data-health/atoms";
import { CopyButton } from "@/components/pulso/copy-button";
import { Button } from "@/components/ui/button";
import { fetchClient, isProblem, type Problem } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import type { apiQuery } from "./url-state";

type Step =
  | { step: "idle" }
  | { step: "preparing"; rows: number | null } // null until the API has counted
  | { step: "done"; file: string }
  | { step: "failed"; problem: Problem | null };

const IDLE: Step = { step: "idle" };
const API_DOWN = "The Pulso API didn't answer. When it runs on your PC, this also means the PC is off.";
// Locked with a token, not opacity, so its focus ring keeps 3:1 (DEC-185, DEC-206).
const LOCKED = "aria-disabled:pointer-events-auto aria-disabled:cursor-not-allowed aria-disabled:text-subtle-foreground aria-disabled:opacity-100";

export const preparing = (rows: number | null) =>
  rows === null ? "Preparing export…" : `Preparing ${rows.toLocaleString("en-US")} ${rows === 1 ? "row" : "rows"}…`;

/** The file name the API gives in Content-Disposition, e.g. pulso_discover_2026-10-25.csv. */
export const attachment = (header: string | null) => /filename="([^"]+)"/.exec(header ?? "")?.[1] ?? null;

function save(blob: Blob, file: string) {
  const url = URL.createObjectURL(blob);
  Object.assign(document.createElement("a"), { href: url, download: file }).click();
  setTimeout(() => URL.revokeObjectURL(url), 60_000); // ponytail: ample for any browser to start the download
}

/** Every row of the feed's query as the API's CSV (WF-7, DEC-316): the API counts, then streams the file. */
export function useCsvExport(query: ReturnType<typeof apiQuery>) {
  const key = JSON.stringify(query);
  const [outcome, setOutcome] = useState<{ key: string; step: Step }>({ key, step: IDLE });
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  // Another query starts clean: an over-cap error was about the old filters.
  const step = outcome.key === key ? outcome.step : IDLE;
  const run = async () => {
    if (step.step === "preparing") return;
    controller.current?.abort();
    const { signal } = (controller.current = new AbortController());
    const set = (next: Step) => setOutcome({ key, step: next });
    set({ step: "preparing", rows: null });
    try {
      const { data, error, response } = await fetchClient.GET("/v1/products", {
        params: { query: { ...query, format: "csv" } },
        parseAs: "stream",
        signal,
      });
      if (!data) {
        set({ step: "failed", problem: isProblem(error) ? error : null });
        return;
      }
      const rows = Number(response.headers.get("X-Total-Count") ?? NaN);
      set({ step: "preparing", rows: Number.isInteger(rows) ? rows : null });
      const blob = await new Response(data).blob();
      const done: Step = { step: "done", file: attachment(response.headers.get("Content-Disposition")) ?? "pulso_discover.csv" };
      save(blob, done.file);
      set(done);
      setTimeout(() => setOutcome((o) => (o.step === done ? { key, step: IDLE } : o)), 2500);
    } catch {
      if (!signal.aborted) set({ step: "failed", problem: null });
    }
  };
  return { step, run };
}

/** Export CSV for the feed's toolbar, with its one polite status and, after a failure, one alert. */
export function ExportCsv({ csv: { step, run }, empty }: { csv: ReturnType<typeof useCsvExport>; empty: boolean }) {
  const button = useRef<HTMLButtonElement>(null);
  const busy = step.step === "preparing";
  const problem = step.step === "failed" ? step.problem : null;
  const Icon = busy ? LoaderCircle : step.step === "done" ? Check : Download;
  return (
    <>
      <TapTooltip hint={empty ? "Nothing to export" : null} asChild>
        <Button
          ref={button}
          size="sm"
          aria-disabled={empty || busy}
          aria-keyshortcuts="E"
          className={cn(LOCKED, "tabular-nums")}
          onClick={() => !empty && void run()}
        >
          <Icon className={cn(busy && "motion-safe:animate-spin", step.step === "done" && "text-positive")} aria-hidden />
          {busy ? (
            // A phone keeps the label as wide as "Export CSV", so the count line never reflows; the status says N.
            <>
              <span className="sm:hidden">Preparing…</span>
              <span className="max-sm:hidden">{preparing(step.rows)}</span>
            </>
          ) : step.step === "done" ? (
            "Downloaded"
          ) : (
            "Export CSV"
          )}
        </Button>
      </TapTooltip>
      <span role="status" className="sr-only">
        {busy ? preparing(step.rows) : step.step === "done" ? `Downloaded ${step.file}` : ""}
      </span>
      {step.step === "failed" &&
        (problem?.code === "export_too_large" ? (
          // Nothing to retry: the filters must narrow, and a new query clears this.
          <p role="alert" className="basis-full rounded-lg border border-warning/40 bg-warning-muted px-3 py-2 text-data text-foreground">
            <TriangleAlert className="mr-1.5 inline size-3.5 align-[-2px] text-warning" aria-hidden />
            {problem.detail}
          </p>
        ) : (
          <div className="flex basis-full flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-negative/40 bg-negative-muted px-3 py-2">
            <p role="alert" className="mr-auto text-data text-foreground">
              <TriangleAlert className="mr-1.5 inline size-3.5 align-[-2px] text-negative" aria-hidden />
              <span className="font-medium">Couldn&apos;t export.</span>{" "}
              {problem ? (
                <>
                  {problem.detail} <span className="font-mono text-label text-subtle-foreground">Error ID {problem.request_id}</span>
                </>
              ) : (
                API_DOWN
              )}
            </p>
            {problem && <CopyButton value={problem.request_id} label="Copy error ID" />}
            <Button
              size="sm"
              variant="primary"
              onClick={() => {
                button.current?.focus(); // Retry leaves with the line; focus goes back to Export CSV
                void run();
              }}
            >
              Retry
            </Button>
          </div>
        ))}
    </>
  );
}
