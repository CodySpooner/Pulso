import type { components } from "@/lib/api/schema";

// UX-5 (vault Features/Product Page - Trends): the Trends tab's pure parts. The API sends a point only for a UTC
// day the source collected (DEC-245); everything here keeps that: a day without a point is null, never filled in.

type S = components["schemas"];
export type Series = S["Series"];
export type Point = S["Point"];
/** openapi-fetch drops a key typed only `null`, so a MissingSeries is told apart by `reason` (like Stat). */
export type Missing = { metric: S["MissingSeries"]["metric"]; reason: string; value?: null };
export type AnySeries = Series | Missing;
export const hasData = (s: AnySeries): s is Series => !("reason" in s);

export const RANGES = [
  { value: "7d", label: "7D", days: 7 },
  { value: "30d", label: "30D", days: 30 },
  { value: "90d", label: "90D", days: 90 },
  { value: "all", label: "All", days: null },
] as const;
export type Range = (typeof RANGES)[number]["value"];
export const DEFAULT_RANGE: Range = "90d"; // shared with Overview (vault Features/Product Page, URL scheme)

/** The panes, top to bottom. `metrics` share a pane and are never summed (two demand families stay two lines). */
export const PANES = [
  { key: "demand", label: "Order velocity", unit: "units per 7 days", metrics: ["velocity_js", "velocity_bumps"], color: 1 },
  { key: "price", label: "Retail price", unit: "USD, lowest to highest", metrics: ["price"], color: 3 },
  { key: "stores", label: "Stores selling it", unit: "stores", metrics: ["store_count"], color: 5 },
  { key: "search", label: "Search interest", unit: "index, 0 to 100", metrics: ["search"], color: 2 },
  { key: "ads", label: "Ad count", unit: "active ads", metrics: ["ads"], color: 4 },
] as const;
export type Pane = (typeof PANES)[number];
export type PaneKey = Pane["key"];

/** Chart geometry shared by the canvas grids and the HTML pane headers laid over them, in px. */
export const LAYOUT = { header: 44, pane: 120, inset: 10, axis: 28, left: 8, right: 60 } as const; // inset: air between a header and its plot

/** A pane as the chart draws it: its lines (one per series, never summed), gap bands and formatters. */
export type ChartPane = {
  key: PaneKey;
  label: string;
  color: number; // --series-n
  lines: { series: Series; name: string; dashed?: boolean }[];
  bands: { from: number; to: number }[];
  format: (p: Point) => string;
  tick: (v: number) => string;
};

export const DAY = 86_400_000;
export const dayMs = (day: string) => Date.parse(`${day}T00:00:00Z`);
const isoDay = (ms: number) => new Date(ms).toISOString().slice(0, 10);

/** The UTC days a range shows, oldest first: the last n days up to `end`, or the real first day for All. */
export function windowDays(range: Range, start: string, end: string): string[] {
  const days = RANGES.find((r) => r.value === range)?.days ?? null;
  const last = dayMs(end);
  const first = days === null ? Math.min(dayMs(start), last) : last - (days - 1) * DAY;
  return Array.from({ length: Math.round((last - first) / DAY) + 1 }, (_, i) => isoDay(first + i * DAY));
}

/** One slot per window day: that day's point, or null. A null breaks the line; nothing is interpolated. */
export function align(series: Series, days: string[]): (Point | null)[] {
  const byDay = new Map(series.points.map((p) => [p.day, p]));
  return days.map((d) => byDay.get(d) ?? null);
}

/** The window's gap days of these series, consecutive days merged into one [from, to) band in UTC ms. */
export function gapBands(series: Series[], days: string[]): { from: number; to: number }[] {
  const inWindow = new Set(days);
  const gapDays = [...new Set(series.flatMap((s) => s.gaps.map((g) => g.day)))].filter((d) => inWindow.has(d)).sort();
  const bands: { from: number; to: number }[] = [];
  for (const day of gapDays) {
    const from = dayMs(day);
    const last = bands.at(-1);
    if (last && last.to === from) last.to = from + DAY;
    else bands.push({ from, to: from + DAY });
  }
  return bands;
}

/** Range and switched-on panes from the URL. A missing `overlay` means every pane with data is on. */
export function readState(params: URLSearchParams): { range: Range; overlay: PaneKey[] | null } {
  const range = RANGES.find((r) => r.value === params.get("range"))?.value ?? DEFAULT_RANGE;
  const raw = params.get("overlay");
  const on = raw?.split(",") ?? [];
  return { range, overlay: raw === null ? null : PANES.map((p) => p.key).filter((k) => on.includes(k)) };
}

/** The query string after a change, other params kept; defaults leave the URL so a clean URL means "defaults". */
export function writeState(search: string, range: Range, overlay: PaneKey[] | null, available: PaneKey[]): string {
  const params = new URLSearchParams(search);
  if (range === DEFAULT_RANGE) params.delete("range");
  else params.set("range", range);
  if (overlay === null || available.every((k) => overlay.includes(k))) params.delete("overlay");
  else params.set("overlay", overlay.join(","));
  return params.toString();
}
