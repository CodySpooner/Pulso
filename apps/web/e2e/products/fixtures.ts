import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { healthySources, mockAdminApi, NOW, problem } from "../data-health/fixtures";
import { decided } from "./keywords-fixtures";
import { trendsSeries } from "./trends-fixtures";

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

// p2-07 (UX-4): the Overview tab and the context rail.
const cj = (value: number, raw_payload_id: number): S["Sourced"] => ({
  value, source: "cj", source_name: "CJ Dropshipping", as_of: at(9), raw_payload_id, method: null, stale: false,
});

export const overview: S["ProductOverview"] = {
  currency: "USD",
  price_min_minor: product.price_min_minor,
  price_median_minor: shopify(2999, 6, 902077),
  price_max_minor: product.price_max_minor,
  best_supplier_cost_minor: { ...cj(812, 901877), platform: "cj" },
  // imp-280: Discover's best margin, as of its oldest input (the CJ cost).
  landed_margin_minor: {
    ...cj(1188, 901903), method: "Landed cost, default scenario: price - landed cost - fees - returns, before ads", margin_bps: 3961, supplier_listing_id: 907001,
  },
  first_seen_at: product.first_seen_at,
  age_days: { ...shopify(9, 24 * 9 + 5, 880412) },
  velocity: {
    ...shopify(34, 14, 0), raw_payload_id: null, method: "Shopify inventory drops", family: "shp_inv", grade: "A", growth: 0.47, gap: false,
  },
  appearances: [
    { vendor: "supplier", count: cj(3, 901877) },
    { vendor: "store", count: shopify(12, 6, 902114) },
  ],
  ad_count: none("No ad source is connected yet."),
};

/** R-16: a withheld margin, with the gaps the view names (imp-280). */
const gap = (reason: string, ...missing: string[]) => ({ value: null, reason, missing });

/** Matched, nothing collected: every Overview number is null with its reason. */
export const overviewUnmatched: S["ProductOverview"] = {
  ...overview,
  price_min_minor: none("No USD retail price observed yet."),
  price_median_minor: none("No USD retail price observed yet."),
  price_max_minor: none("No USD retail price observed yet."),
  best_supplier_cost_minor: none("No in-stock supplier offer yet."),
  landed_margin_minor: gap("Needs a market price, a supplier price and a freight quote.", "price_missing", "supplier_cost_missing", "freight_missing"),
  age_days: none("No listing observation yet."),
  velocity: none("No demand family has a 7-day growth yet."),
  appearances: [],
};

/** Costed, but the workspace has no duty rate: R-16 withholds the margin (imp-280). */
export const overviewNoDuty: S["ProductOverview"] = { ...overview, landed_margin_minor: gap("Needs a duty rate.", "duty_not_set") };

/** The store crawler last captured 3 days ago: the retail stats are stale. */
export const overviewStale: S["ProductOverview"] = {
  ...overview,
  ...Object.fromEntries(
    (["price_min_minor", "price_median_minor", "price_max_minor"] as const).map((k) => [k, { ...(overview[k] as S["Sourced"]), as_of: at(74), stale: true }]),
  ),
};

export const notes: S["Note"][] = [
  { id: "7c1f0a52-0000-4000-8000-000000000002", body: "Glow films well: a TikTok angle. Test at $29.99 against the $24 floor.", created_at: at(20) },
  { id: "7c1f0a52-0000-4000-8000-000000000001", body: "CJ ships from CN only.\nAsk for a US warehouse quote before a test.", created_at: at(50) },
];
export const manyNotes = (n: number): S["Note"][] =>
  Array.from({ length: n }, (_, i) => ({ id: `7c1f0a52-0000-4000-8000-${String(1000 + i).padStart(12, "0")}`, body: `Note ${n - i}`, created_at: at(i + 1) }));

export interface ProductMock {
  /** GET /v1/products/{id}; `status` answers it with a problem (`code`, default "unavailable"), and `hold` never answers. */
  body?: S["ProductHeader"];
  status?: number;
  code?: string;
  hold?: boolean;
  overview?: S["ProductOverview"];
  overviewStatus?: number;
  holdOverview?: boolean;
  notes?: S["Note"][];
  tags?: string[];
  /** Answer the rail's GETs with a 503, or never answer them. */
  railStatus?: number;
  holdRail?: boolean;
  /** Answer every note POST and tags PUT with a 503, or never answer them. */
  failSaves?: boolean;
  holdSaves?: boolean;
}

const fail = (status: number, id: string, code?: string) => ({
  status,
  contentType: "application/problem+json",
  json: { ...problem(status, id), ...(code && { code }) },
});

/** The shell's admin calls, plus the product's header, overview, notes and tags. Notes and tags keep what the page
 *  saves, like the API (notes newest first, 20 a page, cursor = offset). Returns the product requests' URLs. */
/** No supplier listing is matched yet (GET /v1/products/{id}/suppliers). */
export const noSuppliers: S["SuppliersPage"] = { country: "US", rows: [], next_cursor: null, picks: { best_margin: null, fastest: null }, as_of: null };

