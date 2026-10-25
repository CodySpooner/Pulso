"use client";

import { Fragment, useMemo } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { LayoutGroup } from "motion/react";
import * as m from "motion/react-m";
import { ChartLine, Info, TriangleAlert } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { PanelError, StaleLine } from "@/components/data-health/atoms";
import { EmptyState } from "@/components/pulso/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { $api } from "@/lib/api/client";
import { formatUtc } from "@/lib/format";
import { spring } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { AmazonSection } from "./amazon";
import { KeywordsSection } from "./keywords";
import {
  align, hasData, LAYOUT, PANES, RANGES, readState, gapBands, windowDays, writeState,
  type AnySeries, type ChartPane, type PaneKey, type Point, type Range, type Series,
} from "./trends-model";

// UX-5 (vault Features/Product Page - Trends). One request for the whole history; a range only moves the window,
// so switching it is instant and never refetches. States (vault Design/UI States): skeleton, error with Retry,
// stale line, no history yet, short history, no source yet, insufficient signal, gaps, no point in this range.
const TrendsChart = dynamic(() => import("./trends-chart"), { ssr: false, loading: () => <PaneSkeletons n={3} /> });

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const money = (minor: number) => usd.format(minor / 100);
const count = (n: number) => n.toLocaleString("en-US");
const compact = new Intl.NumberFormat("en-US", { notation: "compact" });
const FORMAT: Record<PaneKey, Pick<ChartPane, "format" | "tick">> = {
  demand: { format: (p) => `${count(p.value)} units`, tick: (v) => compact.format(v) },
  price: { format: (p) => (p.high != null && p.high !== p.value ? `${money(p.value)}–${money(p.high)}` : money(p.value)), tick: (v) => `$${compact.format(v / 100)}` },
  stores: { format: (p) => count(p.value), tick: (v) => compact.format(v) },
  search: { format: (p) => String(p.value), tick: (v) => compact.format(v) },
  ads: { format: (p) => count(p.value), tick: (v) => compact.format(v) },
};
const LINE: Record<string, { name: string; dashed?: boolean }> = {
  velocity_js: { name: "Inventory drops (A)" },
  velocity_bumps: { name: "Updated-at bumps (B, lower bound)", dashed: true },
  price: { name: "Retail price" },
  store_count: { name: "Stores" },
};
const SWATCH = ["bg-chart-1", "bg-chart-2", "bg-chart-3", "bg-chart-4", "bg-chart-5"];
// The gap legend's swatch: the canvas hatch, drawn in CSS from the same token.
const HATCH = "bg-[repeating-linear-gradient(135deg,var(--muted-foreground)_0_1px,transparent_1px_4px)] opacity-60";

export function TrendsTab({ id }: { id: string }) {
  return (
    <>
      <SeriesView id={id} />
      <KeywordsSection id={id} />
      <AmazonSection id={id} />
    </>
  );
}

function SeriesView({ id }: { id: string }) {
  const params = useSearchParams();
  const query = $api.useQuery("get", "/v1/products/{product_id}/series", { params: { path: { product_id: id }, query: { range: "all" } } }, { enabled: useApiReady() });
  const { data, error } = query;
  const retry = () => void query.refetch();
  if (!data)
    return query.isError ? (
      <PanelError headingLevel="h2" size="md" title="Couldn't load the trends" error={error} retry={retry} />
    ) : (
      <div className="flex flex-col gap-4 p-4">
        <span className="sr-only" role="status">
          Loading trends…
        </span>
        <Skeleton className="h-8 w-72 max-w-full" />
        <PaneSkeletons n={3} />
      </div>
    );
  return (
    <div className="flex flex-col gap-4 p-4">
      {query.isError && <StaleLine boxed what="Couldn't refresh the trends" error={error} asOf={query.dataUpdatedAt} retry={retry} />}
      <Loaded series={data.series as AnySeries[]} start={data.start} end={data.end} params={params} />
    </div>
  );
}

/** Everything the tab draws, from the response and the two URL params; pure, so one memo covers it. */
function buildView(series: AnySeries[], start: string, end: string, rangeParam: string | null, overlayParam: string | null) {
  const params = new URLSearchParams();
  if (rangeParam !== null) params.set("range", rangeParam);
  if (overlayParam !== null) params.set("overlay", overlayParam);
  const { range, overlay } = readState(params);
  const byMetric = new Map(series.map((s) => [s.metric as string, s]));
  const withData = PANES.filter((p) => p.metrics.some((metric) => { const s = byMetric.get(metric); return !!s && hasData(s); }));
  const available = withData.map((p) => p.key);
  const on = overlay ?? available;
  const days = windowDays(range, start, end);
  const panes: ChartPane[] = withData
    .filter((p) => on.includes(p.key))
    .map((p) => {
      const lines = p.metrics.map((metric) => byMetric.get(metric)).filter((s): s is Series => !!s && hasData(s));
      return { key: p.key, label: p.label, color: p.color, ...FORMAT[p.key], bands: gapBands(lines, days), lines: lines.map((s) => ({ series: s, ...LINE[s.metric] })) };
    });
  return { range, byMetric, withData, available, on, days, panes };
}

