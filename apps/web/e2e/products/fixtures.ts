import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { healthySources, mockAdminApi, NOW, problem } from "../data-health/fixtures";

// Fixture GET /v1/products/{id} responses for the product page e2e tests and screenshots, never a database restore.
// Times are relative to Data Health's NOW, which mockAdminApi pins with page.clock (the shell's badge reads it too).

type S = components["schemas"];
const at = (hoursAgo: number) => new Date(NOW.getTime() - hoursAgo * 3_600_000).toISOString();

export const PRODUCT_ID = "3f6c1e52-8a7d-4b0e-9c21-5d4e8f7a6b13";
export const TAB_LABELS = { overview: "Overview", trends: "Trends", suppliers: "Suppliers", sellers: "Sellers", profit: "Profit" };

const shopify = (value: number, hoursAgo: number, raw_payload_id: number): S["Sourced"] => ({
  value, source: "shopify_stores", source_name: "Shopify stores", as_of: at(hoursAgo), raw_payload_id, method: null, stale: false,
});

export const product: S["ProductHeader"] = {
  id: PRODUCT_ID,
  title: "Sunset projection lamp with 16 colour modes and remote",
  image_url: "https://cdn.example.test/sunset-lamp.svg",
  category: "Home & Garden > Lighting > Lamps",
  first_seen_at: at(24 * 9 + 5),
  currency: "USD",
  store_count: shopify(12, 6, 902114),
  supplier_count: { value: 3, source: "cj", source_name: "CJ Dropshipping", as_of: at(9), raw_payload_id: 901877, method: null, stale: false },
  price_min_minor: shopify(2400, 6, 902051),
  price_max_minor: shopify(3999, 7, 901994),
};

const none = (reason: string): S["NoSource"] => ({ value: null, reason });
/** Matched, but nothing collected for it yet: every stat is null with its reason. */
export const unmatched: S["ProductHeader"] = {
  ...product,
  image_url: null,
  category: null,
  store_count: none("No store listing is matched to this product yet."),
  supplier_count: none("No supplier listing is matched to this product yet."),
  price_min_minor: none("No USD retail price observed for this product yet."),
  price_max_minor: none("No USD retail price observed for this product yet."),
};

/** The store crawler last captured 3 days ago, past twice its daily interval. */
export const stale: S["ProductHeader"] = {
  ...product,
  ...Object.fromEntries(
    (["store_count", "price_min_minor", "price_max_minor"] as const).map((k) => [k, { ...(product[k] as S["Sourced"]), as_of: at(74), stale: true }]),
  ),
};

// A product photo stand-in, served for the fixture image URL so no request leaves the test.
const LAMP = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 72 72"><defs><radialGradient id="g" cx=".5" cy=".42" r=".6"><stop offset="0" stop-color="#ffd27a"/><stop offset=".55" stop-color="#f0743e"/><stop offset="1" stop-color="#3a1f4d"/></radialGradient></defs><rect width="72" height="72" fill="url(#g)"/><circle cx="36" cy="30" r="13" fill="#fff3c9" opacity=".85"/><rect x="31" y="46" width="10" height="14" rx="2" fill="#1d1426"/></svg>`;

/** The shell's admin calls, plus GET /v1/products/{id} answering `body` (or `status` with a problem; `hold` never
 *  answers). Returns the product requests' URLs. */
export async function mockProductApi(page: Page, options: { body?: S["ProductHeader"]; status?: number; hold?: boolean } = {}) {
  const calls: string[] = [];
  await mockAdminApi(page, { sources: healthySources });
  await page.route("https://cdn.example.test/**", (route) => route.fulfill({ contentType: "image/svg+xml", body: LAMP }));
  await page.route("**/api/v1/products/**", async (route) => {
    calls.push(route.request().url());
    if (options.hold) return; // never answers: the first-load skeleton stays
    if (options.status) return route.fulfill({ status: options.status, contentType: "application/problem+json", json: problem(options.status, `e2e-product-${options.status}`) });
    return route.fulfill({ json: options.body ?? product });
  });
  return calls;
}
