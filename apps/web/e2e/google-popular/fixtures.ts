import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { healthySources, mockAdminApi, problem } from "../data-health/fixtures";
import { PRODUCT_ID } from "../products/fixtures";

// Synthetic GET /v1/popular-products pages (P2-29 b) and the workspace brand list (DEC-277). The repo is public and Google's rows are internal use only, so
// no real export row: invented titles and brands. Dates sit around Data Health's NOW (2026-10-22), which
// mockAdminApi pins with page.clock.

type S = components["schemas"];
export const LATEST = "2026-10-19";
const PREVIOUS = "2026-10-12";
export const CATEGORIES = ["Apparel & Accessories", "Home & Garden > Lighting"];
const TITLES = [
  "Sunset projection lamp with 16 colour modes",
  "Magnetic car vent phone mount",
  "Silicone pet grooming glove",
  "Portable neck fan with 3 speeds",
  "Collapsible silicone water bottle",
  "LED strip lights, 5 m, app control",
  "Posture corrector for back and shoulders",
  "Electric milk frother, handheld",
  "Reusable lint roller for pet hair",
  "Mini thermal label printer",
];
const BRANDS = ["Lumeva", "Kestrelle", "Ordwell", null, "Pinegrove", "Halvy", "Tessaro", "Brindle & Oak"];
const AVAILABILITY = ["In stock", "Product suggestion", "Out of stock", "Brand suggestion"];

function change(rank: number, previous: boolean): S["RankChange"] {
  if (!previous) return { value: null, basis: "no_previous_week", previous_rank: null, as_of: null };
  if (rank % 5 === 3) return { value: null, basis: "new", previous_rank: null, as_of: PREVIOUS };
  const value = [3, 3, 7, -2, 0, -1][rank % 6]; // never above rank 1 last week
  return { value, basis: rank === 2 ? "previous_rank" : "previous_week", previous_rank: rank + value, as_of: PREVIOUS };
}

/** Rank `rank` of a report: every fourth row is the major brand Vantoro (10 of 40), every third row links to a product. */
export function popularRow(rank: number, previous = true): S["PopularRow"] {
  const major = rank % 4 === 0;
  const low = rank % 7 === 6 ? null : 900 + ((rank * 731) % 4000);
  return {
    rank,
    change: change(rank, previous),
    title: `${TITLES[rank % TITLES.length]}${rank > TITLES.length ? ` (${Math.ceil(rank / TITLES.length)})` : ""}`,
    brand: major ? "Vantoro" : BRANDS[rank % BRANDS.length],
    major_brand: major,
    hidden_by: major ? "major" : null,
    availability: AVAILABILITY[rank % 3 === 0 ? 1 : rank % 11 === 0 ? 2 : rank % 13 === 0 ? 3 : 0],
    price_min_minor: low,
    price_max_minor: low === null ? null : rank % 2 ? low + 1500 : low,
    currency: low === null ? null : "USD",
    gtins: [],
    product_id: rank % 3 === 1 ? PRODUCT_ID : null,
    as_of: LATEST,
    raw_payload_id: 7001,
  };
}

export interface PopularOptions {
  rows?: number;
  /** No earlier week imported: every change is "no source yet". */
  noPrevious?: boolean;
  /** The newest import is for the week of Oct 5, 17 days before NOW. */
  stale?: boolean;
  /** Nothing imported yet. */
  empty?: boolean;
  /** Answer with this error status. */
  status?: number;
  /** Never answer: the first-load skeleton stays. */
  hold?: boolean;
  pageSize?: number;
  /** The workspace's brand rules by lower-case brand; the mock reads and writes it, so a test can check it. */
  rules?: Map<string, S["BrandRule"]>;
  /** Answer every brand rule change with this error status. */
  writeStatus?: number;
}

/** A brand rule as the API returns it. */
export const brandRule = (brand: string, action: "hide" | "show"): S["BrandRule"] => ({ brand, action, created_at: "2026-10-22T09:00:00Z" });

/** The shell's admin calls, GET /v1/popular-products in pages of `pageSize` (cursor = offset) with the brand rules
 * applied as the API does, and brand rule PUT and DELETE. Returns the popular-products URLs. */
export async function mockPopularApi(page: Page, options: PopularOptions = {}) {
  const { rows = 40, pageSize = 200, rules = new Map<string, S["BrandRule"]>() } = options;
  const calls: URL[] = [];
  await page.route(
    (url) => url.pathname === "/api/v1/popular-products/brands",
    async (route) => {
      const request = route.request();
      if (options.writeStatus && request.method() !== "GET")
        return route.fulfill({ status: options.writeStatus, contentType: "application/problem+json", json: problem(options.writeStatus, "e2e-brands-write") });
      if (request.method() === "PUT") {
        const { brand, action } = request.postDataJSON() as S["BrandRuleIn"];
        rules.set(brand.toLowerCase(), brandRule(brand, action));
        return route.fulfill({ json: rules.get(brand.toLowerCase()) });
      }
      const brand = (new URL(request.url()).searchParams.get("brand") ?? "").toLowerCase();
      const removed = rules.get(brand) ?? null;
      rules.delete(brand);
      return route.fulfill({ json: removed });
    },
  );
  await mockAdminApi(page, { sources: healthySources });
  await page.route(
    (url) => url.pathname === "/api/v1/popular-products",
    async (route) => {
      const url = new URL(route.request().url());
      calls.push(url);
      if (options.hold) return;
      if (options.status)
        return route.fulfill({ status: options.status, contentType: "application/problem+json", json: problem(options.status, "e2e-popular-503") });
      const weeks = options.empty ? [] : options.stale ? ["2026-10-05", "2026-09-28"] : [LATEST, PREVIOUS];
      const all = url.searchParams.get("include_major_brands") === "true";
      const report = (options.empty ? [] : Array.from({ length: rows }, (_, i) => popularRow(i + 1, !options.noPrevious))).map((r) => {
        const rule = rules.get(r.brand?.toLowerCase() ?? "")?.action;
        return { ...r, hidden_by: rule === "hide" ? ("you" as const) : r.major_brand && rule !== "show" ? ("major" as const) : null };
      });
      const shown = all ? report : report.filter((r) => !r.hidden_by);
      const offset = Number(url.searchParams.get("cursor") ?? 0);
      const end = offset + pageSize;
      const body: S["PopularPage"] = {
        country: "US",
        category: url.searchParams.get("category") ?? (options.empty ? null : CATEGORIES[0]),
        categories: options.empty ? [] : CATEGORIES,
        weeks,
        rows: shown.slice(offset, end).map((r) => ({ ...r, as_of: weeks[0] })),
        next_cursor: end < shown.length ? String(end) : null,
        total: report.length,
        hidden: report.length - shown.length,
        hidden_by_you: all ? 0 : report.filter((r) => r.hidden_by === "you").length,
        major_brand_rows: 10,
        previous_week: options.noPrevious || options.empty ? null : PREVIOUS,
        source: "merchant_bestsellers",
        source_name: "Google Merchant Center Popular products",
        captured_at: options.empty ? null : "2026-10-21T08:12:00Z",
        as_of: weeks[0] ?? null,
        stale: options.stale === true,
      };
      return route.fulfill({ json: body });
    },
  );
  return calls;
}
