"use client";

import { CircleCheck, CircleDashed, CircleX, Clock, LoaderCircle, type LucideIcon } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { formatDuration, formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { BACKUP_RUNS, useBackupRuns, useCoreDown, useHost, useSources } from "./api";
import { Ago, Missing, Panel, PanelError, Pill, runStatus, StaleLine, type Tone } from "./atoms";
import { backupState, hostState, mergeGaps, type BackupState, type HostState } from "./model";

const HOST_API = "GET /v1/admin/host";
const RUNS_API = "GET /v1/admin/runs?source=backup";

const hostPill: Record<HostState, { label: string; icon: LucideIcon; tone: Tone }> = {
  online: { label: "Online", icon: CircleCheck, tone: "neutral" },
  late: { label: "Late", icon: Clock, tone: "warning" },
  offline: { label: "Offline", icon: CircleX, tone: "negative" },
  none: { label: "No heartbeat", icon: CircleDashed, tone: "muted" },
};

const backupPill: Record<BackupState, { label: string; icon: LucideIcon; tone: Tone }> = {
  ok: { label: "OK", icon: CircleCheck, tone: "neutral" },
  running: { label: "Running", icon: LoaderCircle, tone: "info" },
  overdue: { label: "Overdue", icon: Clock, tone: "warning" },
  failed: { label: "Failed", icon: CircleX, tone: "negative" },
  none: { label: "None yet", icon: CircleDashed, tone: "muted" },
};

function Facts({ children }: { children: React.ReactNode }) {
  return <dl className="zone-data grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-4 gap-y-2 px-4 py-3">{children}</dl>;
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-foreground">{children}</dd>
    </>
  );
}

function CardSkeleton() {
  return (
    // One bar per fact at the facts' row gap, so the card keeps its loaded height (imp-082).
    <div className="flex flex-col gap-2 px-4 py-3">
      {[0, 1, 2, 3, 4].map((i) => (
        <Skeleton key={i} className="h-4.5 w-full" />
      ))}
    </div>
  );
}

export function HostCard({ now }: { now: number }) {
  const host = useHost();
  const sources = useSources();
  const coreDown = useCoreDown();
  const state = host.data ? hostState(host.data, now) : null;
  const pill = state && hostPill[state];
  const gaps = host.data ? mergeGaps(host.data.open_gaps) : [];
  const nameOf = (key: string) => sources.data?.find((s) => s.key === key)?.name ?? key;

  return (
    <Panel
      id="host"
      title="Collector host"
      actions={pill && <Pill tone={pill.tone} icon={pill.icon}>{pill.label}</Pill>}
    >
      {host.isRefetchError && !coreDown && (
        <StaleLine what="Couldn't refresh the collector host" error={host.error} asOf={host.dataUpdatedAt} retry={() => host.refetch()} />
      )}
      {host.isPending ? (
        <CardSkeleton />
      ) : host.isLoadingError ? (
        <PanelError title="Couldn't load the collector host" error={host.error} retry={() => host.refetch()} />
      ) : (
        <Facts>
          <Fact label="Host">
            {host.data.latest_heartbeat ? (
              <span className="font-mono" title={`Latest heartbeat host · ${HOST_API}`}>
                {host.data.latest_heartbeat.host}
              </span>
            ) : (
              <span className="text-muted-foreground">No heartbeat yet. Beat sends one every 5 minutes once it runs.</span>
            )}
          </Fact>
          <Fact label="Last heartbeat">
            {host.data.latest_heartbeat ? (
              <span className={cn(state === "late" && "text-warning", state === "offline" && "text-negative")}>
                <Ago iso={host.data.latest_heartbeat.at} now={now} source={HOST_API} />
                {state === "late" && " · late after 15 min"}
                {state === "offline" && " · offline after 2 h"}
              </span>
            ) : (
              <Missing reason="No heartbeat recorded" />
            )}
          </Fact>
          <Fact label="Run now">
            <span title={HOST_API}>
              {host.data.live_runs_allowed ? "Allowed on this API" : "Off here: live collectors run only on the collector host"}
            </span>
          </Fact>
          <Fact label="Open gaps, 90 d">
            {gaps.length === 0 ? (
              <span title={HOST_API} className="text-muted-foreground">
                None
              </span>
            ) : (
              <span title={HOST_API}>
                <span className="tabular-nums">{host.data.next_cursor ? "At least " : ""}{host.data.open_gaps.length}</span> {host.data.open_gaps.length === 1 ? "missed slot" : "missed slots"} · latest {nameOf(gaps[0].source_key)},{" "}
                <time dateTime={gaps[0].start}>{formatUtc(gaps[0].start)}</time>
              </span>
            )}
          </Fact>
          <Fact label="Uptime, 7 d">
            <Missing reason="No source yet: the API doesn't serve uptime or offline windows" />
          </Fact>
        </Facts>
      )}
    </Panel>
  );
}

