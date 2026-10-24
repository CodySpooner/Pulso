"use client";

import { ArrowDown, CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";

import { EmptyState } from "@/components/pulso/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useCoreDown, useCoverage, useHost, useOlderGaps, useSources } from "./api";
import { Panel, PanelError, StaleLine } from "./atoms";
import { LoadMore } from "./load-more";
import { coverageRows, gapReasons, gapsNote, mergeGaps, plural, utcDays, type CoverageDay, type MissedSlot } from "./model";

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

const legend = (
  <ul aria-label="Legend" className="flex flex-wrap gap-x-4 gap-y-1.5 text-label text-muted-foreground">
    {(["success", "partial", "failed", "gap", "filled", "running", "none"] as const).map((s) => (
      <li key={s} className="flex items-center gap-1.5">
        <span aria-hidden className={cn("size-3 rounded-xs", cellStyle[s].className)} />
        {cellStyle[s].label}
      </li>
    ))}
  </ul>
);

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
  const coreDown = useCoreDown();
  const days = utcDays(COVERAGE_DAYS, now);
  const firstPhoneDay = COVERAGE_DAYS - PHONE_DAYS;

  return (
    <Panel id="coverage" title="Coverage" note="One cell per UTC day · newest on the right">
      {coverage.isRefetchError && !coreDown && (
        <StaleLine what="Couldn't refresh coverage" error={coverage.error} asOf={coverage.dataUpdatedAt} retry={() => coverage.refetch()} />
      )}
      {coverage.isPending || sources.isPending ? (
        // The loaded layout (imp-082): a row per Phase 1 source, the axis line, the legend and an open-gaps
        // block sized for a heading and two ranges, so nothing below moves when the data lands.
        <div className="flex flex-col gap-3 p-4">
          <div aria-hidden className="flex flex-col gap-1.5">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="grid grid-cols-[6.5rem_1fr] items-center gap-3 sm:grid-cols-[9rem_1fr]">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-4" />
              </div>
            ))}
            <div className="h-3.5" />
          </div>
          {legend}
          <div aria-hidden className="flex flex-col gap-2 border-t border-border-subtle pt-3">
            <Skeleton className="h-4.5 w-72 max-w-full" />
            <div>
              {["h-7", "row-h-compact border-t", "row-h-compact border-t"].map((row, i) => (
                <div key={i} className={cn("flex items-center border-border-subtle", row)}>
                  <Skeleton className="h-4 w-full" />
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : coverage.isLoadingError ? (
        <PanelError title="Couldn't load coverage" error={coverage.error} retry={() => coverage.refetch()} />
      ) : sources.isLoadingError ? (
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

          {legend}

          <OpenGaps names={new Map(sources.data.map((s) => [s.key, s.name]))} host={host} />
        </div>
      )}
    </Panel>
  );
}

const SHOWN_GAPS = 8;
export const OPEN_GAPS_ID = "open-gaps";

/**
 * An Overdue source's missed slot, then its reason on a line of its own, as an in-page link to the Open gaps table
 * (imp-124). Following it focuses the table's heading, or calls `onFollow` instead (the run drawer closes first).
 */
export function GapsLink({ missed, onFollow }: { missed: MissedSlot; onFollow?: () => void }) {
  // Each slot phrase stays whole, whatever the font's widths, so the line breaks only between phrases (p1-53).
  const slot = missed.slot.map((phrase, i) => (
    <Fragment key={i}>
      {i > 0 && " "}
      <span className="whitespace-nowrap">{phrase}</span>
    </Fragment>
  ));
  const lines = missed.reason ? [slot, missed.reason] : [slot];
  return (
    <a
      href={`#${OPEN_GAPS_ID}`}
      onClick={(e) => {
        // Focus scrolls only as far as needed. A fragment jump also scrolls the document, which at lg sits behind
        // the shell's own scroller (escaped absolute boxes make it taller), so the whole shell would shift up.
        e.preventDefault();
        if (onFollow) onFollow();
        else document.getElementById(OPEN_GAPS_ID)?.focus();
      }}
      className="relative hit-area flex w-fit flex-col rounded-sm underline decoration-border-strong underline-offset-2 hover:decoration-current">
      {lines.map((line, i) => (
        <span key={i}>
          {line}
          {i === lines.length - 1 && <ArrowDown aria-hidden className="ml-0.5 inline size-3 align-[-2px]" />}
        </span>
      ))}
      <span className="sr-only"> (in Open gaps)</span>
    </a>
  );
}

function OpenGaps({ names, host }: { names: Map<string, string>; host: ReturnType<typeof useHost> }) {
  const older = useOlderGaps(host.data?.next_cursor ?? null);
  if (!host.data) return null; // the host card shows its own loading, error and stale state (imp-132)
  // Ranges merge across pages, so a range cut by a page boundary reads as one (DEC-166).
  const gaps = [host.data.open_gaps, ...older.pages.map((p) => p.open_gaps)].flat();
  const ranges = mergeGaps(gaps);
  const shown = older.on ? ranges : ranges.slice(0, SHOWN_GAPS);
  const hidden = ranges.length - shown.length;
  if (ranges.length === 0) {
    return <p className="border-t border-border-subtle pt-3 text-data text-muted-foreground">No open gaps in the last 90 days.</p>;
  }
  return (
    <div className="flex flex-col gap-2 border-t border-border-subtle pt-3">
      {/* The target of GapsLink: following it focuses this heading; the scroll margin clears the phone's top bar. */}
      <h3 id={OPEN_GAPS_ID} tabIndex={-1} className="scroll-mt-18 text-data font-medium text-foreground lg:scroll-mt-4">
        Open gaps <span className="font-normal text-subtle-foreground">· {plural(ranges.length, "range")}{older.hasMore ? " loaded" : ""}, newest first · feature dates touching them carry gap flags</span>
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
            {shown.map((r) => (
              <tr key={`${r.source_key} ${r.reason} ${r.start}`} className="row-h-compact border-t border-border-subtle">
                <td className="pr-3 text-foreground">{names.get(r.source_key) ?? r.source_key}</td>
                <td className="pr-3 whitespace-nowrap text-foreground" title="GET /v1/admin/host">
                  {formatUtc(r.start)} → {formatUtc(r.end)}
                </td>
                <td className="num pr-3">{r.slots}</td>
                <td className="pr-3 text-muted-foreground">{gapReasons[r.reason] ?? r.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollCue>
      {(ranges.length > SHOWN_GAPS || host.data.next_cursor) && (
        <LoadMore
          note={gapsNote(shown.length, ranges.length, gaps.length, older.hasMore)}
          label={older.hasMore ? "Load older gaps" : `Show ${plural(hidden, "older range")}`}
          more={hidden > 0 || older.hasMore}
          pending={older.pending}
          error={older.error}
          errorTitle="Couldn't load older gaps"
          onLoad={older.load}
        />
      )}
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
