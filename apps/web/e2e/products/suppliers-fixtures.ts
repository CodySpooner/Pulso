import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { NOW, problem } from "../data-health/fixtures";
import { mockProductApi } from "./fixtures";
import { complete } from "./profit-fixtures";

// p2-26 (UX-6): fixture GET /v1/products/{id}/suppliers pages for the Suppliers tab e2e tests and screenshots, never
// a database restore. Each row's `cost` is what POST /v1/profit/calc answers for that supplier: the API test
// `test_each_row_costs_exactly_what_the_profit_tab_gets_for_that_supplier` pins that equality on Postgres.

type S = components["schemas"];
type Row = S["SupplierRow"];
type Calc = S["ProfitCalc"];
const at = (hoursAgo: number) => new Date(NOW.getTime() - hoursAgo * 3_600_000).toISOString();
const none = (reason: string) => ({ value: null, reason });
const cj = (value: number, hoursAgo = 9, raw: number | null = 901877) => ({
  value, source: "cj", source_name: "CJ Dropshipping", as_of: at(hoursAgo), raw_payload_id: raw, method: null, stale: false,
});

/** The worked example's fees at another supplier's unit cost, freight and days (2999 price, 20% duty, 2.9% + $0.30,
 *  5% returns, $15 CPA). */
function costed(id: number, unit: number, freight: number | null, method: string | null, days: [number, number] | null): Calc {
  const duty = Math.round(unit * 0.2);
  const sources = { ...complete.sources, unit_cost: { ...complete.sources.unit_cost, raw_payload_id: id * 10 } };
  if (freight === null) {
    const { freight: _, ...rest } = sources;
    return {
      ...complete, supplier_listing_id: id, goods_minor: unit, duty_minor: duty, freight_minor: null, method: null, freight_min_days: null,
      freight_max_days: null, landed_cost_minor: null, margin_minor: null, margin_bps: null, net_minor: null, net_bps: null,
      complete: false, missing: ["freight_missing"], sources: rest,
    };
  }
  const landed = unit + freight + duty;
  const margin = 2999 - landed - 117 - 150;
  return {
    ...complete, supplier_listing_id: id, goods_minor: unit, freight_minor: freight, duty_minor: duty, method, freight_min_days: days![0],
    freight_max_days: days![1], landed_cost_minor: landed, margin_minor: margin, margin_bps: Math.round((margin * 10_000) / 2999),
    net_minor: margin - 1500, net_bps: Math.round(((margin - 1500) * 10_000) / 2999),
    sources: { ...sources, freight: { ...complete.sources.freight, raw_payload_id: id * 10 + 1 } },
  };
}

function row(id: number, name: string, cost: Calc, over: Partial<Row> = {}): Row {
  return {
    listing_id: id, title: "Sunset projection lamp, 16 colours, USB", url: `https://cjdropshipping.com/product/sunset-lamp-p-${id}.html`,
    supplier_name: name, platform: "cj", supplier_url: null, supplier_country: "CN", warehouse_country: "CN",
    unit_cost_minor: cost.goods_minor, currency: "USD", cost, picks: [], in_stock: true,
    stock: none("The source reports no stock for this listing."), rating: none("The source gives no rating."),
    orders: none("The source gives no order count."), years_active: none("The source gives no years active."),
    moq: none("No offer terms captured for this listing yet."), bulk_tiers: [], source_name: "CJ Dropshipping",
    last_seen: at(3), stale: false, as_of: at(9), ...over,
  };
}