function Loaded({ series, start, end, params }: { series: AnySeries[]; start: string; end: string; params: URLSearchParams }) {
  const rangeParam = params.get("range");
  const overlayParam = params.get("overlay");
  const view = useMemo(() => buildView(series, start, end, rangeParam, overlayParam), [series, start, end, rangeParam, overlayParam]);
  const { range, byMetric, withData, available, on, days, panes } = view;
  // Clicks build on the URL, not this render: Next syncs useSearchParams in a transition, so a quick second
  // click can land before the re-render and would undo the first (imp-278).
  const current = () => readState(new URLSearchParams(window.location.search));
  const set = (nextRange: Range, nextOverlay: PaneKey[] | null) => {
    const query = writeState(window.location.search, nextRange, nextOverlay, available);
    window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
  };
  const toggle = (key: PaneKey) => {
    const now = current();
    const shown = now.overlay ?? available;
    set(now.range, shown.includes(key) ? shown.filter((k) => k !== key) : PANES.map((p) => p.key).filter((k) => k === key || shown.includes(k)));
  };

  const observed = new Set(series.filter(hasData).flatMap((s) => s.points.map((p) => p.day))).size;
  const gapDays = new Set(panes.flatMap((p) => p.lines.flatMap((l) => l.series.gaps.map((g) => g.day))).filter((d) => days.includes(d))).size;
  const missing = PANES.filter((p) => !available.includes(p.key));
  const height = panes.length * (LAYOUT.header + LAYOUT.pane) + LAYOUT.axis;
  const summary = `Trends chart, ${formatDay(days[0])} to ${formatDay(days[days.length - 1])} UTC. ${panes
    .map((p) => `${p.label}: ${latestText(p, days) ?? "no point in this range"}`)
    .join(". ")}. ${gapDays ? `${gapDays} collection gap ${gapDays === 1 ? "day" : "days"}.` : "No collection gaps."}`;

  return (
    <>
      {withData.length > 0 && (
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <LayoutGroup id="trends-range">
          <div role="group" aria-label="Range" className="flex h-(--button-h-md) shrink-0 rounded-md border border-border bg-secondary p-0.5">
            {RANGES.map((r) => (
              <button
                key={r.value}
                type="button"
                aria-pressed={range === r.value}
                onClick={() => set(r.value, current().overlay)}
                className={cn(
                  "relative hit-area rounded-sm px-3 text-label font-medium transition-colors duration-(--duration-fast) ease-standard",
                  range === r.value ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {range === r.value && <m.span layoutId="trends-range" transition={spring.snappy} className="absolute inset-0 rounded-sm segment-thumb" />}
                <span className="relative font-mono">{r.label}</span>
              </button>
            ))}
          </div>
        </LayoutGroup>
        {withData.length > 1 && (
          <div role="group" aria-label="Panes" className="flex flex-wrap items-center gap-1.5">
            {withData.map((p) => (
              <button
                key={p.key}
                type="button"
                aria-pressed={on.includes(p.key)}
                onClick={() => toggle(p.key)}
                className="relative hit-area flex h-(--button-h-md) items-center gap-1.5 rounded-md border border-border px-2.5 text-label text-muted-foreground transition-colors duration-(--duration-fast) ease-standard hover:text-foreground aria-pressed:border-border-strong aria-pressed:bg-secondary aria-pressed:text-foreground"
              >
                <span aria-hidden className={cn("size-2 rounded-full", on.includes(p.key) ? SWATCH[p.color - 1] : "border border-current")} />
                {p.label}
              </button>
            ))}
          </div>
        )}
        {gapDays > 0 && (
          <p className="flex items-center gap-1.5 text-label text-muted-foreground sm:ml-auto">
            <span aria-hidden className={cn("h-3 w-4 rounded-sm border border-border", HATCH)} />
            Collection gap · {gapDays} {gapDays === 1 ? "day" : "days"}, no data
          </p>
        )}
      </div>
      )}

      {observed > 0 && observed < 7 && (
        <p className="flex items-start gap-2 rounded-lg border border-border bg-secondary px-3 py-2 text-data text-muted-foreground">
          <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          Only {observed} {observed === 1 ? "day" : "days"} of history so far. Trends need at least 7 before a direction means much.
        </p>
      )}

      {withData.length === 0 ? (
        <EmptyState
          icon={ChartLine}
          headingLevel="h2"
          title="No history for this product yet"
          action={
            <Button asChild variant="secondary">
              <Link href="/admin/data-health">Open Data Health</Link>
            </Button>
          }
        >
          A pane draws once a source has collected this product on at least one day. Each day is a real capture; Pulso never fills one in.
        </EmptyState>
      ) : panes.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-data text-muted-foreground">Every pane is off. Turn one on above.</p>
      ) : (
        <div className="relative" style={{ height }}>
          <TrendsChart panes={panes} days={days} summary={summary} />
          <div className="pointer-events-none relative">
            {panes.map((p) => (
              <Fragment key={p.key}>
                <PaneHeader pane={p} days={days} />
                <div style={{ height: LAYOUT.pane, paddingRight: LAYOUT.right }} className="grid place-items-center">
                  {p.lines.every((l) => !l.series.points.some((pt) => days.includes(pt.day))) && (
                    <p className="rounded-md bg-card px-2 py-1 text-label text-subtle-foreground">No point in this range</p>
                  )}
                </div>
              </Fragment>
            ))}
          </div>
        </div>
      )}

      {missing.length > 0 && (
        <ul className="flex flex-col gap-2" aria-label="Panes without data">
          {missing.map((p) => (
            <li key={p.key} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 rounded-lg border border-dashed border-border px-3 py-2.5">
              <span className="text-label font-medium text-foreground">{p.label}</span>
              <span className="text-label text-muted-foreground">· {p.key === "demand" ? "Insufficient signal" : "No source yet"}</span>
              <span className="basis-full text-micro text-subtle-foreground">
                {p.metrics.map((metric) => (byMetric.get(metric) as { reason?: string } | undefined)?.reason).filter(Boolean).join(" ")}
              </span>
            </li>
          ))}
        </ul>
      )}
      {withData.length > 0 && <p className="text-micro text-subtle-foreground">Daily points by UTC day. A day without a point wasn&apos;t collected; Pulso never fills one in.</p>}
    </>
  );
}

const shortDay = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
const formatDay = (day: string) => shortDay.format(new Date(`${day}T00:00:00Z`));

/** The pane's newest point in the window, formatted, with its day. */
function latest(pane: ChartPane, days: string[]): { point: Point; series: Series } | null {
  for (const line of pane.lines) {
    const point = align(line.series, days).findLast((p) => p !== null);
    if (point) return { point, series: line.series };
  }
  return null;
}
const latestText = (pane: ChartPane, days: string[]) => {
  const found = latest(pane, days);
  return found && `${pane.format(found.point)} on ${formatDay(found.point.day)}`;
};

/** Name, unit and the newest value on the right; source and the series' as of below, visible (not only on hover). */
function PaneHeader({ pane, days }: { pane: ChartPane; days: string[] }) {
  const found = latest(pane, days);
  const meta = PANES.find((p) => p.key === pane.key);
  const series = pane.lines[0].series;
  return (
    <div style={{ height: LAYOUT.header }} className="pointer-events-auto flex flex-col justify-end px-2">
      <div className="flex items-baseline justify-between gap-3">
        <p className="flex min-w-0 items-center gap-1.5 text-label font-medium text-foreground">
          <span aria-hidden className={cn("size-2 shrink-0 rounded-full", SWATCH[pane.color - 1])} />
          <span className="truncate">{pane.label}</span>
          <span className="hidden truncate font-normal text-subtle-foreground sm:inline">· {meta?.unit}</span>
        </p>
        <p className="shrink-0 font-mono text-data text-foreground" title={found ? `${formatDay(found.point.day)} · as of ${formatUtc(found.point.as_of)}` : undefined}>
          {found ? pane.format(found.point) : <span className="font-sans text-subtle-foreground">—</span>}
        </p>
      </div>
      <p className={cn("truncate text-micro text-subtle-foreground", series.stale && "text-warning")}>
        {series.stale && <TriangleAlert className="mr-1 inline size-3 align-[-2px]" aria-hidden />}
        {/* Velocity is Pulso's estimate: name the demand family (and its grade) before the source; phones keep the as of. */}
        {pane.key === "demand" && <span className="hidden sm:inline">{pane.lines.map((l) => l.name).join(" · ")} · </span>}
        {series.source_name} · as of <time dateTime={series.as_of}>{formatUtc(series.as_of)}</time>
        {series.stale && " · stale"}
      </p>
    </div>
  );
}

function PaneSkeletons({ n }: { n: number }) {
  return (
    <div className="flex flex-col">
      {Array.from({ length: n }, (_, i) => (
        <div key={i} style={{ height: LAYOUT.header + LAYOUT.pane }} className="flex flex-col justify-end gap-2 pb-1">
          <Skeleton className="h-3.5 w-40" />
          <Skeleton className="h-2.5 w-56 max-w-full" />
          <div className="mt-2 flex flex-1 flex-col justify-between border-y border-border-subtle py-2">
            <span />
            <Skeleton className="h-px w-full" />
          </div>
        </div>
      ))}
    </div>
  );
}
