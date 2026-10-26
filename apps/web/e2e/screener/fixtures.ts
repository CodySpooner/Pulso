import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { healthySources, mockAdminApi, NOW, problem } from "../data-health/fixtures";
import { mockProductApi, product } from "../products/fixtures";

// p4-32 (WF-1b): fixture GET /v1/screener pages and an in-memory /v1/screens store, for the Screener e2e tests and
// screenshots; never a database restore. Times are relative to Data Health's NOW (mockAdminApi pins the clock).

type S = components["schemas"];
const at = (hoursAgo: number) => new Date(NOW.getTime() - hoursAgo * 3_600_000).toISOString();
export const DAY = at(24).slice(0, 10); // yesterday (UTC), the newest scored day
export const NULL_TREND = "Under 14 days of history in every demand family.";
const STAGES = ["emerging", "rising", "peaking", "declining", "dead"] as const;
const NAMES = ["Sunset projection lamp", "Magnetic car phone mount", "Posture corrector brace", "Portable USB blender", "Cloud pillow slides", "Mini waffle maker", "Smart LED strip lights", "Pet hair remover roller", "Facial ice roller", "Electric scalp massager", "Car seat gap filler", "Galaxy star projector"];
const none = (reason: string) => ({ value: null, reason });
const sourced = (value: number, source: "cj" | "shopify_stores", raw: number): S["Sourced"] => ({
  value, source, source_name: source === "cj" ? "CJ Dropshipping" : "Shopify stores", as_of: at(9), raw_payload_id: raw, method: null, stale: false,
});
const score = (value: number | null, stage: S["LatestScore"]["stage"] = null): S["LatestScore"] => ({ value, stage, day: DAY, model_version: "v0.1.0", as_of: at(14), reason: null });
const NO_ROW = none("No source yet: nothing has scored this product.");

/** Row `i`: row 0 has a NULL Trend row (insufficient signal), row 1 no score rows at all, the rest a mix of gaps. */
export function screenerRow(i: number): S["ScreenerRow"] {
  const price = 1500 + ((i * 731) % 4800);
  const velocity: S["ScreenerRow"]["velocity"] =
    i % 5 === 4
      ? none("No demand family has a 7-day growth yet.")
      : { ...sourced(80 - ((i * 7) % 70), "shopify_stores", 0), raw_payload_id: null, method: "Shopify updated_at bumps, a lower bound", family: "shp_bump", grade: i % 3 ? "B" : "A", growth: 1.2 - i * 0.07, gap: false };
  return {
    id: `00000000-0000-4000-9000-${String(i).padStart(12, "0")}`,
    title: NAMES[i % NAMES.length] + (i >= NAMES.length ? ` ${Math.floor(i / NAMES.length) + 1}` : ""),
    image_url: `https://cdn.example.test/p/${i}.svg`,
    category: "Home & Garden > Lighting > Lamps",
    currency: "USD",
    price_minor: sourced(price, "shopify_stores", 905000 + i),
    margin:
      i % 4 === 1
        ? { value: null, reason: "Needs a duty rate.", missing: ["duty_not_set"] }
        : { ...sourced(Math.round(price * 0.42), "cj", 908000 + i), margin_bps: 4200 - i * 40, supplier_listing_id: 907000 + i, method: "Landed cost, default scenario" },
    velocity,
    acceleration: "family" in velocity ? { value: 0.3 - i * 0.06, family: "shp_bump", source: "shopify_stores", source_name: "Shopify stores", as_of: at(14), stale: false } : none("No demand family has a 7-day growth yet."),
    supplier_rating: sourced(420 + (i % 8) * 10, "cj", 909000 + i),
    ship_days_us: i % 6 === 5 ? none("No live supplier listing has a US delivery estimate yet.") : sourced(6 + (i % 9), "cj", 910000 + i),
    trend: i === 0 ? { ...score(null), reason: NULL_TREND } : i === 1 ? NO_ROW : score(92 - i * 3),
    saturation: i === 1 ? NO_ROW : score(18 + i * 2),
    lifecycle: i === 1 ? NO_ROW : score(null, STAGES[i % 5]),
    opportunity: i < 2 ? { value: null, as_of: null, confidence: null, reason: "No Trend score yet.", missing: ["trend", "risk"] } : { value: 81 - i * 2, as_of: at(14), confidence: 0.7, reason: null, missing: ["risk"] },
  };
}
export const rows = (n: number) => Array.from({ length: n }, (_, i) => screenerRow(i));