export async function mockProductApi(page: Page, options: ProductMock = {}) {
  const calls: string[] = [];
  const saved = { notes: [...(options.notes ?? notes)], tags: [...(options.tags ?? ["Q4 test", "TikTok"])] };
  await mockAdminApi(page, { sources: healthySources });
  await page.route("https://cdn.example.test/**", (route) => route.fulfill({ contentType: "image/svg+xml", body: LAMP }));
  await page.route("**/api/v1/products/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const part = url.pathname.split("/")[5]; // /api/v1/products/{id}/{part}
    calls.push(request.url());
    if (part === "overview") {
      if (options.holdOverview) return;
      if (options.overviewStatus) return route.fulfill(fail(options.overviewStatus, `e2e-overview-${options.overviewStatus}`));
      return route.fulfill({ json: options.overview ?? overview });
    }
    if (part === "notes" || part === "tags") {
      const write = request.method() !== "GET";
      if (write && options.holdSaves) return;
      if (write && options.failSaves) return route.fulfill(fail(503, `e2e-${part}-save`));
      if (!write && options.holdRail) return;
      if (!write && options.railStatus) return route.fulfill(fail(options.railStatus, `e2e-${part}-${options.railStatus}`));
      if (part === "tags") {
        if (write) saved.tags = [...(request.postDataJSON() as S["Tags"]).tags].sort((a, b) => a.localeCompare(b, "en", { sensitivity: "base" }));
        return route.fulfill({ json: { tags: saved.tags } });
      }
      if (write) {
        const note = { id: crypto.randomUUID(), body: (request.postDataJSON() as S["NoteIn"]).body.trim(), created_at: NOW.toISOString() };
        saved.notes.unshift(note);
        return route.fulfill({ status: 201, json: note });
      }
      const offset = Number(url.searchParams.get("cursor") ?? 0);
      const end = offset + Number(url.searchParams.get("limit") ?? 20);
      return route.fulfill({ json: { items: saved.notes.slice(offset, end), next_cursor: end < saved.notes.length ? String(end) : null } });
    }
    if (options.hold) return; // never answers: the first-load skeleton stays
    if (options.status) return route.fulfill(fail(options.status, `e2e-product-${options.status}`, options.code));
    if (part === "series") return route.fulfill({ json: trendsSeries }); // the Trends tab (p2-09)
    if (part === "keywords") return route.fulfill({ json: decided }); // its keywords (p3-02); that spec keeps POSTs
    if (part === "suppliers") return route.fulfill({ json: noSuppliers }); // the Suppliers tab (p2-26); its spec mocks rows
    if (part === "amazon-ranks") return route.fulfill({ json: { source: "amazon", source_name: "Amazon", imported: true, rows: [], as_of: null, captured_at: null, stale: false } }); // Trends, not ranked (p3-07)
    if (part === "aliexpress") return route.fulfill({ json: { status: "disabled" } }); // AE-3's honest default; its spec mocks the rest
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
    best_margin_minor: margin(i, noStores, low),
    as_of: noStores ? at(9) : at(staleShop ? 74 : 9),
    stale: staleShop && !noStores,
  };
}

/** Best margin of product `i` (DEC-265): no market price without stores, then duty not set, freight not quoted, or a
 *  complete margin. */
function margin(i: number, noStores: boolean, low: number): S["DiscoverItem"]["best_margin_minor"] {
  const gap = (reason: string, code: string) => ({ value: null, reason, missing: [code] });
  if (noStores) return gap("Needs a market price.", "price_missing");
  if (i % 4 === 1) return gap("Needs a duty rate.", "duty_not_set");
  if (i % 4 === 2) return gap("Needs a freight quote.", "freight_missing");
  const value = Math.round(low * 0.38);
  return {
    value, margin_bps: Math.round((value * 10000) / low), supplier_listing_id: 907000 + i, source: "cj", source_name: "CJ Dropshipping",
    as_of: at(9), raw_payload_id: 908000 + i, method: "Landed cost, default scenario: price - landed cost - fees - returns, before ads",
    stale: false,
  };
}

/** Momentum order, as the API serves it: insufficient signal sinks to the end. */
export const feedItems = (n: number) =>
  Array.from({ length: n }, (_, i) => discoverItem(i)).sort((a, b) => growth(b) - growth(a));
const growth = (item: S["DiscoverItem"]) => ("growth" in item.velocity ? item.velocity.growth : -Infinity);
export const FEED_PATH = (url: URL) => url.pathname === "/api/v1/products";
/** The stores and suppliers the feed names for its filter chips (imp-242): the palette's search fixtures' ids. */
export const FEED_VENDORS: Record<"store" | "supplier", Record<string, string>> = {
  store: { 4101: "glowbeam.example.test", 4102: "nightglow.example.test" },
  supplier: { 88: "Shenzhen Glowtech Co." },
};

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
    const vendor = (key: "store" | "supplier") => {
      const id = url.searchParams.get(key);
      return id && FEED_VENDORS[key][id] ? { id: Number(id), name: FEED_VENDORS[key][id] } : null;
    };
    const next_cursor = end < items.length ? String(end) : null;
    const body: S["DiscoverPage"] = { items: items.slice(offset, end), next_cursor, as_of: at(6), degraded, store: vendor("store"), supplier: vendor("supplier") };
    return route.fulfill({ json: body });
  });
  return calls;
}
