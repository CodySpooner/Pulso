import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { healthySources, mockAdminApi, NOW, problem } from "../data-health/fixtures";
import { PRODUCT_ID } from "../products/fixtures";

// Fixture /v1/alerts and /v1/alert-rules for the bell and /alerts e2e tests and screenshots, never a database restore.
// The mock keeps state like the API (DEC-330, DEC-333): newest first, archived only with ?archived=true, the first
// read time kept, writes return the unread count, and an id that isn't one of the alerts is 404 with nothing changed.

type S = components["schemas"];
type Stored = S["AlertOut"] & { archived: boolean };
const at = (hours: number) => new Date(NOW.getTime() - hours * 3_600_000).toISOString();
const usd = (value: number, hours: number, source?: string) => ({ value, currency: "USD", as_of: at(hours), ...(source && { source, raw_payload_id: 900_000 + value }) });
const flip = (from: boolean, to: boolean, hours: number) => ({ old: { value: from, as_of: at(hours + 24) }, new: { value: to, as_of: at(hours), source: "cj", raw_payload_id: 901_000 } });
const link = `/products/${PRODUCT_ID}/suppliers`;

function alert(id: number, type: string, hours: number, payload: Record<string, unknown>, read = false): Stored {
  return { id, rule_id: null, type, entity_type: "supplier_offer", entity_id: String(4800 + id), fired_at: at(hours), payload: { link, ...payload }, read_at: read ? at(hours - 1) : null, archived: false };
}

export const alerts = (): Stored[] => [
  alert(6, "supplier_price_change", 2, { old: usd(1240, 50), new: usd(1390, 3, "cj"), threshold: { pct: 5 } }),
  alert(5, "freight_change", 8, { old: usd(500, 60), new: usd(450, 9, "cj"), threshold: { pct: 5 } }),
  alert(4, "supplier_stock_out", 13, flip(true, false, 14)),
  alert(3, "back_in_stock", 40, flip(false, true, 41), true),
  alert(2, "supplier_price_change", 75, { old: usd(2000, 200), new: usd(1890, 76, "cj"), threshold: { pct: 5 } }, true),
  alert(1, "freight_change", 120, { old: usd(700, 300), new: usd(790, 121, "cj"), threshold: { pct: 10 } }, true),
];

/** p4-34 (DEC-353): a velocity spike and a Saturation cross on the lamp, newer than the fixture's six. */
export const scoreAlerts = (): Stored[] =>
  [
    alert(8, "velocity_spike", 1, {
      old: { value: 22, as_of: at(178) },
      new: { value: 34, as_of: at(14), source: "cj", model_version: "000-life" },
      threshold: { pct: 50, window_days: 7, min_volume: 10 },
      link: `/products/${PRODUCT_ID}/trends`,
      product: "Sunset projection lamp",
    }),
    alert(7, "saturation_cross", 1.5, {
      old: { value: 61.2, as_of: at(38) },
      new: { value: 66.4, as_of: at(14), source: "shopify_stores", model_version: "000-sat" },
      threshold: { threshold: 65, direction: "above" },
      link: `/products/${PRODUCT_ID}`,
      product: "Sunset projection lamp",
    }),
  ].map((a) => ({ ...a, entity_type: "product", entity_id: PRODUCT_ID }));

/** `extra` more read price alerts, a day apart, older than the fixture's six. */
export const older = (extra: number): Stored[] =>
  Array.from({ length: extra }, (_, i) => alert(-i - 1, "supplier_price_change", 130 + 24 * i, { old: usd(1000, 900), new: usd(1100 + i, 131 + 24 * i, "cj") }, true));

const rule = (n: number, name: string, type: string, over: Partial<S["RuleOut"]>): S["RuleOut"] => ({
  id: `0a1e0000-0000-4000-8000-00000000000${n}`,
  name,
  type,
  target_type: "test",
  target_id: null,
  params: {},
  enabled: true,
  muted_until: null,
  armed: true,
  status: "ok",
  skipped: null,
  last_evaluated_at: at(8),
  created_at: at(400),
  product_id: null,
  product_name: null,
  watchlist_name: null,
  last_fired_at: null,
  ...over,
});

