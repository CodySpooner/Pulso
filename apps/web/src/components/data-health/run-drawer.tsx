"use client";

import { useRef, useState } from "react";
import { ArrowDown, ChevronRight, History } from "lucide-react";

import { EmptyState } from "@/components/pulso/empty-state";
import { useOnline } from "@/components/shell/offline-banner";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useHost, useMoreTargets, useRunDetail, useSourceRuns } from "./api";
import { Ago, Missing, PanelError, runStatus, sourceStates, StaleLine, StatePill } from "./atoms";
import { GapsLink, OPEN_GAPS_ID } from "./coverage";
import { LoadMore } from "./load-more";
import { RetryScope, useRetryScope } from "./retry";
import { missedNote, plural, runBlocker, skipNote, sourceState, targetsNote, typeLabel, type Run, type SourceHealth } from "./model";

const RUNS_API = "GET /v1/admin/runs";

const runTone = (status: string) =>
  status === "failed" || status === "blocked" ? "text-negative" : status === "partial" ? "text-warning" : "text-muted-foreground";

// Source drawer (vault Features/Data Health): the source's every DH-1 field, then its runs newest first.
// The newest run opens expanded, so a failing source's error is one click from the table.
export function RunDrawer({
  source,
  now,
  onClose,
  onImport,
  returnFocusRef,
}: {
  source: SourceHealth | null;
  now: number;
  onClose: () => void;
  /** Opens the CSV import panel on `key`, as the Sources row's Import does. */
  onImport: (key: string) => void;
  returnFocusRef: React.RefObject<HTMLElement | null>;
}) {
  const toGaps = useRef(false); // closed by the missed-slot link: focus goes to Open gaps, not back to the opener
  const toImport = useRef<string | null>(null); // closed by the CSV import link: the panel opens on this key (imp-172)
  // The last source shown, so a closing drawer keeps its body through the exit, never an empty sheet (imp-165's rule).
  const [last, setLast] = useState(source);
  if (source && source !== last) setLast(source);
  const shown = source ?? last;
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
          // Once the drawer is gone (its focus trap and scroll lock too), the panel takes the focus and scrolls in.
          const key = toImport.current;
          toImport.current = null;
          if (key) return onImport(key);
          const gaps = toGaps.current && document.getElementById(OPEN_GAPS_ID);
          toGaps.current = false;
          (gaps || returnFocusRef.current)?.focus();
        }}
      >
        {shown && (
          <DrawerBody
            source={shown}
            now={now}
            onGaps={() => {
              toGaps.current = true;
              onClose();
            }}
            onImport={() => {
              toImport.current = shown.key;
              onClose();
            }}
          />
        )}
      </SheetContent>
    </Sheet>
  );
}

