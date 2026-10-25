import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { NOW, problem } from "../data-health/fixtures";

// p2-09 (UX-5): fixture GET /v1/products/{id}/series responses, never a database restore. Relative to Data Health's
// NOW (mockAdminApi pins page.clock to it). Three weeks of history with real holes, the way the API sends them:
// days -9 and -8 are a collection gap, every run failed on day -3, and day -14 has no record at all.

type S = components["schemas"];
const day = (ago: number) => new Date(NOW.getTime() - ago * 86_400_000).toISOString().slice(0, 10);
const at = (ago: number, time = "06:00") => `${day(ago)}T${time}:00Z`;

export const GAP_DAYS = [day(9), day(8)];
const gaps: S["SeriesGap"][] = [
  { day: day(9), status: "gap" },
  { day: day(8), status: "gap" },
  { day: day(3), status: "failed" },
];
const holes = new Set([...GAP_DAYS, day(3), day(14)]);
const observed = (from: number, to = 0) => Array.from({ length: from - to + 1 }, (_, i) => from - i).filter((ago) => !holes.has(day(ago)));

function series(metric: S["Series"]["metric"], unit: S["Series"]["unit"], days: number[], value: (ago: number) => [number, number | null], method: string | null = null): S["Series"] {
  const points = days.map((ago) => {
    const [v, high] = value(ago);
    // A velocity feature for day d ends at d + 1 00:00Z; a snapshot is the day's 06:00 capture.
    return { day: day(ago), value: v, high, as_of: method ? at(ago - 1, "00:00") : at(ago) };
  });
  return { metric, unit, source: "shopify_stores", source_name: "Shopify stores", method, as_of: points.at(-1)?.as_of ?? at(0), stale: false, points, gaps };
}
const missing = (metric: S["MissingSeries"]["metric"], reason: string) => ({ metric, value: null, reason }) as S["MissingSeries"];
const SEARCH = missing("search", "No search interest is collected for this product's keywords yet. Confirmed keywords join the weekly Google Trends fetch in a later step.");
const ADS = missing("ads", "No ad source yet. Ad counts arrive in Phase 8 or by CSV import.");
const NO_JS = missing("velocity_js", "No velocity computed from Shopify inventory drops yet.");

/** Price slips from $24 as sellers pile in (3 → 7 stores) while bump velocity climbs: saturation starting. */
export const trendsSeries: S["ProductSeries"] = {
  id: "3f6c1e52-8a7d-4b0e-9c21-5d4e8f7a6b13",
  range: "all",
  start: day(20),
  end: day(0),
  series: [
    series("price", "usd_minor", observed(20), (ago) => [ago > 6 ? 2400 : 2400 - (7 - ago) * 30, 3999]),
    series("store_count", "stores", observed(20), (ago) => [ago > 12 ? 3 : ago > 5 ? 5 : 7, null]),
    SEARCH,
    NO_JS,
    series("velocity_bumps", "units_7d", observed(20, 1), (ago) => [Math.round(41 - ago * 1.6), null], "Shopify updated_at bumps, a lower bound (grade B)"),
    ADS,
  ],
};

/** Four days in: the short-history note shows. */
export const shortHistory: S["ProductSeries"] = {
  ...trendsSeries,
  start: day(4),
  series: trendsSeries.series.map((s) => ("points" in s ? { ...s, points: s.points.filter((p) => p.day >= day(4)), gaps: s.gaps.filter((g) => g.day >= day(4)) } : s)),
};

/** Matched but never collected: every pane says why it has nothing. */
export const noHistory: S["ProductSeries"] = {
  ...trendsSeries,
  start: day(0),
  series: [
    missing("price", "No store listing matched yet."),
    missing("store_count", "No store listing matched yet."),
    SEARCH,
    NO_JS,
    missing("velocity_bumps", "No velocity computed from Shopify updated_at bumps yet."),
    ADS,
  ],
};

/** The store crawler last captured 3 days ago, past twice its interval. */
export const staleSeries: S["ProductSeries"] = {
  ...trendsSeries,
  series: trendsSeries.series.map((s) => ("points" in s ? { ...s, stale: true, as_of: at(3), points: s.points.filter((p) => p.day <= day(4)) } : s)),
};

/** GET /v1/products/{id}/series answering `body` (or `status` with a problem; `hold` never answers). Register after
 *  mockProductApi: Playwright tries the newest route first. Returns the series requests' URLs. */
export async function mockSeriesApi(page: Page, options: { body?: S["ProductSeries"]; status?: number; hold?: boolean } = {}) {
  const calls: URL[] = [];
  await page.route("**/api/v1/products/*/series*", async (route) => {
    calls.push(new URL(route.request().url()));
    if (options.hold) return;
    if (options.status) return route.fulfill({ status: options.status, contentType: "application/problem+json", json: problem(options.status, `e2e-series-${options.status}`) });
    return route.fulfill({ json: options.body ?? trendsSeries });
  });
  return calls;
}
