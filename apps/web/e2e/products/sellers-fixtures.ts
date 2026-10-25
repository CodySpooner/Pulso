import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { NOW, problem } from "../data-health/fixtures";
import { mockProductApi, product } from "./fixtures";

// p2-11 (UX-7): fixture GET /v1/products/{id}/sellers responses for the Sellers tab e2e tests and screenshots, never a
// database restore. Times are relative to Data Health's NOW, which mockAdminApi pins with page.clock.

type S = components["schemas"];
type Row = S["SellerRow"];
const at = (hoursAgo: number) => new Date(NOW.getTime() - hoursAgo * 3_600_000).toISOString();
const ads = { value: null, reason: "No ad source yet: ad data arrives in Phase 8 or by CSV." };

let id = 7000;
function row(domain: string, over: Partial<Row> = {}): Row {
  return {
    listing_id: id++, url: `https://${domain}/products/sunset-lamp`, store_id: id, domain, platform: "shopify", tracked: false, untrackable: false,
    price_usd_minor: 2499, price_minor: 2499, price_max_minor: null, currency: "USD", fx_missing: false,
    started_at: at(24 * 40), started_basis: "store", listed: "listed", delisted_at: null, unknown_reason: null,
    last_seen: at(3), stale: false, running_ads: ads, source_name: "Shopify stores", as_of: at(6), raw_payload_id: 903000 + id, ...over,
  };
}

export const ROWS: Row[] = [
  row("nightsky-decor.com", { price_usd_minor: 2799, price_minor: 2799, started_at: at(24 * 5) }),
  row("lumenhaus.co", { price_usd_minor: 3285, price_minor: 4500, currency: "CAD", started_at: at(24 * 20) }),
  row("trendyglow.com", { tracked: true, price_usd_minor: 2400, price_minor: 2400, price_max_minor: 3499, started_at: at(24 * 34) }),
  row("cozycorner.shop", { price_usd_minor: 2999, price_minor: 2999, listed: "unknown", unknown_reason: "last_crawl_incomplete", last_seen: at(52), stale: true, started_at: at(24 * 38) }),
  row("moodlight.eu", { price_usd_minor: null, price_minor: 2900, currency: "EUR", fx_missing: true, started_at: at(24 * 41) }),
  row("auroralamps.store", { price_usd_minor: 2650, price_minor: 2650, untrackable: true, listed: "unknown", unknown_reason: "store_untrackable", started_at: at(24 * 44) }),
  row("glowupgoods.com", { price_usd_minor: 3999, price_minor: 3999, started_basis: "first_seen", started_at: at(24 * 52) }),
  row("bright-nest.com", { price_usd_minor: 2199, price_minor: 2199, listed: "delisted", delisted_at: at(24 * 4 + 2), started_at: at(24 * 30) }),
  row("homeglow.co", { price_usd_minor: 2599, price_minor: 2599, listed: "delisted", delisted_at: at(24 * 12 + 2), started_at: at(24 * 47) }),
];

const points = [2400, 2799, 2999, 3285, 3999].map((price) => ({ domain: ROWS.find((r) => r.price_usd_minor === price)!.domain, price_usd_minor: price, as_of: at(6) }));
// Observed since the crawler started 40 days ago, with two gap days (the PC was off), never interpolated.
const series: S["SeriesDay"][] = Array.from({ length: 90 }, (_, i) => {
  const ago = 89 - i;
  const gap = ago > 40 || ago === 9 || ago === 10;
  const date = new Date(NOW.getTime() - ago * 86_400_000).toISOString().slice(0, 10);
  return { date, active: gap ? null : Math.min(7, 3 + Math.floor((40 - ago) / 8)), gap, as_of: gap ? null : `${date}T06:10:00Z` };
});

export const sellers: S["SellersPage"] = {
  rows: ROWS,
  next_cursor: null,
  spread: { min: 2400, p25: 2799, median: 2999, mean: 3096, p75: 3285, max: 3999, n: 5, missing: 1, untrackable: 1, points, as_of: at(6) },
  band: { low: null, high: null, reason: "needs_landed_cost" },
  counts: { active: 7, delisted_30d: 2, new_14d: 1, as_of: at(3) },
  series_90d: series,
  crawler: { status: "enabled", since: null, reason: null },
  as_of: at(3),
};

/** The crawler stopped itself after repeated 429s 30 hours ago. */
export const paused: S["SellersPage"] = { ...sellers, crawler: { status: "auto_disabled", since: at(30), reason: "consecutive_blocks:http_429" } };

/** No tracked store lists the product. */
export const empty: S["SellersPage"] = {
  ...sellers,
  rows: [],
  spread: { min: null, p25: null, median: null, mean: null, p75: null, max: null, n: 0, missing: 0, untrackable: 0, points: [], as_of: null },
  counts: { active: 0, delisted_30d: 0, new_14d: 0, as_of: null },
  series_90d: series.map((d) => ({ ...d, active: d.gap ? null : 0 })),
  as_of: null,
};

/** The product shell's calls, plus the sellers endpoint answering `body` filtered like the API (or `status` with a
 *  problem; `hold` never answers). Returns the sellers requests' URLs. */
export async function mockSellersApi(page: Page, options: { body?: S["SellersPage"]; status?: number; hold?: boolean } = {}) {
  // The header agrees with the tab: 7 stores, $24.00 the lowest live price.
  await mockProductApi(page, { body: { ...product, store_count: { ...(product.store_count as S["Sourced"]), value: 7 } } });
  const calls: string[] = [];
  // Registered after the product route, so it answers first.
  await page.route("**/api/v1/products/*/sellers**", async (route) => {
    const url = new URL(route.request().url());
    calls.push(url.search);
    if (options.hold) return;
    if (options.status) return route.fulfill({ status: options.status, contentType: "application/problem+json", json: problem(options.status, `e2e-sellers-${options.status}`) });
    const body = options.body ?? sellers;
    const q = url.searchParams;
    const rows = body.rows.filter(
      (r) =>
        (q.get("include_delisted") === "true" || r.listed !== "delisted") &&
        (q.get("new_14d") !== "true" || r.domain === "nightsky-decor.com") &&
        (q.get("tracked") !== "true" || r.tracked),
    );
    return route.fulfill({ json: { ...body, rows } });
  });
  return calls;
}
