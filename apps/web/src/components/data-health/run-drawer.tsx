"use client";

import { useState } from "react";
import { ChevronRight, History } from "lucide-react";

import { EmptyState } from "@/components/pulso/empty-state";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useHost, useMoreTargets, useRunDetail, useSourceRuns } from "./api";
import { Ago, Missing, PanelError, runStatus, StatePill } from "./atoms";
import { LoadMore } from "./load-more";
import { skipNote, sourceState, targetsNote, type Run, type SourceHealth } from "./model";

const RUNS_API = "GET /v1/admin/runs";

const runTone = (status: string) =>
  status === "failed" || status === "blocked" ? "text-negative" : status === "partial" ? "text-warning" : "text-muted-foreground";

// Source drawer (vault Features/Data Health): the source's every DH-1 field, then its runs newest first.
// The newest run opens expanded, so a failing source's error is one click from the table.
export function RunDrawer({
  source,
  now,
  onClose,
  returnFocusRef,
}: {
  source: SourceHealth | null;
  now: number;
  onClose: () => void;
  returnFocusRef: React.RefObject<HTMLElement | null>;
}) {
  return (
    <Sheet open={source != null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        closeLabel="Close runs"
        // Focus the drawer itself: its first control is the status pill, and focus would open the pill's hint.
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          (e.currentTarget as HTMLElement).focus();
        }}
        onCloseAutoFocus={(e) => {
          e.preventDefault();
          returnFocusRef.current?.focus();
        }}
      >
        {source && <DrawerBody source={source} now={now} />}
      </SheetContent>
    </Sheet>
  );
}

