"use client";

import { useRef, useState } from "react";
import { Database, Play } from "lucide-react";

import { EmptyState } from "@/components/pulso/empty-state";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { $api, isProblem } from "@/lib/api/client";
import { formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useHost, useRefreshAdmin, useSources } from "./api";
import { Ago, Missing, Panel, PanelError, StatePill } from "./atoms";
import { attentionCount, sourceState, type SourceHealth } from "./model";

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

type Notice = { tone: "ok" | "error"; text: string };
type Confirm = { source: SourceHealth; mode: "disable" | "reenable" };

const th = "h-8 border-b border-border px-3 text-label font-medium whitespace-nowrap text-muted-foreground";

function problemText(error: unknown, fallback: string): string {
  return isProblem(error) ? `${error.detail} (error ID ${error.request_id})` : fallback;
}

export function SourcesPanel({ now, onOpen }: { now: number; onOpen: (key: string) => void }) {
  const sources = useSources();
  const host = useHost();
  const refresh = useRefreshAdmin();
  const patch = $api.useMutation("patch", "/v1/admin/sources/{key}");
  const run = $api.useMutation("post", "/v1/admin/sources/{key}/run");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const toggled = useRef<HTMLElement | null>(null); // the dialog has no Radix trigger, so focus returns here

  const gaps = host.data?.open_gaps ?? [];
  const rows = sources.data?.filter((s) => s.type !== "internal") ?? [];
  const attention = sources.data ? attentionCount(rows, gaps, now) : 0;

  function setEnabled(source: SourceHealth, enabled: boolean, reason?: string) {
    patch.mutate(
      { params: { path: { key: source.key } }, body: { enabled, reason: reason || null } },
      {
        onSuccess: () => {
          setConfirm(null);
          setNotice({ tone: "ok", text: `${source.name} ${enabled ? "enabled" : "disabled"}.` });
          void refresh();
        },
        onError: (error) => setNotice({ tone: "error", text: `Couldn't change ${source.name}: ${problemText(error, "the API didn't answer.")}` }),
      },
    );
  }

  function toggle(source: SourceHealth, enabled: boolean) {
    toggled.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (!enabled) setConfirm({ source, mode: "disable" });
    else if (source.status === "blocked") setConfirm({ source, mode: "reenable" });
    else setEnabled(source, true);
  }

  function runNow(source: SourceHealth) {
    run.mutate(
      { params: { path: { key: source.key } } },
      {
        onSuccess: (r) => {
          setNotice({ tone: "ok", text: `Run #${r.id} queued for ${source.name}.` });
          void refresh();
        },
        onError: (error) => setNotice({ tone: "error", text: `Couldn't start ${source.name}: ${problemText(error, "the API didn't answer.")}` }),
      },
    );
  }

  /** Why Run now is unavailable, or null when it can run. */
  function runBlocker(source: SourceHealth): string | null {
    if (host.data && !host.data.live_runs_allowed) return "Live collectors run only on the collector host.";
    if (!source.enabled) return "Enable the source before running it.";
    return null;
  }

  const controls = (s: SourceHealth) => ({
    toggle: (
      <Switch
        checked={s.enabled}
        onCheckedChange={(on) => toggle(s, on)}
        disabled={patch.isPending && patch.variables?.params.path.key === s.key}
        aria-label={`${s.name} enabled`}
      />
    ),
    run: <RunButton name={s.name} blocker={runBlocker(s)} pending={run.isPending && run.variables?.params.path.key === s.key} onRun={() => runNow(s)} />,
  });

  return (
    <Panel
      id="sources"
      title="Sources"
      note={
        sources.data && (
          <>
            {rows.length} {rows.length === 1 ? "source" : "sources"}
            {attention > 0 && <span className="text-negative"> · {attention} need attention</span>}
          </>
        )
      }
    >
      <p role="status" className={cn("px-4 text-data empty:hidden", notice && "border-b border-border-subtle py-2", notice?.tone === "error" ? "text-negative" : "text-muted-foreground")}>
        {notice?.text}
      </p>

      {sources.isPending ? (
        <div className="flex flex-col gap-2 p-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
      ) : sources.isError ? (
        <PanelError title="Couldn't load sources" error={sources.error} retry={() => sources.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState icon={Database} size="sm" title="No sources configured">
          Apply the database migrations to seed the Phase 1 sources (Shopify stores, CJ, Google Trends, Frankfurter FX).
        </EmptyState>
      ) : (
        <>
          {/* Phone and small tablet: one card per source (vault Features/Data Health, Mobile). */}
          <ul className="flex flex-col divide-y divide-border-subtle md:hidden">
            {rows.map((s) => {
              const c = controls(s);
              return (
                <li key={s.key} className="flex flex-col gap-2 px-4 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <SourceName source={s} onOpen={onOpen} />
                    <StatePill state={sourceState(s, gaps, now)} />
                  </div>
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
                    {c.run}
                  </div>
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
                {rows.map((s) => {
                  const c = controls(s);
                  const lr = s.last_run;
                  return (
                    <tr key={s.key} className="row-h-comfortable border-b border-border-subtle hover:bg-(--table-row-hover)">
                      <td className="px-3 py-1.5">
                        <SourceName source={s} onOpen={onOpen} />
                      </td>
                      <td className="px-3">
                        <div className="flex flex-col items-start gap-0.5">
                          <StatePill state={sourceState(s, gaps, now)} />
                          <StatusNote source={s} />
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
                      <td className="px-3 text-right">{c.run}</td>
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

      <ReasonDialog returnFocusRef={toggled} confirm={confirm} pending={patch.isPending} onCancel={() => setConfirm(null)} onSubmit={(reason) => confirm && setEnabled(confirm.source, confirm.mode === "reenable", reason)} />
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
        className="self-start truncate rounded-sm text-left font-medium text-foreground underline-offset-4 hover:underline"
      >
        {source.name}
      </button>
      <span className="text-micro text-subtle-foreground">{typeLabel[source.type] ?? source.type}</span>
    </div>
  );
}

function StatusNote({ source }: { source: SourceHealth }) {
  const note = [source.disabled_reason, source.retry_not_before && `retry after ${formatUtc(source.retry_not_before)}`].filter(Boolean).join(" · ");
  if (!note) return null;
  return (
    <span title={note} className="max-w-48 truncate text-micro text-muted-foreground">
      {note}
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
  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent>{blocker}</TooltipContent>
    </Tooltip>
  );
}

function ReasonDialog({
  returnFocusRef,
  confirm,
  pending,
  onCancel,
  onSubmit,
}: {
  returnFocusRef: React.RefObject<HTMLElement | null>;
  confirm: Confirm | null;
  pending: boolean;
  onCancel: () => void;
  onSubmit: (reason: string) => void;
}) {
  const reenable = confirm?.mode === "reenable";
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
              <DialogDescription>
                {reenable
                  ? "The block rule turned this source off. Say why it is safe to try again; the reason goes to the source's audit log (§4.2)."
                  : "Scheduled runs stop until you enable it again, and the days it is disabled show as gaps."}
              </DialogDescription>
            </div>
            <label className="flex flex-col gap-1.5 text-label font-medium text-muted-foreground">
              {reenable ? "Reason" : "Reason (optional)"}
              <textarea
                name="reason"
                rows={3}
                required={reenable}
                className="rounded-md border border-input bg-background px-2.5 py-2 text-body text-foreground placeholder:text-subtle-foreground"
                placeholder={reenable ? "For example: retry-after passed, store reachable again" : "For example: pausing while the seed list is reviewed"}
              />
            </label>
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
