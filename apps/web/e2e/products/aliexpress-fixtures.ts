import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { NOW, problem } from "../data-health/fixtures";
import { mockSuppliersApi } from "./suppliers-fixtures";

// p3-05 (AE-3): fixture GET/POST /v1/products/{id}/aliexpress answers, never a database restore or an AliExpress call.
// The numbers mirror packages/sources/tests/aliexpress/fixtures (product.json, freight.json).

type Lookup = components["schemas"]["AliExpressLookup"];
const at = (hoursAgo: number) => new Date(NOW.getTime() - hoursAgo * 3_600_000).toISOString();
const gone = (iso: string) => new Date(Date.parse(iso) + 86_400_000).toISOString();

export const LIVE = "AliExpress · live · not stored";
export const LINK = "https://www.aliexpress.com/item/1005000000000001.html?skuId=12000000000000001";
export const empty: Lookup = { status: "empty" };
export const found: Lookup = {
  status: "ok",
  as_of: at(2),
  expires_at: gone(at(2)),
  retry_at: null,
  product: {
    product_id: "1005000000000001",
    title: "Fixture Sunset Projection Lamp",
    rating: "4.7",
    review_count: 128,
    sales: "1000+",
    store_name: "Fixture Store",
    skus: [
      { sku_id: "12000000000000001", price_minor: 549, sale_price_minor: 399, currency: "USD", stock: 57 },
      { sku_id: "12000000000000002", price_minor: 549, sale_price_minor: 425, currency: "USD", stock: null },
    ],
  },
  shipping: [
    { code: "FIXTURE_STANDARD", company: "Fixture Standard", fee_minor: 499, currency: "USD", free: false, min_days: 9, max_days: 15, ship_from: "CN" },
    { code: "FIXTURE_ECONOMY", company: "Fixture Economy", fee_minor: 0, currency: "USD", free: true, min_days: 20, max_days: 35, ship_from: "CN" },
  ],
};
export const paused: Lookup = { status: "throttled", retry_at: new Date(NOW.getTime() + 5 * 60_000).toISOString() };

/** Each GET takes the next answer (the last repeats): a Lookup, an HTTP error status, or "hold" (never answers). */
export async function mockAliExpressApi(page: Page, gets: (Lookup | number | "hold")[], post: Lookup | number = found) {
  await mockSuppliersApi(page);
  const posted: unknown[] = [];
  let n = 0;
  // Registered after the product routes, so it answers first.
  await page.route("**/api/v1/products/*/aliexpress", async (route) => {
    if (route.request().method() === "POST") {
      posted.push(route.request().postDataJSON());
      if (typeof post === "number")
        return route.fulfill({ status: post, contentType: "application/problem+json", json: { ...problem(post, `e2e-aliexpress-${post}`), code: post === 422 ? "invalid_link" : "unavailable" } });
      return route.fulfill({ json: post });
    }
    const answer = gets[Math.min(n++, gets.length - 1)];
    if (answer === "hold") return;
    if (typeof answer === "number") return route.fulfill({ status: answer, contentType: "application/problem+json", json: problem(answer, `e2e-aliexpress-${answer}`) });
    return route.fulfill({ json: answer });
  });
  return posted;
}