export const rules = (): S["RuleOut"][] => [
  rule(1, "Testing: supplier cost change", "supplier_price_change", {}),
  rule(2, "Testing: freight change", "freight_change", { status: "skipped", skipped: { reason: "gap", from: at(80), to: at(30) } }),
  rule(3, "Testing: supplier stock-out", "supplier_stock_out", { status: "no_source" }),
];

const lamp = { product_id: PRODUCT_ID, product_name: "Sunset projection lamp" };

/** WF-4c (p4-27): two rules on a product above the Testing defaults: one offer's price (fired, muted for a day), and
 *  stock-outs on any of its suppliers (off, never fired). */
export const ruleList = (): S["RuleOut"][] => [
  rule(5, "Lamp: supplier price ±8%", "supplier_price_change", {
    ...lamp,
    target_type: "supplier_offer",
    target_id: "4806",
    params: { pct: 8 },
    muted_until: at(-24),
    last_fired_at: at(2),
    created_at: at(30),
  }),
  rule(4, "Lamp: stock-out", "supplier_stock_out", { ...lamp, target_type: "product", target_id: PRODUCT_ID, params: { pct: 5 }, enabled: false, status: null, last_evaluated_at: null, created_at: at(40) }),
  ...rules(),
];

export const PET_LIST = "a0000000-0000-4000-8000-000000000002";
export const lists = (): S["Watchlist"][] => [{ id: PET_LIST, name: "Pet", position: 1, item_count: 4, created_at: at(500) }];

/** p4-34 (DEC-353): a velocity spike on the lamp, skipped over a data gap, and a Saturation cross on the Pet
 *  watchlist with no source yet (Saturation reads Shopify stores, off until DEC-261 lifts). */
export const scoreRules = (): S["RuleOut"][] => [
  rule(7, "Lamp: velocity +50%", "velocity_spike", {
    ...lamp,
    target_type: "product",
    target_id: PRODUCT_ID,
    params: { pct: 50, window_days: 7, min_volume: 10 },
    status: "skipped",
    skipped: { reason: "gap", from: "2026-10-08", to: "2026-10-22" },
    last_fired_at: at(80),
    created_at: at(10),
  }),
  rule(6, "Pet: saturation above 65", "saturation_cross", { target_type: "watchlist", target_id: PET_LIST, watchlist_name: "Pet", params: { threshold: 65, direction: "above" }, status: "no_source", created_at: at(20) }),
  ...ruleList(),
];

export interface AlertsMock {
  items?: Stored[];
  rules?: S["RuleOut"][];
  /** GET /v1/watchlists answers with these (the builder's watchlist targets). */
  lists?: S["Watchlist"][];
  /** GET /v1/alerts never answers: the skeletons stay. */
  hold?: boolean;
  /** GET /v1/alerts answers with this problem status. */
  status?: number;
  /** GET /v1/alert-rules never answers, or answers with this problem status. */
  holdRules?: boolean;
  rulesStatus?: number;
}

const unprocessable = (loc: string[], msg: string) => ({ status: 422, contentType: "application/problem+json", json: { ...problem(422, "e2e-rules-422"), code: "validation_error", detail: "Invalid request.", errors: [{ loc, msg, type: "e2e" }] } });

