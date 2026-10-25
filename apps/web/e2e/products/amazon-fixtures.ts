import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { problem } from "../data-health/fixtures";
import { PRODUCT_ID } from "./fixtures";

// p3-07 (AMZ-1c): synthetic GET /v1/products/{id}/amazon-ranks answers, invented ASINs and titles, never a real
// export row. Days sit around Data Health's NOW (2026-10-22), which mockAdminApi pins with page.clock.

type S = components["schemas"];
type Ranks = S["ProductAmazonRanks"];

const row = (category: string, rank_kind: "bsr" | "movers", rank: number, as_of: string, captured_at: string, asin: string): S["AmazonRankRow"] => ({
  asin,
  title: "Example LED desk lamp with dimmer",
  category,
  rank_kind,
  rank,
  price_minor: 2499,
  currency: "USD",
  rating: 4.5,
  review_count: 1532,
  product_id: PRODUCT_ID,
  as_of,
  captured_at,
  raw_payload_id: 8001,
});

const base = { source: "amazon", source_name: "Amazon", imported: true, rows: [], as_of: null, captured_at: null, stale: false } satisfies Ranks;

/** Ranked in three lists; Office Products' newest ranked day is earlier. */
export const ranked: Ranks = {
  ...base,
  rows: [
    row("Home & Kitchen", "bsr", 12, "2026-10-21", "2026-10-21T19:40:00Z", "B0EX000412"),
    row("Home & Kitchen", "movers", 3, "2026-10-21", "2026-10-21T19:40:00Z", "B0EX000412"),
    row("Office Products", "bsr", 1048, "2026-10-18", "2026-10-18T08:05:00Z", "B0EX000977"),
  ],
  as_of: "2026-10-21",
  captured_at: "2026-10-21T19:40:00Z",
};
/** The newest ranked day is Oct 5, 17 days before NOW. */
export const staleRanks: Ranks = {
  ...base,
  rows: [row("Home & Kitchen", "bsr", 27, "2026-10-05", "2026-10-05T18:12:00Z", "B0EX000412")],
  as_of: "2026-10-05",
  captured_at: "2026-10-05T18:12:00Z",
  stale: true,
};
/** Lists are imported; none shares a barcode with this product. */
export const notRanked: Ranks = base;
export const noImport: Ranks = { ...base, imported: false };
export const noSource: Ranks = { ...base, source: null, source_name: null, imported: false };

export interface AmazonRanksMock {
  body?: Ranks;
  /** Answer every request with this error status. */
  status?: number;
  /** Never answer: the skeleton stays. */
  hold?: boolean;
}

/** Overrides mockProductApi's default (not ranked). Returns how many times it was asked. */
export async function mockProductAmazonApi(page: Page, options: AmazonRanksMock = {}) {
  const calls = { n: 0 };
  await page.route("**/api/v1/products/*/amazon-ranks", async (route) => {
    calls.n++;
    if (options.hold) return;
    if (options.status)
      return route.fulfill({ status: options.status, contentType: "application/problem+json", json: problem(options.status, "e2e-product-amazon-503") });
    return route.fulfill({ json: options.body ?? ranked });
  });
  return calls;
}
