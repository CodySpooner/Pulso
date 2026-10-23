"use client";

import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { EmptyState } from "@/components/pulso/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useCoverage, useHost, useSources } from "./api";
import { Panel, PanelError } from "./atoms";
import { coverageRows, mergeGaps, utcDays, type CoverageDay } from "./model";

export const COVERAGE_DAYS = 90;
/** Phones show the most recent month; the cells before it are hidden below md. */
const PHONE_DAYS = 30;
const COVERAGE_API = "GET /v1/admin/coverage?days=90";

type CellStatus = CoverageDay["status"] | "none";

// Status colours only on this view (vault Design/Charts & Data Viz, Status), and only for the days that need
// attention: a collected day is neutral. Missed days are hatched, so a gap never reads as a colour alone;
// each cell names its status on hover and each row reads as text.
const cellStyle: Record<CellStatus, { label: string; className: string }> = {
  success: { label: "Collected", className: "bg-subtle-foreground" },
  partial: { label: "Partial", className: "bg-warning/70" },
  failed: { label: "Failed", className: "bg-negative" },
  gap: { label: "Missed (gap)", className: "bg-[repeating-linear-gradient(135deg,var(--negative)_0_2px,transparent_2px_4px)] ring-1 ring-negative/60 ring-inset" },
  filled: { label: "Gap filled later", className: "bg-[repeating-linear-gradient(135deg,var(--subtle-foreground)_0_2px,transparent_2px_4px)]" },
  running: { label: "Running", className: "bg-info/60" },
  queued: { label: "Queued", className: "bg-info/30" },
  unknown: { label: "Unknown", className: "ring-1 ring-border-strong ring-inset" },
  none: { label: "No data", className: "bg-accent" },
};

const reasonLabel: Record<string, string> = {
  host_offline: "Host offline",
  run_failed: "Run failed",
  source_disabled: "Source disabled",
  blocked: "Blocked",
};

const day = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
const dayLabel = (iso: string) => day.format(new Date(`${iso}T00:00:00Z`));

function summary(cells: (CoverageDay | null)[]): string {
  const counts = new Map<string, number>();
  for (const c of cells) {
    const label = cellStyle[c?.status ?? "none"].label.toLowerCase();
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  return [...counts].map(([label, n]) => `${n} ${label}`).join(", ");
}

export function CoveragePanel({ now }: { now: number }) {
  const coverage = useCoverage(COVERAGE_DAYS);
  const sources = useSources();
  const host = useHost();
  const days = utcDays(COVERAGE_DAYS, now);
  const firstPhoneDay = COVERAGE_DAYS - PHONE_DAYS;

  return (
    <Panel id="coverage" title="Coverage" note="One cell per UTC day · newest on the right">
      {coverage.isPending || sources.isPending ? (
        <div className="flex flex-col gap-2 p-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-4 w-full" />
          ))}
        </div>
      ) : coverage.isError ? (
        <PanelError title="Couldn't load coverage" error={coverage.error} retry={() => coverage.refetch()} />
      ) : sources.isError ? (
        <PanelError title="Couldn't load sources" error={sources.error} retry={() => sources.refetch()} />
      ) : coverage.data.length === 0 ? (
        <EmptyState icon={CalendarDays} size="sm" title="No coverage yet">
          Each source&apos;s days fill in here as runs land. Missed runs show as hatched gaps; history is never backfilled.
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-3 p-4">
          <div className="flex flex-col gap-1.5">
            {coverageRows(coverage.data, sources.data, days).map((row) => (
              <div key={row.key} className="grid grid-cols-[6.5rem_1fr] items-center gap-3 sm:grid-cols-[9rem_1fr]">
                <span className="truncate text-label text-muted-foreground" title={row.name}>
                  {row.name}
                </span>
                <div
                  role="img"
                  aria-label={`${row.name}, last ${COVERAGE_DAYS} days: ${summary(row.cells)}`}
                  className="grid h-4 grid-cols-30 gap-px md:grid-cols-90"
                >
                  {row.cells.map((c, i) => {
                    const style = cellStyle[c?.status ?? "none"];
                    const title = c
                      ? `${dayLabel(days[i])} · ${style.label} · ${c.runs} runs · ${c.rows} rows · ${c.successful_targets}/${c.targets} targets · ${COVERAGE_API}`
                      : `${dayLabel(days[i])} · No data`;
                    return <span key={days[i]} title={title} className={cn("rounded-xs", style.className, i < firstPhoneDay && "max-md:hidden")} />;
                  })}
                </div>
              </div>
            ))}
            <div className="grid grid-cols-[6.5rem_1fr] gap-3 text-micro text-subtle-foreground sm:grid-cols-[9rem_1fr]">
              <span />
              <span className="flex justify-between">
                <span className="max-md:hidden">{dayLabel(days[0])}</span>
                <span className="md:hidden">{dayLabel(days[firstPhoneDay])}</span>
                <span>{dayLabel(days.at(-1)!)} (today, UTC)</span>
              </span>
            </div>
          </div>

          <ul aria-label="Legend" className="flex flex-wrap gap-x-4 gap-y-1.5 text-label text-muted-foreground">
            {(["success", "partial", "failed", "gap", "filled", "running", "none"] as const).map((s) => (
              <li key={s} className="flex items-center gap-1.5">
                <span aria-hidden className={cn("size-3 rounded-xs", cellStyle[s].className)} />
                {cellStyle[s].label}
              </li>
            ))}
          </ul>

          <OpenGaps names={new Map(sources.data.map((s) => [s.key, s.name]))} host={host} />
        </div>
      )}
    </Panel>
  );
}