export async function mockAlertsApi(page: Page, options: AlertsMock = {}) {
  const rows = options.items ?? alerts();
  const writes: { path: string; body: unknown }[] = [];
  const unread = () => ({ count: rows.filter((a) => !a.read_at && !a.archived).length });
  const ruleRows = options.rules ?? rules();
  const ruleWrites: { method: string; id?: string; body: unknown }[] = [];
  await mockAdminApi(page, { sources: healthySources });
  if (options.lists) {
    const listed = options.lists;
    await page.route("**/api/v1/watchlists", (route) => route.fulfill({ json: listed }));
  }
  // The rules keep what the page writes, like the API (DEC-324, DEC-339, DEC-353): newest first; a % must be over 0
  // and a Saturation line 0–100; a Testing default can't be deleted.
  await page.route("**/api/v1/alert-rules**", (route) => {
    const request = route.request();
    const method = request.method();
    const id = new URL(request.url()).pathname.split("/")[4];
    if (method === "GET") {
      if (options.holdRules) return;
      if (options.rulesStatus) return route.fulfill({ status: options.rulesStatus, contentType: "application/problem+json", json: problem(options.rulesStatus, "e2e-rules") });
      return route.fulfill({ json: { items: ruleRows, next_cursor: null } satisfies S["RulePage"] });
    }
    const body = (method === "DELETE" ? null : request.postDataJSON()) as (Partial<S["RuleIn"]> & { muted_until?: string | null }) | null;
    ruleWrites.push({ method, id, body });
    if (body?.params && "pct" in body.params && !(Number(body.params.pct) > 0)) return route.fulfill(unprocessable(["body", "params", "pct"], "Input should be greater than 0"));
    const line = Number(body?.params?.threshold ?? 0);
    if (!(line >= 0 && line <= 100)) return route.fulfill(unprocessable(["body", "params", "threshold"], "Input should be less than or equal to 100"));
    if (body?.name === "") return route.fulfill(unprocessable(["body", "name"], "String should have at least 1 character"));
    if (method === "POST") {
      const listed = body!.target_type === "watchlist" ? { product_id: null, product_name: null, watchlist_name: options.lists?.find((l) => l.id === body!.target_id)?.name ?? null } : lamp;
      const made = rule(9, body!.name!, body!.type!, { ...listed, target_type: body!.target_type!, target_id: body!.target_id!, params: body!.params!, status: null, last_evaluated_at: null, created_at: NOW.toISOString() });
      ruleRows.unshift(made);
      return route.fulfill({ status: 201, json: made });
    }
    const at = ruleRows.findIndex((r) => r.id === id);
    if (method === "DELETE") return route.fulfill({ json: ruleRows.splice(at, 1)[0] });
    Object.assign(ruleRows[at], body);
    return route.fulfill({ json: ruleRows[at] });
  });
  await page.route("**/api/v1/alerts**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api/, "");
    const q = url.searchParams;
    if (path === "/v1/alerts/unread-count") return route.fulfill({ json: unread() });
    if (path === "/v1/alerts" && request.method() === "GET") {
      if (options.hold) return;
      if (options.status) return route.fulfill({ status: options.status, contentType: "application/problem+json", json: problem(options.status, "e2e-alerts") });
      const archived = q.get("archived") === "true";
      const listed = rows
        .filter((a) => a.archived === archived && (!q.has("type") || a.type === q.get("type")) && (!q.has("unread") || (q.get("unread") === "true") === !a.read_at))
        .sort((a, b) => b.fired_at.localeCompare(a.fired_at) || b.id - a.id);
      const limit = Number(q.get("limit") ?? 50);
      const start = q.has("cursor") ? listed.findIndex((a) => String(a.id) === q.get("cursor")) + 1 : 0;
      const items = listed.slice(start, start + limit);
      const next_cursor = start + limit < listed.length ? String(items.at(-1)!.id) : null;
      return route.fulfill({ json: { items: items.map((a) => ({ ...a, archived: undefined })), next_cursor } satisfies S["AlertPage"] });
    }
    const body = request.postDataJSON() as { ids?: number[]; all?: boolean };
    writes.push({ path, body });
    const chosen = body.all ? rows : rows.filter((a) => body.ids?.includes(a.id));
    if (!body.all && chosen.length !== new Set(body.ids).size) return route.fulfill({ status: 404, contentType: "application/problem+json", json: { ...problem(404, "e2e-alerts-404"), code: "not_found", detail: "Alert not found." } });
    for (const a of chosen) {
      if (path === "/v1/alerts/read") a.read_at ??= NOW.toISOString();
      if (path === "/v1/alerts/archive") a.archived = true;
      if (path === "/v1/alerts/unarchive") a.archived = false;
    }
    return route.fulfill({ json: unread() });
  });
  return { rows, writes, ruleRows, ruleWrites };
}
