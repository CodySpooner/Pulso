"use client";

import { useEffect, useRef, useState } from "react";
import { Clock, Database, Play, TriangleAlert, Upload } from "lucide-react";

import { CopyButton, SelectableId } from "@/components/pulso/copy-button";
import { EmptyState } from "@/components/pulso/empty-state";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { $api, isProblem } from "@/lib/api/client";
import { formatAgo, formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useHost, useRefreshAdmin, useSources } from "./api";
import { Ago, Missing, Panel, PanelError, StatePill, TapTooltip } from "./atoms";
import { attentionCount, importEntry, skipNote, sourceState, type SourceHealth, type SourceState } from "./model";

const SOURCES_API = "GET /v1/admin/sources";

const typeLabel: Record<string, string> = {
  official_api: "Official API",
  public_endpoint: "Public endpoint",
  vendor: "Vendor API",
  internal: "Internal",
};

// "No source yet" rows (vault Features/Data Health, States): later-phase sources, greyed out with their phase.
const planned = [
  { name: "AliExpress", phase: 3, why: "Live lookup only, cached 24 h and never stored (DEC-037)" },
  { name: "Amazon", phase: 3, why: "Marketplace prices and seller counts" },
  { name: "Meta Ad Library", phase: 8, why: "Ads linked to the products they promote" },
  { name: "TikTok ads", phase: 8, why: "Ads linked to the products they promote" },
];

// First load: the loaded table and cards with one skeleton row per Phase 1 source, each as tall as a loaded
// row (the name and type lines set it), so nothing below moves when the data lands (CLS < 0.1, imp-082).
// ponytail: four rows fits Phase 1's seeded sources; derive the count if later phases make it vary.
const loadingRows = [0, 1, 2, 3];
// One bar per column, about as wide as its loaded content, so the header stays put too.
const loadingCells = ["h-8 w-24", "h-4 w-48","h-4 w-28", "ml-auto h-4 w-24", "h-4 w-20", "h-4 w-4", "ml-auto h-4 w-8", "h-5 w-8", "ml-auto h-7 w-52"];

const skeletonRows = loadingRows.map((i) => (
  <tr key={i} aria-hidden className="row-h-comfortable border-b border-border-subtle">
    {loadingCells.map((bar, j) => (
      <td key={j} className="px-3 py-1.5">
        <Skeleton className={bar} />
      </td>
    ))}
  </tr>
));

const pillSkeleton = <Skeleton className="h-5.5 w-18" />;

const skeletonCards = loadingRows.map((i) => (
  <li key={i} aria-hidden className="flex flex-col gap-2 px-4 py-3">
    <div className="flex items-center justify-between gap-2">
      <Skeleton className="h-8 w-32" />
      <Skeleton className="h-5.5 w-18" />
    </div>
    <Skeleton className="h-10 w-48" />
    <div className="flex items-center justify-between gap-2">
      <Skeleton className="h-5 w-24" />
      <Skeleton className="h-7 w-52" />
    </div>
  </li>
));

type Failure = { tone: "error"; text: string; key: string; error: unknown };
type Notice = { tone: "ok"; text: string } | Failure;
type Confirm = { source: SourceHealth; mode: "disable" | "reenable" };

const th = "h-8 border-b border-border px-3 text-label font-medium whitespace-nowrap text-muted-foreground";

/** A failed action on `source`: what failed, then why and what next. The transport copy is imp-078's next step. */
function actionFailure(source: SourceHealth, action: string, error: unknown): Failure {
  const cause = isProblem(error) ? error.detail : "the API didn't answer. When it runs on your PC, check that the PC is on.";
  return { tone: "error", text: `Couldn't ${action} ${source.name}: ${cause}`, key: source.key, error };
}

