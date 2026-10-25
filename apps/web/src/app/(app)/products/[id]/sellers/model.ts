// Pure helpers for the Sellers tab (UX-7, DEC-247): the filter chip in the URL, the API query it maps to, and the
// words and geometry the tab renders.

import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];
// openapi-fetch drops a key typed only `null` from responses (DEC-238 g): NoSource's value and Band's low and high.
export type Row = Omit<Schemas["SellerRow"], "running_ads"> & { running_ads: { reason: string } };
export type Page = Omit<Schemas["SellersPage"], "rows" | "band"> & { rows: Row[]; band: Pick<Schemas["Band"], "reason"> };
export type Day = Schemas["SeriesDay"];

// One chip at a time, in the order F cycles them. Active only is the default and never written to the URL.
export const FILTERS = { active: "Active only", all: "Include delisted", new: "New in 14 d", tracked: "Tracked only" } as const;
export type Filter = keyof typeof FILTERS;
const ORDER = Object.keys(FILTERS) as Filter[];
const PARAM = "sellers";

export const parseFilter = (params: URLSearchParams): Filter => ORDER.find((f) => f !== "active" && f === params.get(PARAM)) ?? "active";

/** The query string with `filter` set and every other parameter (the tab, for one) kept, without the `?`. */
export function filterSearch(search: string, filter: Filter): string {
  const params = new URLSearchParams(search);
  if (filter === "active") params.delete(PARAM);
  else params.set(PARAM, filter);
  return params.toString();
}

export const nextFilter = (filter: Filter): Filter => ORDER[(ORDER.indexOf(filter) + 1) % ORDER.length];

export function apiQuery(filter: Filter) {
  return { all: { include_delisted: true }, new: { new_14d: true }, tracked: { tracked: true }, active: {} }[filter];
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
export const money = (minor: number) => usd.format(minor / 100);

/** A price in the currency the store lists it in; the exponent comes from Intl (JPY 0, KWD 3). */
export function original(minor: number, currency: string): string {
  const format = new Intl.NumberFormat("en-US", { style: "currency", currency });
  return format.format(minor / 10 ** (format.resolvedOptions().maximumFractionDigits ?? 2));
}

export const day = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

export const UNKNOWN: Record<NonNullable<Row["unknown_reason"]>, string> = {
  last_crawl_incomplete: "The store's last crawl didn't finish, so Pulso can't tell whether the listing is still up. Only a complete crawl marks a listing delisted.",
  store_blocked: "The store blocked the crawler, so Pulso can't check its catalog.",
  store_untrackable: "The store is headless or password-protected, so Pulso can't read its catalog.",
  never_crawled: "No crawl of this store has finished yet; the listing came from an import or a single fetch.",
};

/** Dot positions (0..1) along the strip plot, or null with nothing to place. One price sits in the middle. */
export function stripScale(min: number | null, max: number | null): ((price: number) => number) | null {
  if (min === null || max === null) return null;
  return max === min ? () => 0.5 : (price) => (price - min) / (max - min);
}

/** The sparkline's polyline segments over observed days only: a gap day breaks the line, never bridges it. */
export function sparkSegments(days: Day[], width: number, height: number): string[] {
  const top = Math.max(1, ...days.map((d) => d.active ?? 0));
  const step = days.length > 1 ? width / (days.length - 1) : 0;
  const segments: string[] = [];
  let current: string[] = [];
  days.forEach((d, i) => {
    if (d.active === null) {
      if (current.length) segments.push(current.join(" "));
      current = [];
      return;
    }
    current.push(`${(i * step).toFixed(1)},${(height - (d.active / top) * height).toFixed(1)}`);
  });
  if (current.length) segments.push(current.join(" "));
  return segments;
}
