import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { healthySources, mockAdminApi, NOW, problem } from "../data-health/fixtures";

// Fixture /v1/tests for the Testing Board e2e tests and screenshots, never a database restore. The mock keeps moves
// and edits like the API (DEC-312): CPA half-even and ROAS computed on read, 422 `kill_reason` for Killed without a
// reason, the start snapshot taken on the first entry to Testing, 409 for a second open test of a product.

type S = components["schemas"];
type Test = S["ProductTestOut"];
const at = (hours: number) => new Date(NOW.getTime() - hours * 3_600_000).toISOString();
const COLORS = ["#d97706", "#7c3aed", "#0891b2", "#16a34a", "#db2777", "#2563eb", "#ca8a04"];
const svg = (fill: string) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><rect width="120" height="120" fill="#1f2125"/><circle cx="60" cy="52" r="26" fill="${fill}"/><rect x="34" y="84" width="52" height="10" rx="5" fill="${fill}" opacity=".55"/></svg>`;
export const PRODUCT = (id: number) => `5e7a0c11-0000-4000-8000-${String(id).padStart(12, "0")}`;

/** The worked example of vault Features/Testing Board: $39.99 price, $14.20 landed, break-even CPA $24.33. */
export const snapshot = {
  complete: true,
  price_minor: 3999,
  landed_cost_minor: 1420,
  margin_minor: 2433,
  missing: [],
  captured_at: at(72),
};
const incomplete = { ...snapshot, complete: false, price_minor: null, landed_cost_minor: null, margin_minor: null, missing: [{ input: "price", reason: "price_missing" }] };

function test(id: number, product_title: string, over: Partial<Test> = {}): Test {
  return {
    id,
    product_id: PRODUCT(id),
    product_title,
    product_image_url: `https://cdn.example.test/t/${id}.svg`,
    stage: "idea",
    started_on: null,
    ended_on: null,
    currency: "USD",
    ad_spend_minor: 0,
    revenue_minor: 0,
    orders: 0,
    cpa_minor: null,
    roas: null,
    notes: null,
    kill_reason: null,
    start_snapshot: null,
    break_even_cpa_minor: null,
    stop_loss_minor: null,
    signal: null,
    signal_reason: null,
    created_at: at(240),
    updated_at: at(2),
    ...over,
  };
}

export const tests = (): Test[] => [
  // The worked example at its $48.66 stop-loss with no orders, and six orders at $20.00 against $24.33 (DEC-340).
  test(9, "LED strip lights", { stage: "testing", started_on: "2026-10-19", ad_spend_minor: 4866, start_snapshot: snapshot, updated_at: at(3) }),
  test(8, "Heatless curling ribbon", { stage: "testing", started_on: "2026-10-12", ad_spend_minor: 12000, revenue_minor: 23994, orders: 6, start_snapshot: snapshot, updated_at: at(5) }),
  test(7, "Sunset projection lamp"),
  test(6, "Magnetic car phone mount", { stage: "researching", product_image_url: null }),
  test(5, "Posture corrector brace", { stage: "testing", started_on: "2026-10-19", ad_spend_minor: 20000, revenue_minor: 25999, orders: 3, start_snapshot: snapshot, updated_at: at(1) }),
  test(4, "Galaxy star projector", { stage: "testing", started_on: "2026-10-17", ad_spend_minor: 4866, start_snapshot: incomplete, updated_at: at(72) }),
  test(3, "Mini waffle maker", { stage: "winner", started_on: "2026-10-01", ended_on: "2026-10-14", ad_spend_minor: 31000, revenue_minor: 98000, orders: 24, start_snapshot: snapshot }),
  test(2, "Cloud pillow slides", { stage: "killed", started_on: "2026-09-20", ended_on: "2026-09-27", ad_spend_minor: 9800, orders: 0, kill_reason: "saturated", start_snapshot: snapshot }),
  test(1, "Pet hair remover roller", { stage: "killed", started_on: "2026-09-10", ended_on: "2026-09-16", ad_spend_minor: 15000, revenue_minor: 7998, orders: 2, kill_reason: "cpa_above_break_even", start_snapshot: snapshot }),
];

/** What the API computes on read: CPA half-even to the cent, ROAS a float, both null on a zero divisor; break-even
 *  CPA, 2 × it and the Testing signal (k = 2, N = 5, DEC-340). */
function computed(t: Test): Test {
  const exact = t.ad_spend_minor / t.orders;
  const floor = Math.floor(exact);
  const half = exact - floor === 0.5 ? (floor % 2 === 0 ? floor : floor + 1) : Math.round(exact);
  const cpa = t.orders ? half : null;
  const be = (t.start_snapshot as { margin_minor?: number | null } | null)?.margin_minor ?? null;
  const testing = t.stage === "testing" && be != null;
  const over = testing && ((t.orders === 0 && t.ad_spend_minor >= 2 * be) || (t.orders >= 5 && cpa! > be));
  return {
    ...t,
    cpa_minor: cpa,
    roas: t.ad_spend_minor ? t.revenue_minor / t.ad_spend_minor : null,
    break_even_cpa_minor: be,
    stop_loss_minor: be != null && be > 0 ? 2 * be : null,
    signal: over ? "over_stop_loss" : testing && t.orders >= 5 ? "winner_candidate" : null,
    signal_reason: t.stage === "testing" && be == null ? "Set price and supplier to compute break-even." : null,
  };
}