export function SourcesPanel({ now, onOpen, onImport }: { now: number; onOpen: (key: string) => void; onImport: (key: string) => void }) {
  const sources = useSources();
  const host = useHost();
  const refresh = useRefreshAdmin();
  const patch = $api.useMutation("patch", "/v1/admin/sources/{key}");
  const run = $api.useMutation("post", "/v1/admin/sources/{key}/run");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const toggled = useRef<HTMLElement | null>(null); // the dialog has no Radix trigger, so focus returns here

  const latestGapEnds = host.data?.latest_gap_ends; // undefined while the host call loads or failed (imp-133)
  const rows = sources.data?.filter((s) => s.type !== "internal") ?? [];
  const attention = attentionCount(rows, latestGapEnds, now);
  // A state that waits on the host's gap summary keeps the loading treatment until the host call settles.
  const waiting = (state: SourceState) => state === "unknown" && host.isPending;
  // A failure shows next to what started it (imp-123): inside its dialog while that is open; otherwise in the
  // source's phone card, and from md up in the status line as before. Each place is the only one showing it.
  const failed = notice?.tone === "error" ? notice : null;
  const inDialog = failed != null && failed.key === confirm?.source.key;
  const status = inDialog ? null : notice;

  /** A new attempt drops the last failure, so a repeat is announced again; a success notice stays until replaced. */
  const clearFailure = () => setNotice((n) => (n?.tone === "error" ? null : n));

  function setEnabled(source: SourceHealth, enabled: boolean, reason?: string) {
    clearFailure();
    patch.mutate(
      { params: { path: { key: source.key } }, body: { enabled, reason: reason || null } },
      {
        onSuccess: () => {
          setConfirm(null);
          setNotice({ tone: "ok", text: `${source.name} ${enabled ? "enabled" : "disabled"}.` });
          void refresh();
        },
        onError: (error) => setNotice(actionFailure(source, enabled ? "enable" : "disable", error)),
      },
    );
  }

  function toggle(source: SourceHealth, enabled: boolean) {
    toggled.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    clearFailure();
    if (!enabled) setConfirm({ source, mode: "disable" });
    else if (source.status === "blocked") setConfirm({ source, mode: "reenable" });
    else setEnabled(source, true);
  }

  function runNow(source: SourceHealth) {
    clearFailure();
    run.mutate(
      { params: { path: { key: source.key } } },
      {
        onSuccess: (r) => {
          setNotice({ tone: "ok", text: `Run #${r.id} queued for ${source.name}.` });
          void refresh();
        },
        onError: (error) => setNotice(actionFailure(source, "start", error)),
      },
    );
  }

  /** Why Run now is unavailable, or null when it can run. */
  function runBlocker(source: SourceHealth): string | null {
    if (host.data && !host.data.live_runs_allowed) return "Live collectors run only on the collector host.";
    if (!source.enabled) return "Enable the source before running it.";
    return null;
  }

  const saving = (s: SourceHealth) => patch.isPending && patch.variables?.params.path.key === s.key;
  const controls = (s: SourceHealth) => ({
    toggle: (
      <Switch
        checked={s.enabled}
        onCheckedChange={(on) => !saving(s) && toggle(s, on)}
        // aria-disabled (not disabled) while saving keeps keyboard focus on the switch when its change fails.
        aria-disabled={saving(s)}
        aria-label={`${s.name} enabled`}
      />
    ),
    run: <RunButton name={s.name} blocker={runBlocker(s)} pending={run.isPending && run.variables?.params.path.key === s.key} onRun={() => runNow(s)} />,
    import: <ImportButton source={s} onImport={onImport} />,
  });

  return (
    <Panel
      id="sources"
      title="Sources"
      note={
        sources.data && (
          <>
            {rows.length} {rows.length === 1 ? "source" : "sources"}
            {attention.count > 0 && !host.isPending && (
              <span className="text-negative">
                {" "}
                · {attention.atLeast && "at least "}
                {attention.count} {attention.count === 1 ? "needs" : "need"} attention
              </span>
            )}
          </>
        )
      }
    >
      <p
        role="status"
        className={cn("px-4 text-data empty:hidden", status && "border-b border-border-subtle py-2", status?.tone === "error" ? "text-negative max-md:hidden" : "text-muted-foreground")}
      >
        {status?.text}
        {status?.tone === "error" && isProblem(status.error) && ` (error ID ${status.error.request_id})`}
      </p>

      {sources.isError ? (
        <PanelError title="Couldn't load sources" error={sources.error} retry={() => sources.refetch()} />
      ) : sources.data && rows.length === 0 ? (
        <EmptyState icon={Database} size="sm" title="No sources configured">
          Apply the database migrations to seed the Phase 1 sources (Shopify stores, CJ, Google Trends, Frankfurter FX).
        </EmptyState>
      ) : (
        <>
          {/* Phone and small tablet: one card per source (vault Features/Data Health, Mobile). */}
          <ul className="flex flex-col divide-y divide-border-subtle md:hidden">
            {sources.isPending && skeletonCards}
            {rows.map((s) => {
              const c = controls(s);
              const state = sourceState(s, latestGapEnds, now);
              return (
                <li key={s.key} className="flex flex-col gap-2 px-4 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <SourceName source={s} onOpen={onOpen} />
                    {waiting(state) ? pillSkeleton : <StatePill state={state} />}
                  </div>
                  {!waiting(state) && <StatusNote source={s} state={state} className="-mt-1" />}
                  <dl className="zone-data grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-muted-foreground">
                    <dt>Last run</dt>
                    <dd className="text-foreground">
                      <LastRun source={s} now={now} />
                    </dd>
                    <dt>Freshness</dt>
                    <dd className="text-foreground">
                      <Freshness source={s} now={now} />
                    </dd>
                  </dl>
                  <div className="flex items-center justify-between gap-2">
                    <label className="flex items-center gap-2 text-data text-muted-foreground">
                      {c.toggle}
                      {s.enabled ? "Enabled" : "Disabled"}
                    </label>
                    <div className="flex gap-2">
                      {c.import}
                      {c.run}
                    </div>
                  </div>
                  {failed?.key === s.key && !inDialog && <ActionError failure={failed} />}
                </li>
              );
            })}
            {planned.map((p) => (
              <li key={p.name} className="flex flex-col gap-0.5 px-4 py-3 text-subtle-foreground">
                <span className="text-data font-medium">{p.name}</span>
                <span className="text-label">
                  No source yet · arrives in Phase {p.phase}. {p.why}.
                </span>
              </li>
            ))}
          </ul>

          <div role="region" aria-label="Sources table" tabIndex={0} className="relative overflow-x-auto max-md:hidden">
            <table className="zone-data w-full min-w-240">
              <thead>
                <tr>
                  <th scope="col" className={cn(th, "text-left")}>Source</th>
                  <th scope="col" className={cn(th, "text-left")}>Status</th>
                  <th scope="col" className={cn(th, "text-left")}>Last run</th>
                  <th scope="col" className={cn(th, "text-right")} title="Rows fetched / inserted / updated by the last run">
                    Rows F / I / U
                  </th>
                  <th scope="col" className={cn(th, "text-left")}>Freshness</th>
                  <th scope="col" className={cn(th, "text-left")}>Next due</th>
                  <th scope="col" className={cn(th, "text-right")}>Last code</th>
                  <th scope="col" className={cn(th, "text-left")}>Enabled</th>
                  <th scope="col" className={cn(th, "text-right")}>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {sources.isPending && skeletonRows}
                {rows.map((s) => {
                  const c = controls(s);
                  const lr = s.last_run;
                  const state = sourceState(s, latestGapEnds, now);
                  return (
                    <tr key={s.key} className="row-h-comfortable border-b border-border-subtle hover:bg-(--table-row-hover)">
                      <td className="px-3 py-1.5">
                        <SourceName source={s} onOpen={onOpen} />
                      </td>
                      <td className="px-3">
                        <div className="flex flex-col items-start gap-0.5">
                          {waiting(state) ? pillSkeleton : <StatePill state={state} />}
                          {!waiting(state) && <StatusNote source={s} state={state} />}
                        </div>
                      </td>
                      <td className="px-3">
                        <LastRun source={s} now={now} />
                      </td>
                      <td className="num px-3 whitespace-nowrap">
                        {lr ? (
                          <span title={`Fetched / inserted / updated · run #${lr.id} · ${SOURCES_API}`}>
                            {lr.rows_fetched.toLocaleString("en-US")} <span className="text-subtle-foreground">/</span> {lr.rows_inserted.toLocaleString("en-US")}{" "}
                            <span className="text-subtle-foreground">/</span> {lr.rows_updated.toLocaleString("en-US")}
                          </span>
                        ) : (
                          <Missing reason="No run recorded yet" />
                        )}
                      </td>
                      <td className="px-3">
                        <Freshness source={s} now={now} />
                      </td>
                      <td className="px-3">
                        <Missing reason="No source yet: the API doesn't serve the Beat schedule" />
                      </td>
                      <td className="num px-3 font-mono">
                        {s.last_status_code != null ? (
                          <span title={`Last HTTP or source code · ${SOURCES_API}`} className={cn(s.last_status_code >= 400 && "text-negative")}>
                            {s.last_status_code}
                          </span>
                        ) : (
                          <Missing reason="No response recorded yet" />
                        )}
                      </td>
                      <td className="px-3">{c.toggle}</td>
                      <td className="px-3">
                        <div className="flex justify-end gap-2">
                          {c.import}
                          {c.run}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tbody className="text-subtle-foreground">
                <tr>
                  <th scope="rowgroup" colSpan={9} className="h-8 px-3 text-left text-label font-medium">
                    Planned
                  </th>
                </tr>
                {planned.map((p) => (
                  <tr key={p.name} className="row-h border-t border-border-subtle">
                    <td className="px-3 font-medium">{p.name}</td>
                    <td colSpan={8} className="px-3">
                      No source yet · arrives in Phase {p.phase}. {p.why}.
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <ReasonDialog
        now={now}
        returnFocusRef={toggled}
        confirm={confirm}
        pending={patch.isPending}
        failure={inDialog ? failed : null}
        onCancel={() => {
          setConfirm(null);
          clearFailure();
        }}
        onSubmit={(reason) => confirm && setEnabled(confirm.source, confirm.mode === "reenable", reason)}
      />
    </Panel>
  );
}

function SourceName({ source, onOpen }: { source: SourceHealth; onOpen: (key: string) => void }) {
  return (
    <div className="flex min-w-0 flex-col">
      <button
        type="button"
        onClick={() => onOpen(source.key)}
        aria-label={`${source.name}: open runs`}
        className="relative hit-area max-w-full self-start rounded-sm text-left font-medium text-foreground underline-offset-4 hover:underline"
      >
        <span className="block truncate">{source.name}</span>
      </button>
      <span className="text-label text-subtle-foreground">{typeLabel[source.type] ?? source.type}</span>
    </div>
  );
}

function StatusNote({ source, state, className }: { source: SourceHealth; state: SourceState; className?: string }) {
  const reason = [
    source.disabled_reason,
    state === "skipped" && source.last_run && skipNote(source.last_run),
    state === "unknown" && "Gap check didn't load", // short enough for the table's truncated note; the hint says the rest
  ]
    .filter(Boolean)
    .join(" · ");
  if (!reason && !source.retry_not_before) return null;
  // The table (md and up) truncates the reason; the phone card wraps it. The deadline line is never cut (imp-094).
  return (
    <span className={cn("flex flex-col text-label text-muted-foreground", className)}>
      {reason && (
        <span title={reason} className="md:max-w-48 md:truncate">
          {reason}
        </span>
      )}
      {source.retry_not_before && <span className="whitespace-nowrap">Retry after {formatUtc(source.retry_not_before)}</span>}
    </span>
  );
}

function LastRun({ source, now }: { source: SourceHealth; now: number }) {
  const r = source.last_run;
  if (!r) return <Missing reason="No run recorded yet" />;
  return (
    <span className="whitespace-nowrap">
      <Ago iso={r.finished_at ?? r.started_at ?? r.queued_at} now={now} source={`run #${r.id} · ${SOURCES_API}`} />
      <span className="text-subtle-foreground"> · {r.trigger}</span>
    </span>
  );
}

function Freshness({ source, now }: { source: SourceHealth; now: number }) {
  if (!source.freshness) return <Missing reason="Not collected yet" />;
  return (
    <span>
      <span className="text-subtle-foreground">as of </span>
      <Ago iso={source.freshness} now={now} source={`Last successful target, including 304 · ${SOURCES_API}`} />
    </span>
  );
}

function RunButton({ name, blocker, pending, onRun }: { name: string; blocker: string | null; pending: boolean; onRun: () => void }) {
  const button = (
    <Button
      size="sm"
      variant="secondary"
      aria-disabled={blocker != null || pending}
      // aria-disabled (not disabled) keeps the button focusable and hoverable so its reason shows.
      className="aria-disabled:pointer-events-auto aria-disabled:cursor-not-allowed"
      onClick={() => blocker == null && !pending && onRun()}
      aria-label={`Run ${name} now`}
    >
      <Play aria-hidden />
      {pending ? "Queuing…" : "Run now"}
    </Button>
  );
  if (!blocker) return button;
  // A tap shows the reason too (imp-126): a phone has no hover, and a tap's focus isn't focus-visible.
  return (
    <TapTooltip hint={blocker} asChild>
      {button}
    </TapTooltip>
  );
}

/** A failed action beside the control that started it (imp-123): what and why, announced once, then the error
 *  ID to copy (PanelError's parts), which the announcement leaves out. It scrolls into view if it lands below. */
function ActionError({ failure }: { failure: Failure }) {
  const problem = isProblem(failure.error) ? failure.error : null;
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    box.current?.scrollIntoView({ block: "nearest" }); // a block: scrollIntoView may return a Promise, never a cleanup
  }, []);
  return (
    // The scroll margin clears the phone's bottom bar (h-14).
    <div ref={box} className="flex scroll-mb-[calc(4.5rem+env(safe-area-inset-bottom))] flex-col gap-1 rounded-lg border border-negative/40 bg-negative-muted px-3 py-2 text-data">
      <p role="alert" className="text-foreground">
        <TriangleAlert aria-hidden className="mr-1.5 inline size-3.5 align-[-2px] text-negative" />
        {failure.text}
      </p>
      {problem && (
        <div className="flex flex-wrap items-center justify-between gap-x-3">
          {/* muted, not subtle: subtle falls below 4.5:1 on this tint over the dialog's popover in dark. */}
          <span className="font-mono text-label text-muted-foreground">
            {/* inline-block: on a phone the ID moves to its own line whole instead of breaking at a hyphen. */}
            Error ID <SelectableId value={problem.request_id} label="Error ID" className="inline-block max-w-full break-all" />
          </span>
          <CopyButton value={problem.request_id} label="Copy error ID" />
        </div>
      )}
    </div>
  );
}

/** Opens the CSV import panel on this source's template (imp-081); without one it says why instead. */
function ImportButton({ source, onImport }: { source: SourceHealth; onImport: (key: string) => void }) {
  const { label, hint, available } = importEntry(source);
  const button = (
    <Button
      size="sm"
      variant="ghost"
      aria-disabled={!available}
      // Only the icon and label fade, not the button, so its focus ring keeps 3:1 (like the import panel's locks, DEC-185).
      className="aria-disabled:pointer-events-auto aria-disabled:cursor-not-allowed aria-disabled:opacity-100 aria-disabled:*:opacity-50"
      onClick={() => available && onImport(source.key)}
      aria-label={`${label} for ${source.name}`}
    >
      <Upload aria-hidden />
      <span>{label}</span>
    </Button>
  );
  if (!hint) return button;
  // A tap on a locked entry says why too (imp-126). "Check CSV" acts on a tap, and the panel then says why.
  if (!available) {
    return (
      <TapTooltip hint={hint} asChild>
        {button}
      </TapTooltip>
    );
  }
  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent>{hint}</TooltipContent>
    </Tooltip>
  );
}

function ReasonDialog({
  now,
  returnFocusRef,
  confirm,
  pending,
  failure,
  onCancel,
  onSubmit,
}: {
  now: number;
  returnFocusRef: React.RefObject<HTMLElement | null>;
  confirm: Confirm | null;
  pending: boolean;
  /** The last Submit failed: the dialog stays open and says why, and Submit tries again. */
  failure: Failure | null;
  onCancel: () => void;
  onSubmit: (reason: string) => void;
}) {
  const reenable = confirm?.mode === "reenable";
  // Re-enabling stays allowed before retry_not_before, and it leaves the deadline as stored: live runs before
  // it are deferred (RunDeferred), so the dialog says so instead of implying the wait is over (imp-094).
  const retryAfter = reenable && confirm.source.retry_not_before && Date.parse(confirm.source.retry_not_before) > now ? confirm.source.retry_not_before : null;
  return (
    <Dialog open={confirm != null} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent
        onCloseAutoFocus={(e) => {
          e.preventDefault();
          returnFocusRef.current?.focus();
        }}
      >
        {confirm && (
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (!pending) onSubmit(String(new FormData(e.currentTarget).get("reason") ?? "").trim());
            }}
          >
            <div className="flex flex-col gap-1.5">
              <DialogTitle>{reenable ? `Re-enable ${confirm.source.name}?` : `Disable ${confirm.source.name}?`}</DialogTitle>
              <DialogDescription asChild>
                <div className="flex flex-col gap-3">
                  <p>
                    {reenable
                      ? "The block rule turned this source off. Say why it is safe to try again; the reason goes to the source's audit log (§4.2)."
                      : "Scheduled runs stop until you enable it again, and the days it is disabled show as gaps."}
                  </p>
                  {retryAfter && (
                    <p className="flex gap-2 rounded-md bg-warning-muted px-3 py-2 text-foreground">
                      <Clock aria-hidden className="mt-0.5 size-3.5 shrink-0 text-warning" />
                      <span>
                        Retry after <span className="font-medium whitespace-nowrap">{formatUtc(retryAfter)}</span> ({formatAgo(retryAfter, now)}). You can re-enable
                        now, but runs before then are deferred.
                      </span>
                    </p>
                  )}
                </div>
              </DialogDescription>
            </div>
            <label className="flex flex-col gap-1.5 text-label font-medium text-muted-foreground">
              {reenable ? "Reason" : "Reason (optional)"}
              <textarea
                name="reason"
                rows={3}
                required={reenable}
                className="rounded-md border border-input bg-background px-2.5 py-2 text-body text-foreground placeholder:text-subtle-foreground"
                placeholder={
                  retryAfter ? "For example: store reachable again" : reenable ? "For example: retry-after passed, store reachable again" : "For example: pausing while the seed list is reviewed"
                }
              />
            </label>
            {failure && <ActionError failure={failure} />}
            <div className="flex justify-end gap-2">
              <DialogClose asChild>
                <Button type="button" variant="ghost">
                  Cancel
                </Button>
              </DialogClose>
              <Button type="submit" variant="primary" aria-disabled={pending} className="aria-disabled:pointer-events-auto">
                {pending ? "Saving…" : reenable ? "Re-enable" : "Disable"}
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