function DrawerBody({ source, now }: { source: SourceHealth; now: number }) {
  const host = useHost();
  const runs = useSourceRuns(source.key);
  const items = runs.data?.pages.flatMap((p) => p.items) ?? [];
  const quota = source.quota_limit != null ? `${source.quota_used?.toLocaleString("en-US") ?? "—"} / ${source.quota_limit.toLocaleString("en-US")}` : null;

  return (
    <>
      <div className="flex flex-col gap-2 border-b border-border-subtle px-5 pt-4 pb-4">
        <div className="flex items-center gap-2 pr-10">
          <SheetTitle className="truncate text-title-2 font-semibold text-foreground">{source.name}</SheetTitle>
          <StatePill state={sourceState(source, host.data?.latest_gap_ends ?? {}, now)} />
        </div>
        <SheetDescription className="text-data text-muted-foreground">Source settings and runs, newest first. All times UTC.</SheetDescription>
        <dl className="zone-data mt-1 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <Fact label="Key">
            <span className="font-mono">{source.key}</span>
          </Fact>
          <Fact label="Type · phase">
            {source.type} · Phase {source.phase}
          </Fact>
          <Fact label="Status">
            {source.status}
            {source.enabled ? " · enabled" : " · disabled"}
            {source.disabled_at && (
              <span className="text-muted-foreground">
                {" "}
                since <span className="whitespace-nowrap">{formatUtc(source.disabled_at)}</span>
              </span>
            )}
          </Fact>
          {source.disabled_reason && <Fact label="Reason">{source.disabled_reason}</Fact>}
          <Fact label="Retry not before">{source.retry_not_before ? formatUtc(source.retry_not_before) : <Missing reason="No retry deadline" />}</Fact>
          <Fact label="Last code">
            {source.last_status_code != null ? <span className="font-mono">{source.last_status_code}</span> : <Missing reason="No response recorded yet" />}
          </Fact>
          <Fact label="Freshness">
            {source.freshness ? <Ago iso={source.freshness} now={now} source="Last successful target · GET /v1/admin/sources" /> : <Missing reason="Not collected yet" />}
          </Fact>
          <Fact label="Seed list">
            {source.seed_approved == null ? (
              <Missing reason="This source has no seed list" />
            ) : (
              <>
                {source.seed_approved ? "Approved" : "Not approved"}
                {source.approved_targets != null && <span className="text-muted-foreground"> · {source.approved_targets.toLocaleString("en-US")} approved targets</span>}
              </>
            )}
          </Fact>
          <Fact label="Quota">{quota ?? <Missing reason="No source yet: quota usage isn't persisted" />}</Fact>
        </dl>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {runs.isPending ? (
          <div className="flex flex-col gap-2">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : runs.isError ? (
          <PanelError title="Couldn't load runs" error={runs.error} retry={() => runs.refetch()} />
        ) : items.length === 0 ? (
          <EmptyState icon={History} size="sm" title="No runs yet">
            Runs appear here when the collector host runs this source, or when you press Run now.
          </EmptyState>
        ) : (
          <ol aria-label={`${source.name} runs`} className="flex flex-col gap-2">
            {items.map((run, i) => (
              <RunItem key={run.id} run={run} now={now} defaultOpen={i === 0} />
            ))}
          </ol>
        )}
        {runs.hasNextPage && (
          <Button variant="ghost" size="sm" className="mt-3" onClick={() => runs.fetchNextPage()} aria-disabled={runs.isFetchingNextPage}>
            {runs.isFetchingNextPage ? "Loading…" : "Load older runs"}
          </Button>
        )}
      </div>
    </>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      {/* Wrap, never truncate: touch has no hover to read a clipped value (imp-098). */}
      <dd className="min-w-0 wrap-break-word text-foreground">{children}</dd>
    </>
  );
}

function RunItem({ run, now, defaultOpen }: { run: Run; now: number; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <li className="rounded-lg border border-border-subtle">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-data hover:bg-accent pointer-coarse:min-h-11"
      >
        <ChevronRight className={cn("size-4 shrink-0 text-subtle-foreground transition-transform duration-(--duration-fast)", open && "rotate-90")} aria-hidden />
        <span className="font-mono text-subtle-foreground">#{run.id}</span>
        <span className={cn("font-medium", runTone(run.status))}>{runStatus(run.status)}</span>
        <span className="text-subtle-foreground">· {run.trigger}</span>
        <span className="ml-auto text-muted-foreground">
          <Ago iso={run.finished_at ?? run.started_at ?? run.queued_at} now={now} source={RUNS_API} />
        </span>
      </button>
      {open && <RunDetailView run={run} />}
    </li>
  );
}

function RunDetailView({ run }: { run: Run }) {
  const detail = useRunDetail(run.id);
  const more = useMoreTargets(run.id, detail.data?.next_cursor ?? null);
  const targets = detail.data ? [detail.data.targets, ...more.pages.map((p) => p.targets)].flat() : [];
  const skipped = run.error_code === "slot_suppressed"; // a skip, not a failure (imp-042)
  return (
    <div className="flex flex-col gap-3 border-t border-border-subtle px-3 py-3">
      {run.error_message || run.error_code ? (
        <div className={cn("rounded-md px-3 py-2 text-data text-foreground", skipped ? "bg-warning-muted" : "bg-negative-muted")}>
          {run.error_code && <span className={cn("font-mono", skipped ? "text-warning" : "text-negative")}>{run.error_code} </span>}
          {skipped ? `${skipNote(run)}.` : run.error_message}
        </div>
      ) : null}
      <dl className="zone-data grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
        <Fact label="Rows">
          <span className="tabular-nums">
            {/* Non-breaking spaces keep each count with its unit; lines break only after a "·". */}
            {run.rows_fetched.toLocaleString("en-US")}&nbsp;fetched&nbsp;· {run.rows_inserted.toLocaleString("en-US")}&nbsp;inserted&nbsp;·{" "}
            {run.rows_updated.toLocaleString("en-US")}&nbsp;updated&nbsp;· {run.rows_unchanged.toLocaleString("en-US")}&nbsp;unchanged
          </span>
        </Fact>
        <Fact label="Targets">
          <span className="tabular-nums">
            {run.successful_target_count.toLocaleString("en-US")} of {run.target_count.toLocaleString("en-US")} succeeded{run.complete ? "" : " · incomplete"}
          </span>
        </Fact>
        <Fact label="Requests">
          <span className="tabular-nums">{run.http_requests.toLocaleString("en-US")}</span>
          {run.last_status_code != null && <span className="text-muted-foreground"> · last code {run.last_status_code}</span>}
        </Fact>
        <Fact label="Queued">{formatUtc(run.queued_at)}</Fact>
        <Fact label="Started">{run.started_at ? formatUtc(run.started_at) : <Missing reason="Not started" />}</Fact>
        <Fact label="Finished">{run.finished_at ? formatUtc(run.finished_at) : <Missing reason="Not finished" />}</Fact>
        <Fact label="Host · slot">
          {run.host ?? <Missing reason="No host recorded" />} · {run.slot_key ?? <Missing reason="Not a scheduled slot" />}
        </Fact>
      </dl>

      {detail.isPending ? (
        <Skeleton className="h-16 w-full" />
      ) : detail.isError ? (
        <PanelError title="Couldn't load targets" error={detail.error} retry={() => detail.refetch()} />
      ) : targets.length === 0 ? (
        <p className="text-label text-muted-foreground">No targets recorded for this run.</p>
      ) : (
        <div role="region" aria-label={`Run ${run.id} targets`} tabIndex={0} className="relative overflow-x-auto">
          <table className="zone-data w-full">
            <thead>
              <tr className="text-left text-label text-muted-foreground">
                <th scope="col" className="h-7 pr-3 font-medium">Target</th>
                <th scope="col" className="pr-3 font-medium">Status</th>
                <th scope="col" className="num font-medium">Raw payload</th>
              </tr>
            </thead>
            <tbody>
              {targets.map((t) => (
                <tr key={`${t.scope} ${t.target_id}`} className="row-h-compact border-t border-border-subtle">
                  <td className="max-w-56 truncate pr-3" title={`${t.scope} · ${t.target_id} · captured ${formatUtc(t.captured_at)}`}>
                    <span className="text-subtle-foreground">{t.scope} · </span>
                    {t.target_id}
                  </td>
                  <td className={cn("pr-3", runTone(t.status))}>{runStatus(t.status)}</td>
                  <td className="num font-mono">
                    {t.raw_payload_id != null ? (
                      <span title="Raw payload id. Signed download links aren't served by the API yet.">#{t.raw_payload_id}</span>
                    ) : (
                      <Missing reason="No payload stored" />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {detail.isSuccess && detail.data.next_cursor && targets.length > 0 && (
        <LoadMore
          note={targetsNote(targets.length, (more.pages.at(-1) ?? detail.data).target_count, more.hasMore)}
          label="Load more targets"
          more={more.hasMore}
          pending={more.pending}
          error={more.error}
          errorTitle="Couldn't load more targets"
          onLoad={more.load}
        />
      )}
    </div>
  );
}