export function BackupCard({ now }: { now: number }) {
  const runs = useBackupRuns();
  const coreDown = useCoreDown();
  const backup =runs.data ? backupState(runs.data.items, now) : null;
  const pill = backup && backupPill[backup.state];
  const shown = backup?.lastSuccess ?? backup?.latest;

  return (
    <Panel id="backup" title="Backups" note={<span className="max-sm:hidden">Nightly pg_dump on the collector host</span>} actions={pill && <Pill tone={pill.tone} icon={pill.icon}>{pill.label}</Pill>}>
      {runs.isRefetchError && !coreDown && (
        <StaleLine what="Couldn't refresh backups" error={runs.error} asOf={runs.dataUpdatedAt} retry={() => runs.refetch()} />
      )}
      {runs.isPending ? (
        <CardSkeleton />
      ) : runs.isLoadingError ? (
        <PanelError title="Couldn't load backups" error={runs.error} retry={() => runs.refetch()} />
      ) : !backup?.latest ? (
        <p className="px-4 py-3 text-data text-muted-foreground">
          No backup recorded yet. Each nightly dump logs a run here once the collector host runs it (DEC-060).
        </p>
      ) : (
        <Facts>
          <Fact label="Last good backup">
            {backup.lastSuccess?.finished_at ? (
              <span className={cn(backup.state === "overdue" && "text-warning")}>
                <Ago iso={backup.lastSuccess.finished_at} now={now} source={RUNS_API} />
                {backup.state === "overdue" && " · none in the last 26 h"}
              </span>
            ) : (
              <Missing reason="No successful backup yet" />
            )}
          </Fact>
          <Fact label="Latest run">
            <span title={`${formatUtc(backup.latest.queued_at)} · ${RUNS_API}`}>
              {runStatus(backup.latest.status)}
              {backup.latest.error_message && <span className="text-negative"> · {backup.latest.error_message}</span>}
            </span>
          </Fact>
          <Fact label="Duration">
            {shown?.started_at && shown.finished_at ? (
              <span className="tabular-nums" title={RUNS_API}>
                {formatDuration(Date.parse(shown.finished_at) - Date.parse(shown.started_at))}
              </span>
            ) : (
              <Missing reason="Not finished" />
            )}
          </Fact>
          <Fact label="Size">
            <Missing reason="No source yet: the API doesn't serve backup size" />
          </Fact>
          <Fact label={`Last ${BACKUP_RUNS} runs`}>
            <RunStrip runs={runs.data.items} />
          </Fact>
        </Facts>
      )}
    </Panel>
  );
}

/** Oldest → newest run cells; each cell's status and time are on hover, and the list reads as text. */
function RunStrip({ runs }: { runs: { id: number; status: string; queued_at: string }[] }) {
  const tone = (status: string) =>
    status === "success" ? "bg-subtle-foreground" : status === "failed" || status === "blocked" ? "bg-negative" : status === "partial" ? "bg-warning" : "bg-border-strong";
  const failed = runs.filter((r) => r.status === "failed" || r.status === "blocked").length;
  return (
    <span className="flex items-center gap-2">
      <span aria-hidden className="flex h-4 items-stretch gap-0.5">
        {[...runs].reverse().map((r) => (
          <span key={r.id} title={`${formatUtc(r.queued_at)} · ${runStatus(r.status)}`} className={cn("w-1.5 rounded-xs", tone(r.status))} />
        ))}
      </span>
      <span className="text-label text-muted-foreground">
        {failed === 0 ? `${runs.length} runs, none failed` : `${failed} of ${runs.length} failed`}
      </span>
    </span>
  );
}

