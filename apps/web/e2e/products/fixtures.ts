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
  store_count: none("No store listing matched yet."),
  supplier_count: none("No supplier listing matched yet."),
  price_min_minor: none("No USD retail price observed yet."),
  price_max_minor: none("No USD retail price observed yet."),
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

// p2-03 (UX-2): fixture GET /v1/products feed pages and GET /v1/categories, for the Discover e2e tests and screenshots.

const NAMES = [
  "Sunset projection lamp", "Magnetic car phone mount", "Posture corrector brace", "Portable USB blender", "Cloud pillow slides",
  "Mini waffle maker", "Smart LED strip lights", "Pet hair remover roller", "Facial ice roller", "Electric scalp massager",
  "Car seat gap filler", "Silicone stretch lids", "Galaxy star projector", "Self-stirring mug", "Foldable laptop stand",
  "Cordless wax melter", "Heated eye mask", "Wireless charging pad", "Reusable lint roller", "Ergonomic seat cushion",
];
const CATEGORIES: S["CategoryOption"][] = [
  { id: 7, path: "Home & Garden > Lighting > Lamps" },
  { id: 12, path: "Health & Beauty > Personal Care" },
  { id: 31, path: "Vehicles & Parts > Vehicle Accessories" },
];

/** Product `i` of a feed: a mix of sourced numbers, gaps, stale data and stats nothing backs yet. */
export function discoverItem(i: number): S["DiscoverItem"] {
  const id = `00000000-0000-4000-8000-${String(i).padStart(12, "0")}`;
  const staleShop = i % 9 === 8;
  const shop = (value: number, raw: number): S["Sourced"] => ({
    value, source: "shopify_stores", source_name: "Shopify stores", as_of: at(staleShop ? 74 : 6 + (i % 4)), raw_payload_id: raw, method: null, stale: staleShop,
  });
  const noStores = i % 6 === 5;
  const low = 1200 + ((i * 731) % 4800);
  const velocity: S["DiscoverItem"]["velocity"] =
    i % 5 === 4
      ? none("No demand family has a 7-day growth yet.")
      : {
          value: 80 - ((i * 7) % 70), source: "shopify_stores", source_name: "Shopify stores", as_of: at(14), raw_payload_id: null,
          method: "Shopify updated_at bumps, a lower bound", stale: false, family: "shp_bump", grade: "B",
          growth: 1.2 - i * 0.07, gap: i % 7 === 3,
        };
  return {
    id,
    title: `${NAMES[i % NAMES.length]}${i >= NAMES.length ? ` ${Math.floor(i / NAMES.length) + 1}` : ""}`,
    image_url: `https://cdn.example.test/p/${i}.svg`,
    category: i % 8 === 6 ? null : CATEGORIES[i % CATEGORIES.length].path,
    first_seen_at: at(24 * (1 + ((i * 5) % 80))),
    currency: "USD",
    store_count: noStores ? none("No store listing matched yet.") : shop(1 + ((i * 3) % 14), 903000 + i),
    supplier_count: { value: 1 + (i % 4), source: "cj", source_name: "CJ Dropshipping", as_of: at(9), raw_payload_id: 904000 + i, method: null, stale: false },
    price_min_minor: noStores ? none("No USD retail price observed yet.") : shop(low, 905000 + i),
    price_max_minor: noStores ? none("No USD retail price observed yet.") : shop(low + 1500 + (i % 3) * 1000, 906000 + i),
    velocity,
    best_margin_minor: none("The landed-cost engine arrives with UX-8."),
    as_of: noStores ? at(9) : at(staleShop ? 74 : 9),
    stale: staleShop && !noStores,
  };
}

/** Momentum order, as the API serves it: insufficient signal sinks to the end. */
export const feedItems = (n: number) =>
  Array.from({ length: n }, (_, i) => discoverItem(i)).sort((a, b) => growth(b) - growth(a));
const growth = (item: S["DiscoverItem"]) => ("growth" in item.velocity ? item.velocity.growth : -Infinity);
export const FEED_PATH = (url: URL) => url.pathname === "/api/v1/products";

export interface FeedOptions {
  items?: S["DiscoverItem"][];
  pageSize?: number;
  degraded?: S["Degraded"][];
  /** Answer the first page with this error status. */
  status?: number;
  /** Answer every later page with a 503. */
  failMore?: boolean;
  /** Never answer: the first-load skeleton stays. */
  hold?: boolean;
}

/** The shell's admin calls, GET /v1/categories and GET /v1/products in pages of `pageSize` (cursor = offset). Returns
 *  the feed requests' URLs. Product photo stand-ins are SVGs in a hue per product, so no request leaves the test. */
export async function mockFeedApi(page: Page, options: FeedOptions = {}) {
  const { items = feedItems(20), pageSize = 48, degraded = [] } = options;
  const calls: URL[] = [];
  await mockAdminApi(page, { sources: healthySources });
  await page.route("https://cdn.example.test/p/**", (route) => {
    const hue = (Number(route.request().url().match(/(\d+)\.svg$/)?.[1] ?? 0) * 47) % 360;
    const body = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 72 72"><defs><linearGradient id="g" x2="1" y2="1"><stop offset="0" stop-color="hsl(${hue} 60% 72%)"/><stop offset="1" stop-color="hsl(${(hue + 40) % 360} 45% 34%)"/></linearGradient></defs><rect width="72" height="72" fill="url(#g)"/><rect x="22" y="20" width="28" height="34" rx="6" fill="hsl(${hue} 30% 96%)" opacity=".85"/><circle cx="36" cy="33" r="7" fill="hsl(${hue} 55% 45%)"/></svg>`;
    return route.fulfill({ contentType: "image/svg+xml", body });
  });
  await page.route("**/api/v1/categories", (route) => route.fulfill({ json: CATEGORIES }));
  await page.route(FEED_PATH, async (route) => {
    const url = new URL(route.request().url());
    calls.push(url);
    if (options.hold) return;
    const offset = Number(url.searchParams.get("cursor") ?? 0);
    const status = offset ? (options.failMore ? 503 : 0) : options.status;
    if (status) return route.fulfill({ status, contentType: "application/problem+json", json: problem(status, `e2e-feed-${status}`) });
    const end = offset + pageSize;
    const body: S["DiscoverPage"] = { items: items.slice(offset, end), next_cursor: end < items.length ? String(end) : null, as_of: at(6), degraded };
    return route.fulfill({ json: body });
  });
  return calls;
}