function DrawerBody({ source, now, onGaps, onImport }: { source: SourceHealth; now: number; onGaps: () => void; onImport: () => void }) {
  const host = useHost();
  const runs = useSourceRuns(source.key);
  const items = runs.data?.pages.flatMap((p) => p.items) ?? [];
  const state = sourceState(source, host.data?.latest_gap_ends, now);
  const missed = state === "overdue" && host.data ? missedNote(source.key, host.data.latest_gap_ends, host.data.open_gaps) : null;
  const online = useOnline();
  // Run now's rule, and the copy names it only once the host call says live runs are allowed (the table doesn't
  // wait for it). A preview-only CSV template checks files but adds no run.
  const canRun = host.data != null && runBlocker(host.data, source, online) == null;
  const csv = source.csv_import === "ready";
  const quota = source.quota_limit != null ? `${source.quota_used?.toLocaleString("en-US") ?? "—"} / ${source.quota_limit.toLocaleString("en-US")}` : null;
  // The drawer is a retry scope (imp-168): a pressed Retry that fails is announced once, one that restores focuses the title.
  const title = useRef<HTMLHeadingElement>(null);
  const retry = useRetryScope(title);
  // One press closes the drawer and opens the panel on this source, as the Sources row's Import does (imp-172).
  const importLink = (end?: string) => (
    <button
      type="button"
      onClick={onImport}
      className={cn("link-inline relative hit-area rounded-sm whitespace-nowrap text-foreground underline decoration-border-strong underline-offset-2 hover:decoration-current", end)}
    >
      CSV import panel
      {/* Trimmed like HostRetryLink's arrow, so the focus ring sits on the glyph (DEC-222 c). */}
      <ArrowDown aria-hidden viewBox="4 0 16 24" className="ml-1 inline h-3 w-2 align-[-2px]" />
    </button>
  );

  return (
    <RetryScope value={retry}>
      <div className="flex flex-col gap-2 border-b border-border-subtle px-5 pt-4 pb-4">
        <div className="flex items-center gap-2 pr-10">
          <SheetTitle ref={title} tabIndex={-1} className="truncate rounded-sm text-title-2 font-semibold text-foreground">
            {source.name}
          </SheetTitle>
          <StatePill state={state} />
        </div>
        {/* Why it is Overdue while its newest run may read Succeeded (imp-124). The link closes the drawer first.
            Under a coarse pointer 6 px more keeps the pill's and the link's 44 px hit squares apart (A11Y-02). */}
        {missed && (
          <p className="text-data text-foreground pointer-coarse:mt-1.5">
            <GapsLink missed={missed} onFollow={onGaps} />
          </p>
        )}
        <SheetDescription className="text-data text-muted-foreground">Source settings and runs, newest first. All times UTC.</SheetDescription>
        <dl className="zone-data mt-1 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <Fact label="Key">
            <span className="font-mono">{source.key}</span>
          </Fact>
          <Fact label="Type · phase">
            {typeLabel[source.type] ?? source.type} · Phase {source.phase}
          </Fact>
          {/* The pill's words, then the switch once; a Disabled pill already says the first (imp-127). */}
          <Fact label="Status">
            {state !== "disabled" && `${sourceStates[state].label} · `}
            {source.enabled ? "Enabled" : "Disabled"}
            {!source.enabled && source.disabled_at && (
              <span className="text-muted-foreground">
                {" "}
                since <span className="whitespace-nowrap">{formatUtc(source.disabled_at)}</span>
              </span>
            )}
          </Fact>
          {source.disabled_reason && <Fact label="Reason">{source.disabled_reason}</Fact>}
          <Fact label="Retry after">{source.retry_not_before ? formatUtc(source.retry_not_before) : <Missing reason="No retry deadline" />}</Fact>
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

      {/* pb-12: the runs footer ends the box, and its Retry's offline reason needs the room below (DEC-236 d). */}
      <div className="min-h-0 flex-1 overflow-y-auto px-5 pt-4 pb-12">
        {/* The drawer covers the page's line, so it says its own (imp-132). Only a failed refresh: an older page's
            failure is the footer's, under the runs it keeps (imp-136). */}
        {runs.isRefetchError && (
          <StaleLine boxed className="mb-3" what="Couldn't refresh runs" error={runs.error} asOf={runs.dataUpdatedAt} retry={() => void runs.refetch()} />
        )}
        {runs.isPending ? (
          <div className="flex flex-col gap-2">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : runs.isLoadingError ? (
          <PanelError title="Couldn't load runs" error={runs.error} retry={() => runs.refetch()} />
        ) : items.length === 0 ? (
          // Names only the ways to a first run this source has now (imp-128).
          <EmptyState icon={History} size="sm" title="No runs yet">
            {source.enabled ? "Runs appear here once the collector host runs this source." : "This source is disabled, so the collector host won't run it until it's enabled."}
            {canRun && csv ? (
              // A comma straight after the link needs `me-1` (DEC-222 b).
              <> Press Run now in the Sources panel, or import a CSV from the {importLink("me-1")}, to add its first&nbsp;run.</>
            ) : canRun ? (
              " Press Run now in the Sources panel to start its first run."
            ) : csv ? (
              <> Import a CSV from the {importLink()} to add its first&nbsp;run.</>
            ) : null}
          </EmptyState>
        ) : (
          <div className="flex flex-col gap-3">
            <ol aria-label={`${source.name} runs`} className="flex flex-col gap-2">
              {items.map((run, i) => (
                <RunItem key={run.id} run={run} now={now} title={title} defaultOpen={i === 0} />
              ))}
            </ol>
            {/* The targets' footer (DEC-166): a failed older page keeps every run, and Retry asks for that page only. */}
            {runs.data?.pages[0].next_cursor != null && (
              <LoadMore
                note={runs.hasNextPage ? `Showing ${plural(items.length, "run")} · older runs not loaded yet` : `Showing all ${plural(items.length, "run")}`}
                label="Load older runs"
                more={runs.hasNextPage}
                pending={runs.isFetchingNextPage}
                error={runs.isFetchNextPageError ? runs.error : null}
                errorTitle="Couldn't load older runs"
                onLoad={() => void runs.fetchNextPage()}
              />
            )}
          </div>
        )}
      </div>
    </RetryScope>
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

function RunItem({ run, now, title, defaultOpen }: { run: Run; now: number; title: React.RefObject<HTMLElement | null>; defaultOpen: boolean }) {
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
      {open && <RunDetailView run={run} title={title} />}
    </li>
  );
}

function RunDetailView({ run, title }: { run: Run; title: React.RefObject<HTMLElement | null> }) {
  const detail = useRunDetail(run.id);
  const more = useMoreTargets(run.id, detail.data?.next_cursor ?? null);
  const targets = detail.data ? [detail.data.targets, ...more.pages.map((p) => p.targets)].flat() : [];
  const skipped = run.error_code === "slot_suppressed"; // a skip, not a failure (imp-042)
  // Each run is its own retry scope (imp-179): a targets Retry that restores focuses the targets it brought back,
  // or the drawer title when the run has none.
  const region = useRef<HTMLDivElement>(null);
  const retry = useRetryScope(region, title);
  return (
    <RetryScope value={retry}>
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

        {detail.isRefetchError && (
          <StaleLine boxed what="Couldn't refresh targets" error={detail.error} asOf={detail.dataUpdatedAt} retry={() => detail.refetch()} />
        )}
        {detail.isPending ? (
          <Skeleton className="h-16 w-full" />
        ) : detail.isLoadingError ? (
          <PanelError title="Couldn't load targets" error={detail.error} retry={() => detail.refetch()} />
        ) : targets.length === 0 ? (
          <p className="text-label text-muted-foreground">No targets recorded for this run.</p>
        ) : (
          <div ref={region} role="region" aria-label={`Run ${run.id} targets`} tabIndex={0} className="relative overflow-x-auto rounded-sm">
            <table className="zone-data w-full">
              <thead>
                <tr className="text-left text-label whitespace-nowrap text-muted-foreground">
                  <th scope="col" className="h-7 pr-3 font-medium">Target</th>
                  <th scope="col" className="pr-3 font-medium">Status</th>
                  <th scope="col" className="num font-medium">Payload</th>
                </tr>
              </thead>
              <tbody>
                {targets.map((t) => (
                  <tr key={`${t.scope} ${t.target_id}`} className="row-h-compact border-t border-border-subtle">
                    {/* The target takes the width left and truncates, so Status and Payload always show (imp-131). */}
                    <td className="w-full max-w-0 truncate pr-3" title={`${t.scope} · ${t.target_id} · captured ${formatUtc(t.captured_at)}`}>
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
          // Room for an offline Retry reason below the footer, clear of the next run's row (imp-136).
          <div className="pb-2">
            <LoadMore
              note={targetsNote(targets.length, (more.pages.at(-1) ?? detail.data).target_count, more.hasMore)}
              label="Load more targets"
              more={more.hasMore}
              pending={more.pending}
              error={more.error}
              errorTitle="Couldn't load more targets"
              onLoad={more.load}
            />
          </div>
        )}
      </div>
    </RetryScope>
  );
}