export interface ScreenerMock {
  items?: S["ScreenerRow"][];
  pageSize?: number;
  screens?: S["SavedScreen"][];
  /** Answer GET /v1/screener with this problem status; read per request, so a test can clear it. */
  status?: number;
  /** GET /v1/screener answers with no rows. */
  empty?: boolean;
}

/** The shell's admin calls, GET /v1/categories, GET /v1/screener (cursor = offset) and /v1/screens kept in memory as
 *  the API keeps them (409 on a used name). Returns the screener request URLs and the screens store. */
export async function mockScreenerApi(page: Page, options: ScreenerMock = {}) {
  const { items = rows(12), pageSize = 50 } = options;
  const calls: URL[] = [];
  const screens = new Map((options.screens ?? []).map((s) => [s.id, s]));
  await mockAdminApi(page, { sources: healthySources });
  await page.route("https://cdn.example.test/p/**", (route) => {
    const hue = (Number(route.request().url().match(/(\d+)\.svg$/)?.[1] ?? 0) * 47) % 360;
    return route.fulfill({ contentType: "image/svg+xml", body: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="24" height="24" fill="hsl(${hue} 45% 40%)"/><circle cx="12" cy="11" r="5" fill="hsl(${hue} 30% 92%)"/></svg>` });
  });
  await page.route("**/api/v1/categories", (route) => route.fulfill({ json: [{ id: 7, path: "Home & Garden > Lighting > Lamps" }] }));
  await page.route((url) => url.pathname === "/api/v1/screener", (route) => {
    const url = new URL(route.request().url());
    calls.push(url);
    if (options.status) return route.fulfill({ status: options.status, contentType: "application/problem+json", json: problem(options.status, "e2e-screener") });
    const offset = Number(url.searchParams.get("cursor") ?? 0);
    const list = options.empty ? [] : items;
    const body: S["ScreenerPage"] = { items: list.slice(offset, offset + pageSize), next_cursor: offset + pageSize < list.length ? String(offset + pageSize) : null, unapplied: {} };
    return route.fulfill({ json: body });
  });
  await page.route("**/api/v1/screens**", async (route) => {
    const request = route.request();
    const id = new URL(request.url()).pathname.split("/")[4];
    const taken = (name: string, except?: string) => [...screens.values()].some((s) => s.name === name && s.id !== except);
    const conflict = { status: 409, contentType: "application/problem+json", json: { ...problem(409, "e2e-screens"), code: "conflict", title: "Conflict" } };
    if (!id && request.method() === "GET") return route.fulfill({ json: { items: [...screens.values()].sort((a, b) => a.name.localeCompare(b.name)), next_cursor: null } });
    if (!id) {
      const given = request.postDataJSON() as S["ScreenIn"];
      if (taken(given.name.trim())) return route.fulfill(conflict);
      const screen: S["SavedScreen"] = { filters: {}, columns: null, ...given, name: given.name.trim(), id: crypto.randomUUID(), version: 1, created_at: NOW.toISOString() };
      screens.set(screen.id, screen);
      return route.fulfill({ status: 201, json: screen });
    }
    const screen = screens.get(id);
    if (!screen) return route.fulfill({ status: 404, contentType: "application/problem+json", json: { ...problem(404, "e2e-screen"), code: "not_found", detail: "Saved screen not found." } });
    if (request.method() === "PATCH") {
      const patch = request.postDataJSON() as S["ScreenPatch"];
      if (patch.name && taken(patch.name, id)) return route.fulfill(conflict);
      const next = { ...screen, ...Object.fromEntries(Object.entries(patch).filter(([k, v]) => v !== null || k === "columns")) } as S["SavedScreen"];
      screens.set(id, next);
      return route.fulfill({ json: next });
    }
    if (request.method() === "DELETE") screens.delete(id);
    return route.fulfill({ json: screen });
  });
  return { calls, screens };
}

/** A product page for row `i`, for the tests that open a result. */
export const mockResultPage = (page: Page, i: number) => mockProductApi(page, { body: { ...product, id: screenerRow(i).id, title: screenerRow(i).title } });

export const savedScreen = (over: Partial<S["SavedScreen"]> = {}): S["SavedScreen"] => ({
  id: "5c0e7f1a-2b3d-4e5f-8a9b-0c1d2e3f4a5b",
  name: "Early & profitable",
  filters: { margin_bps_min: 4000, lifecycle: ["emerging", "rising"] },
  sort: "margin_bps",
  order: "desc",
  columns: null,
  version: 1,
  created_at: NOW.toISOString(),
  ...over,
});