const SHOWN_GAPS = 8;

function OpenGaps({ names, host }: { names: Map<string, string>; host: ReturnType<typeof useHost> }) {
  if (host.isPending || host.isError) return null; // the host card shows its own loading and error state
  const ranges = mergeGaps(host.data.open_gaps);
  if (ranges.length === 0) {
    return <p className="border-t border-border-subtle pt-3 text-data text-muted-foreground">No open gaps in the last 90 days.</p>;
  }
  return (
    <div className="flex flex-col gap-2 border-t border-border-subtle pt-3">
      <h3 className="text-data font-medium text-foreground">
        Open gaps <span className="font-normal text-subtle-foreground">· {ranges.length} ranges, newest first · feature dates touching them carry gap flags</span>
      </h3>
      <ScrollCue label="Open gaps">
        <table className="zone-data w-full min-w-150">
          <thead>
            <tr className="text-left text-label text-muted-foreground">
              <th scope="col" className="h-7 pr-3 font-medium">Source</th>
              <th scope="col" className="pr-3 font-medium">Missed (UTC)</th>
              <th scope="col" className="num pr-3 font-medium">Slots</th>
              <th scope="col" className="pr-3 font-medium">Reason</th>
            </tr>
          </thead>
          <tbody>
            {ranges.slice(0, SHOWN_GAPS).map((r) => (
              <tr key={`${r.source_key} ${r.reason} ${r.start}`} className="row-h-compact border-t border-border-subtle">
                <td className="pr-3 text-foreground">{names.get(r.source_key) ?? r.source_key}</td>
                <td className="pr-3 whitespace-nowrap text-foreground" title="GET /v1/admin/host">
                  {formatUtc(r.start)} → {formatUtc(r.end)}
                </td>
                <td className="num pr-3">{r.slots}</td>
                <td className="pr-3 text-muted-foreground">{reasonLabel[r.reason] ?? r.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollCue>
      {ranges.length > SHOWN_GAPS && <p className="text-label text-subtle-foreground">{ranges.length - SHOWN_GAPS} older ranges not shown.</p>}
    </div>
  );
}

/**
 * A keyboard-scrollable region that fades the edge hiding columns and points a chevron at them (imp-069).
 * Nothing shows when the content fits; the cue is static, so there is no motion to reduce.
 */
function ScrollCue({ label, children }: { label: string; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [left, setLeft] = useState(false);
  const [right, setRight] = useState(false);
  const update = useCallback(() => {
    const el = ref.current!;
    setLeft(el.scrollLeft > 1);
    setRight(el.scrollWidth - el.clientWidth - el.scrollLeft > 1);
  }, []);
  useEffect(() => {
    const el = ref.current!;
    const resize = new ResizeObserver(update); // also fires once on observe, for the first paint
    resize.observe(el);
    resize.observe(el.firstElementChild!);
    return () => resize.disconnect();
  }, [update]);

  const edge = "pointer-events-none absolute inset-y-0 flex w-10 pt-1.5 text-muted-foreground";
  return (
    <div className="relative">
      <div ref={ref} role="region" aria-label={label} tabIndex={0} onScroll={update} className="overflow-x-auto">
        {children}
      </div>
      {left && (
        <span aria-hidden data-scroll-cue="left" className={cn(edge, "left-0 bg-linear-to-r from-card from-40%")}>
          <ChevronLeft className="size-4" />
        </span>
      )}
      {right && (
        <span aria-hidden data-scroll-cue="right" className={cn(edge, "right-0 justify-end bg-linear-to-l from-card from-40%")}>
          <ChevronRight className="size-4" />
        </span>
      )}
    </div>
  );
}