/** GET /v1/tests/{id}'s comparison: a newer freight quote and a higher duty rate on the worked example, none for the
 *  rest; `sinceStart` overrides it per test id. */
const SINCE: S["SinceStart"] = {
  changes: [
    { input: "freight_quote_id", old: 41, new: 57 },
    { input: "freight_minor", old: 400, new: 520 },
    { input: "duty_bps", old: 2000, new: 2500 },
    { input: "margin_minor", old: 2433, new: 2271 }, // $8.50 goods: duty $1.70 → $2.12; $24.33 − $1.20 − $0.42
  ],
  reason: null,
  as_of: at(20),
};

export interface TestingMock {
  items?: Test[];
  /** GET /v1/tests never answers: the skeleton stays. */
  hold?: boolean;
  /** GET /v1/tests answers with this problem status. */
  status?: number;
  /** PATCH answers 503. */
  failPatch?: boolean;
  /** GET /v1/tests/{id}'s `since_start` by test id; tests 5 and 9 default to SINCE, the rest to no changes. */
  sinceStart?: Record<number, S["SinceStart"] | "error">;
}

export async function mockTestingApi(page: Page, options: TestingMock = {}) {
  const rows = (options.items ?? tests()).map(computed);
  const patches: Record<string, unknown>[] = [];
  const posts: Record<string, unknown>[] = [];
  let next = 100;
  await mockAdminApi(page, { sources: healthySources });
  await page.route("https://cdn.example.test/t/**", (route) => {
    const id = Number.parseInt(new URL(route.request().url()).pathname.split("/").pop()!, 10);
    return route.fulfill({ contentType: "image/svg+xml", body: svg(COLORS[id % COLORS.length]) });
  });
  await page.route("**/api/v1/tests**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(/^\/api/, "");
    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body });
    const fail = (status: number, code: string, detail: string) =>
      route.fulfill({ status, contentType: "application/problem+json", json: { ...problem(status, `e2e-tests-${code}`), code, detail } });
    if (request.method() === "GET" && path === "/v1/tests") {
      if (options.hold) return;
      if (options.status) return route.fulfill({ status: options.status, contentType: "application/problem+json", json: problem(options.status, "e2e-tests") });
      const kill_reasons: Record<string, number> = {};
      for (const t of rows) if (t.kill_reason) kill_reasons[t.kill_reason] = (kill_reasons[t.kill_reason] ?? 0) + 1;
      return json({ items: [...rows].sort((a, b) => b.id - a.id), next_cursor: null, kill_reasons } satisfies S["ProductTestPage"]);
    }
    if (request.method() === "POST" && path === "/v1/tests") {
      const body = request.postDataJSON() as { product_id: string };
      posts.push(body);
      if (rows.some((t) => t.product_id === body.product_id && ["idea", "researching", "testing"].includes(t.stage)))
        return fail(409, "conflict", "The request conflicts with existing data.");
      const made = computed(test(next++, "Sunset projection lamp", { product_id: body.product_id, created_at: NOW.toISOString(), updated_at: NOW.toISOString() }));
      rows.push(made);
      return json(made, 201);
    }
    const one = path.match(/^\/v1\/tests\/(\d+)$/);
    const row = one && rows.find((t) => t.id === Number(one[1]));
    if (request.method() === "GET" && row) {
      const since = options.sinceStart?.[row.id] ?? ([5, 9].includes(row.id) ? SINCE : { changes: [], reason: null, as_of: at(20) });
      if (since === "error") return fail(503, "unavailable", "The API is restarting. Try again.");
      return json({ ...row, since_start: row.start_snapshot ? since : null } satisfies S["ProductTestDetail"]);
    }
    if (request.method() === "PATCH" && row) {
      const body = request.postDataJSON() as Partial<Test>;
      patches.push(body);
      if (options.failPatch) return fail(503, "unavailable", "The API is restarting. Try again.");
      const stage = body.stage ?? row.stage;
      const kill_reason = "kill_reason" in body ? body.kill_reason : stage === "killed" ? row.kill_reason : null;
      if ((stage === "killed") !== (kill_reason != null)) return fail(422, "kill_reason", "Killed needs a kill reason, and only Killed has one.");
      const ended = stage === "winner" || stage === "killed";
      Object.assign(row, body, {
        stage,
        kill_reason,
        started_on: body.started_on !== undefined ? body.started_on : stage === "testing" ? (row.started_on ?? NOW.toISOString().slice(0, 10)) : row.started_on,
        ended_on: body.ended_on !== undefined ? body.ended_on : ended ? (row.ended_on ?? NOW.toISOString().slice(0, 10)) : null,
        start_snapshot: row.start_snapshot ?? (stage === "testing" ? { ...snapshot, captured_at: NOW.toISOString() } : null),
        updated_at: NOW.toISOString(),
      });
      Object.assign(row, computed(row));
      return json(row);
    }
    return json(problem(404, "e2e-tests-404"), 404);
  });
  return {
    patches,
    posts,
    rows,
    failLists: (status = 503) => (options.status = status),
    failPatches: (on = true) => (options.failPatch = on),
  };
}
