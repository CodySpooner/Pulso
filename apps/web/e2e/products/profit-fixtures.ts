import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { NOW, problem } from "../data-health/fixtures";
import { mockProductApi, PRODUCT_ID } from "./fixtures";

// p2-20 (UX-8 part b): fixture POST /v1/profit/calc answers for the Profit tab e2e tests and screenshots, never a
// database restore. Times are relative to Data Health's NOW, which mockAdminApi pins with page.clock.

type S = components["schemas"];
type Calc = S["ProfitCalc"];
type Request = S["ProfitCalcRequest"];
const at = (hoursAgo: number) => new Date(NOW.getTime() - hoursAgo * 3_600_000).toISOString();
const observed = (source: string, source_name: string, hoursAgo: number, raw_payload_id: number, stale = false): S["InputSource"] => ({
  source, source_name, as_of: at(hoursAgo), raw_payload_id, stale,
});
const settings: S["InputSource"] = { source: "settings", source_name: "Workspace settings", as_of: null, raw_payload_id: null, stale: false };
const estimate: S["InputSource"] = { source: "owner_estimate", source_name: "Your estimate", as_of: null, raw_payload_id: null, stale: false };
const RATES = ["duty_bps", "customs_fee_minor", "payment_fee_bps", "payment_fee_fixed_minor", "shopify_fee_bps", "returns_bps", "ad_cost_minor"];

/** The Profit note's worked example as the endpoint answers it. apps/api/tests/test_profit.py
 *  `test_the_profit_tab_gets_net_profit_rates_freight_days_and_named_sources` pins these numbers to the server. */
export const complete: Calc = {
  product_id: PRODUCT_ID, supplier_listing_id: 88123, variant_id: null, quantity: 1, method: "CJPacket", freight_min_days: 8,
  freight_max_days: 12, ddp: false, currency: "USD",
  price_minor: 2999, goods_minor: 620, freight_minor: 485, duty_minor: 124, customs_fee_minor: 0, payment_fee_minor: 117,
  shopify_fee_minor: 0, returns_minor: 150, landed_cost_minor: 1229, margin_minor: 1503, margin_bps: 5012, ad_cost_minor: 1500,
  net_minor: 3, net_bps: 10, duty_bps: 2000, payment_fee_bps: 290, payment_fee_fixed_minor: 30, shopify_fee_bps: 0, returns_bps: 500,
  complete: true, missing: [], estimates: [],
  sources: {
    price_minor: observed("shopify_stores", "Shopify stores", 6, 902077),
    unit_cost: observed("cj", "CJ Dropshipping", 9, 901877),
    freight: observed("cj", "CJ Dropshipping", 9, 901880),
    ...Object.fromEntries(RATES.map((name) => [name, settings])),
  },
};

/** One price-slider step up ($30.49), pinned by the same test. */
export const step: Calc = {
  ...complete, price_minor: 3049, payment_fee_minor: 118, returns_minor: 152, margin_minor: 1550, margin_bps: 5084, net_minor: 50, net_bps: 164,
  estimates: ["price_minor"], sources: { ...complete.sources, price_minor: estimate },
};

const withheld = { landed_cost_minor: null, margin_minor: null, margin_bps: null, net_minor: null, net_bps: null, complete: false } as const;
const without = (sources: Calc["sources"], ...names: string[]) => Object.fromEntries(Object.entries(sources).filter(([name]) => !names.includes(name)));

/** The supplier has no US quote for this variant: freight is missing, so nothing is totalled. */
export const noFreight: Calc = {
  ...complete, ...withheld, method: null, freight_min_days: null, freight_max_days: null, freight_minor: null, missing: ["freight_missing"],
  sources: without(complete.sources, "freight"),
};

/** No freight quote and no US duty rate in Settings: the common state before Settings is filled in. */
export const incomplete: Calc = {
  ...noFreight, duty_minor: null, duty_bps: null, missing: ["freight_missing", "duty_not_set"],
  sources: without(complete.sources, "freight", "duty_bps"),
};

/** No store sells it in USD yet: the price is the owner's to enter. */
export const noPrice: Calc = {
  ...complete, ...withheld, landed_cost_minor: 1229, price_minor: null, payment_fee_minor: null, shopify_fee_minor: null, returns_minor: null,
  missing: ["price_missing"], sources: without(complete.sources, "price_minor"),
};

/** No supplier listing is matched: there is nothing to cost. */
export const noSupplier: Calc = {
  ...noPrice, supplier_listing_id: null, method: null, freight_min_days: null, freight_max_days: null, goods_minor: null, freight_minor: null,
  duty_minor: null, landed_cost_minor: null, missing: ["price_missing", "supplier_cost_missing", "freight_missing"],
};

/** CJ last answered 3 days ago, past twice its interval. */
export const stale: Calc = {
  ...complete,
  sources: { ...complete.sources, unit_cost: observed("cj", "CJ Dropshipping", 74, 880211, true), freight: observed("cj", "CJ Dropshipping", 74, 880214, true) },
};

/** The fixture the endpoint would answer for `request`: the pinned vectors, or, for any other scenario, the worked
 *  example's numbers with the request's inputs echoed (the keyboard test checks requests and slider values, not
 *  maths; the server's landed_cost() is the only implementation). */
function answer(base: Calc, request: Request): Calc {
  const changed = Object.keys(request).filter((key) => !["product_id", "quantity", "ddp"].includes(key));
  if (changed.length === 0 && (request.quantity ?? 1) === 1) return base;
  if (base === complete && changed.join() === "price_minor" && request.price_minor === 3049) return step;
  if (base === noPrice && changed.join() === "price_minor" && request.price_minor === 2999)
    return { ...complete, estimates: ["price_minor"], sources: { ...complete.sources, price_minor: estimate } };
  const echo = {
    quantity: request.quantity ?? 1,
    price_minor: request.price_minor ?? base.price_minor,
    returns_bps: request.returns_bps ?? base.returns_bps,
    payment_fee_bps: request.payment_fee_bps ?? base.payment_fee_bps,
    ad_cost_minor: request.ad_cost_minor ?? base.ad_cost_minor,
  };
  return { ...base, ...echo, estimates: changed.sort(), sources: { ...base.sources, ...Object.fromEntries(changed.map((k) => [k, estimate])) } };
}

export interface ProfitMock {
  /** What the defaults request answers; other scenarios follow `answer`. */
  body?: Calc;
  /** Answer every calc with this problem status, or only the ones after the first (`failRecompute`). */
  status?: number;
  failRecompute?: boolean;
  /** Never answer: the first-load skeleton stays. */
  hold?: boolean;
}

/** The product shell's calls plus POST /v1/profit/calc. Returns the calc request bodies, in order. */
export async function mockProfitApi(page: Page, options: ProfitMock = {}) {
  await mockProductApi(page);
  const requests: Request[] = [];
  await page.route("**/api/v1/profit/calc", async (route) => {
    const request = route.request().postDataJSON() as Request;
    requests.push(request);
    if (options.hold) return;
    const status = options.status ?? (options.failRecompute && requests.length > 1 ? 503 : 0);
    if (status) return route.fulfill({ status, contentType: "application/problem+json", json: problem(status, `e2e-profit-${status}`) });
    return route.fulfill({ json: answer(options.body ?? complete, request) });
  });
  return requests;
}
