import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { healthySources, mockAdminApi, problem } from "../data-health/fixtures";
import { PRODUCT_ID } from "../products/fixtures";

// Synthetic GET /v1/amazon/ranks pages (AMZ-1b): invented ASINs and titles, never a real export row. Dates sit around
// Data Health's NOW (2026-10-22), which mockAdminApi pins with page.clock.

type S = components["schemas"];
export const LATEST = "2026-10-21";
const CAPTURED = "2026-10-21T19:40:00Z";
/** Category, rank kind, rows: two categories each with a rank 1, and one category in both lists. */
export const LISTS = [
  ["Home & Kitchen", "bsr", 30],
  ["Home & Kitchen", "movers", 8],
  ["Toys & Games", "bsr", 12],
] as const;
const TITLES = [
  "Example LED desk lamp with dimmer",
  "Example silicone spatula set, 5 pieces",
  "Example magnetic knife strip",
  "Example glass meal-prep containers",
  "Example cordless milk frother",
  "Example bamboo drawer organiser",
  "Example stacking building blocks",
  "Example wooden puzzle board",
];

/** Rank `rank` of a list: every third row links to a product; some rows lack a price, rating or review count. */
export function amazonRow(category: string, rank_kind: "bsr" | "movers", rank: number, as_of = LATEST): S["AmazonRankRow"] {
  const seed = rank * 31 + category.length + (rank_kind === "movers" ? 7 : 0);
  return {
    asin: `B0EX${String(seed).padStart(6, "0")}`,
    title: `${TITLES[seed % TITLES.length]}${rank > TITLES.length ? ` (${Math.ceil(rank / TITLES.length)})` : ""}`,
    category,
    rank_kind,
    rank,
    price_minor: rank % 5 === 4 ? null : 999 + ((seed * 431) % 4000),
    currency: "USD",
    rating: rank % 6 === 5 ? null : 3.6 + ((seed * 7) % 14) / 10,
    review_count: rank % 7 === 6 ? null : 40 + ((seed * 977) % 25_000),
    product_id: rank % 3 === 1 ? PRODUCT_ID : null,
    as_of,
    captured_at: CAPTURED,
    raw_payload_id: 8001,
  };
}

export interface AmazonOptions {
  /** The newest import is from Oct 5, 17 days before NOW. */
  stale?: boolean;
  /** The source exists, nothing imported. */
  empty?: boolean;
  /** No amazon source row: no source yet. */
  noSource?: boolean;
  /** Answer with this error status. */
  status?: number;
  /** Never answer: the first-load skeleton stays. */
  hold?: boolean;
  pageSize?: number;
}

/** The shell's admin calls and GET /v1/amazon/ranks filtered as the API does, in pages of `pageSize` (cursor = offset).
 * Returns the requested URLs. */
export async function mockAmazonApi(page: Page, options: AmazonOptions = {}) {
  const { pageSize = 200 } = options;
  const calls: URL[] = [];
  await mockAdminApi(page, { sources: healthySources });
  await page.route(
    (url) => url.pathname === "/api/v1/amazon/ranks",
    async (route) => {
      const url = new URL(route.request().url());
      calls.push(url);
      if (options.hold) return;
      if (options.status)
        return route.fulfill({ status: options.status, contentType: "application/problem+json", json: problem(options.status, "e2e-amazon-503") });
      const as_of = options.stale ? "2026-10-05" : LATEST;
      const lists = options.empty || options.noSource ? [] : LISTS;
      const [category, kind] = [url.searchParams.get("category"), url.searchParams.get("rank_kind")];
      const shown = lists.filter(([c, k]) => (category ?? c) === c && (kind ?? k) === k);
      const rows = shown.flatMap(([c, k, n]) => Array.from({ length: n }, (_, i) => amazonRow(c, k, i + 1, as_of)));
      const offset = Number(url.searchParams.get("cursor") ?? 0);
      const end = offset + pageSize;
      const body: S["AmazonRankPage"] = {
        source: options.noSource ? null : "amazon",
        source_name: options.noSource ? null : "Amazon",
        lists: lists.map(([c, k, n]) => ({ category: c, rank_kind: k, as_of, captured_at: CAPTURED, rows: n, stale: options.stale === true })),
        rows: rows.slice(offset, end),
        next_cursor: end < rows.length ? String(end) : null,
        total: rows.length,
        as_of: rows.length ? as_of : null,
        captured_at: rows.length ? CAPTURED : null,
        stale: options.stale === true && rows.length > 0,
      };
      return route.fulfill({ json: body });
    },
  );
  return calls;
}
