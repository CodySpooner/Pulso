// Pure helpers for Watchlists (WF-2b, DEC-322): one patch that keeps the ★ the same in every cached product read, the
// 5-second undo window for removals, the "merged" note and the velocity sparkline's words (imp-419).

import type { QueryClient } from "@tanstack/react-query";

import type { components } from "@/lib/api/schema";

import type { Item } from "../discover/feed-views";

export type List = components["schemas"]["Watchlist"];
export type Spark = components["schemas"]["Spark"];
/** A list item as a response carries it: its product typed like a Discover row, and its sparkline or why there's none
 *  (openapi-fetch drops null-only keys). */
export type Row = Omit<components["schemas"]["WatchlistItem"], "product" | "spark"> & { product: Item; spark?: Spark | { reason: string; value?: null } | null };
export interface Watch {
  watched: boolean;
  watchlist_ids: string[];
}

/** `data` with every read of product `id` (a product header, a Discover row, a watchlist row's product) set by `next`;
 *  the same object when nothing changed, so untouched caches keep their identity. */
export function patchWatch<T>(data: T, id: string, next: (watch: Watch) => Watch): T {
  if (Array.isArray(data)) {
    const out = data.map((each) => patchWatch(each, id, next));
    return out.some((each, i) => each !== data[i]) ? (out as T) : data;
  }
  if (typeof data !== "object" || data === null) return data;
  const record = data as Record<string, unknown>;
  let out: Record<string, unknown> | null = null;
  for (const [key, value] of Object.entries(record)) {
    const patched = patchWatch(value, id, next);
    if (patched !== value) (out ??= { ...record })[key] = patched;
  }
  if (record.id === id && typeof record.watched === "boolean" && Array.isArray(record.watchlist_ids)) {
    const watch = next({ watched: record.watched, watchlist_ids: record.watchlist_ids as string[] });
    if (watch.watched !== record.watched || watch.watchlist_ids.join() !== record.watchlist_ids.join()) out = { ...(out ?? record), ...watch };
  }
  return (out ?? data) as T;
}

/** Applies `next` to every cached query, keeping each one's fetch time: a patch isn't a fresher read. */
export function applyWatch(client: QueryClient, id: string, next: (watch: Watch) => Watch) {
  for (const query of client.getQueryCache().getAll()) {
    const data = patchWatch(query.state.data, id, next);
    if (data !== query.state.data) client.setQueryData(query.queryKey, data, { updatedAt: query.state.dataUpdatedAt });
  }
}

const onList = (ids: string[], list: string, on: boolean) => (on ? [...new Set([...ids, list])] : ids.filter((each) => each !== list));
/** A product's watch once list `list` (Main when `main`) holds it or not. */
export const listed = (list: string, on: boolean, main: boolean) => (w: Watch): Watch => ({
  watched: main ? on : w.watched,
  watchlist_ids: onList(w.watchlist_ids, list, on),
});

/** Refetches the lists and their pages, and marks product reads stale: a removal or a move changed what they hold. Only
 *  queries on screen refetch, so a long Discover feed in the cache isn't reloaded behind the page. */
export const refreshWatchlists = (client: QueryClient, products = false) =>
  client.invalidateQueries({
    predicate: ({ queryKey: [, path] }) => typeof path === "string" && (path.startsWith("/v1/watchlists") || (products && path.startsWith("/v1/products"))),
  });

/** The list the page shows: the one in the URL, else Main, else the first. */
export const pickList = (lists: List[] | undefined, requested: string | null) =>
  lists?.find((l) => l.id === requested) ?? lists?.find((l) => l.name === "Main") ?? lists?.[0];

/** The item's product was merged after it was added: the row shows the survivor (DEC-314 d). */
export const isMerged = (row: Pick<Row, "product_id" | "product">) => row.product.id !== row.product_id;

export interface Removal {
  list: string;
  ids: string[];
  text: string;
}

/** One removal at a time: its rows hide at once and it commits after `ms` unless undone. A second removal, or leaving
 *  the page (`flush`), commits the first straight away. Nothing is sent before then, so an undo loses no `added_at`. */
export function undoWindow(commit: (removal: Removal) => void, onChange: (pending: Removal | null) => void, ms = 5000) {
  let pending: { removal: Removal; timer: ReturnType<typeof setTimeout> } | null = null;
  const settle = (send: boolean) => {
    if (!pending) return;
    clearTimeout(pending.timer);
    const { removal } = pending;
    pending = null;
    onChange(null);
    if (send) commit(removal);
  };
  return {
    remove(removal: Removal) {
      settle(true);
      pending = { removal, timer: setTimeout(() => settle(true), ms) };
      onChange(removal);
    },
    undo: () => settle(false),
    flush: () => settle(true),
  };
}

const shortDay = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
const short = (day: string) => shortDay.format(new Date(day));

/** The days a sparkline breaks, e.g. ["Oct 3 → Oct 5", "Oct 20"]: runs without a value after its first value. Days
 *  before that are before tracking began, not gaps. */
export function sparkGaps(points: Spark["points"]): string[] {
  const runs: [string, string][] = [];
  let seen = false;
  points.forEach((p, i) => {
    if (p.value !== null) seen = true;
    else if (seen && points[i - 1].value === null) runs.at(-1)![1] = p.day;
    else if (seen) runs.push([p.day, p.day]);
  });
  return runs.map(([from, to]) => (from === to ? short(from) : `${short(from)} → ${short(to)}`));
}

/** The sparkline's text alternative: its first and last values, and where it breaks. */
export function sparkLabel(spark: Spark): string {
  const values = spark.points.flatMap((p) => (p.value === null ? [] : [Math.round(p.value).toLocaleString("en-US")]));
  const range = values.length > 1 ? `${values[0]}/7d to ${values.at(-1)}/7d` : `${values[0]}/7d`;
  const gaps = sparkGaps(spark.points);
  return `Velocity, last ${spark.points.length} days: ${range}${gaps.length ? `, no data ${gaps.join(", ")}` : ""}`;
}
