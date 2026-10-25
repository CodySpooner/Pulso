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
  ...over,
});

export const rules = (): S["RuleOut"][] => [
  rule(1, "Testing: supplier cost change", "supplier_price_change", {}),
  rule(2, "Testing: freight change", "freight_change", { status: "skipped", skipped: { reason: "gap", from: at(80), to: at(30) } }),
  rule(3, "Testing: supplier stock-out", "supplier_stock_out", { status: "no_source" }),
];

export interface AlertsMock {
  items?: Stored[];
  rules?: S["RuleOut"][];
  /** GET /v1/alerts never answers: the skeletons stay. */
  hold?: boolean;
  /** GET /v1/alerts answers with this problem status. */
  status?: number;
}

export async function mockAlertsApi(page: Page, options: AlertsMock = {}) {
  const rows = options.items ?? alerts();
  const writes: { path: string; body: unknown }[] = [];
  const unread = () => ({ count: rows.filter((a) => !a.read_at && !a.archived).length });
  await mockAdminApi(page, { sources: healthySources });
  await page.route("**/api/v1/alert-rules**", (route) => route.fulfill({ json: { items: options.rules ?? rules(), next_cursor: null } satisfies S["RulePage"] }));
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
      return route.fulfill({ json: { items: items.map(({ archived: _, ...a }) => a), next_cursor } satisfies S["AlertPage"] });
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
  return { rows, writes };
}