// Best margin first (complete rows), then the incomplete one; the out-of-stock row sorts by its margin but never picks.
const soldOut = row(88160, "Glowhub Trading", costed(88160, 500, 300, "YunExpress", [3, 5]), { in_stock: false, stock: cj(0) });
const best = row(88123, "CJ Dropshipping", complete, { picks: ["best_margin"] });
const dear = row(88131, "Yiwu Brightway", costed(88131, 700, 485, "CJPacket", [8, 12]), {
  orders: { ...cj(96), semantics: "window", window_days: 30 },
});
const fastest = row(88140, "Shenzhen Lamp Co.", costed(88140, 900, 300, "YunExpress", [3, 5]), {
  picks: ["fastest"], warehouse_country: "US", supplier_country: "CN", rating: { ...cj(470), count: 312 },
  orders: { ...cj(1840), semantics: "lifetime", window_days: null }, years_active: { ...cj(6), as_of: at(3), raw_payload_id: null },
  moq: { ...cj(2), as_of: at(3), raw_payload_id: null }, stock: cj(40),
  bulk_tiers: [{ min_quantity: 10, unit_minor: 590, currency: "USD", as_of: at(3) }, { min_quantity: 50, unit_minor: 540, currency: "USD", as_of: at(3) }],
});
const unquoted = row(88150, "Fuzhou Cheap Lights", costed(88150, 100, null, null, null));

export const SUPPLIERS: Row[] = [soldOut, best, dear, fastest, unquoted];
export const suppliers: S["SuppliersPage"] = { country: "US", rows: SUPPLIERS, next_cursor: null, picks: { best_margin: best, fastest }, as_of: at(3) };

const withoutPrice = (r: Row): Row => {
  const { price_minor: _, ...sources } = r.cost.sources;
  return {
    ...r, picks: r.picks.filter((p) => p !== "best_margin"),
    cost: {
      ...r.cost, price_minor: null, payment_fee_minor: null, shopify_fee_minor: null, returns_minor: null, margin_minor: null, margin_bps: null,
      net_minor: null, net_bps: null, complete: false, missing: ["price_missing", ...r.cost.missing], sources,
    },
  };
};
/** No market price (the store crawler is off for good, DEC-261): landed costs compare, no margin ranks. */
export const noPrice: S["SuppliersPage"] = {
  ...suppliers, rows: SUPPLIERS.map(withoutPrice), picks: { best_margin: null, fastest: withoutPrice(fastest) },
};

const staleRow = (r: Row): Row => ({
  ...r, stale: true, last_seen: at(74),
  cost: { ...r.cost, sources: { ...r.cost.sources, unit_cost: { ...r.cost.sources.unit_cost, as_of: at(74), stale: true } } },
});
/** CJ last answered 3 days ago, past twice its interval. */
export const stale: S["SuppliersPage"] = {
  ...suppliers, rows: SUPPLIERS.map(staleRow), picks: { best_margin: staleRow(best), fastest: staleRow(fastest) }, as_of: at(74),
};

export interface SuppliersMock {
  body?: S["SuppliersPage"];
  status?: number;
  hold?: boolean;
}

/** The product shell's calls, the suppliers endpoint (or `status` with a problem; `hold` never answers), and
 *  POST /v1/profit/calc answering each supplier's own row cost; without a supplier, the best complete margin in
 *  stock or not (DEC-246 f). Returns the calc request bodies, in order. */
export async function mockSuppliersApi(page: Page, options: SuppliersMock = {}) {
  await mockProductApi(page);
  const body = options.body ?? suppliers;
  // Registered after the product route, so these answer first.
  await page.route("**/api/v1/products/*/suppliers**", async (route) => {
    if (options.hold) return;
    if (options.status) return route.fulfill({ status: options.status, contentType: "application/problem+json", json: problem(options.status, `e2e-suppliers-${options.status}`) });
    return route.fulfill({ json: body });
  });
  const requests: S["ProfitCalcRequest"][] = [];
  await page.route("**/api/v1/profit/calc", async (route) => {
    const request = route.request().postDataJSON() as S["ProfitCalcRequest"];
    requests.push(request);
    const ranked = body.rows.filter((r) => r.cost.complete).sort((a, b) => b.cost.margin_minor! - a.cost.margin_minor!);
    const chosen = body.rows.find((r) => r.listing_id === request.supplier_listing_id) ?? ranked[0] ?? body.rows[0];
    return route.fulfill({ json: chosen.cost });
  });
  return requests;
}
