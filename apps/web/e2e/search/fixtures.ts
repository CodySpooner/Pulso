import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { NOW, problem } from "../data-health/fixtures";
import { mockProductApi, PRODUCT_ID } from "../products/fixtures";

// p2-16 (UX-9): fixture GET /v1/search answers for the palette's search e2e tests and screenshots, never a database
// restore. The mock filters these rows by substring, as the API's ranked match would for these queries.

type S = components["schemas"];
const at = (hoursAgo: number) => new Date(NOW.getTime() - hoursAgo * 3_600_000).toISOString();
const id = (n: number) => `5e2c0d41-0000-4000-8000-${String(n).padStart(12, "0")}`;

export const products: S["ProductHit"][] = [
  {
    id: id(1), title: "Glow-in-the-dark star projector", category: "Home & Garden > Lighting > Night Lights",
    match: { field: "title", text: "Glow-in-the-dark star projector", kind: "prefix" },
  },
  {
    id: PRODUCT_ID, title: "Sunset projection lamp with 16 colour modes and remote", category: "Home & Garden > Lighting > Lamps",
    match: { field: "listing_title", text: "Glow sunset lamp, 16 colours", kind: "prefix" },
  },
  {
    id: id(3), title: "LED glow face mask", category: "Health & Beauty > Personal Care",
    match: { field: "title", text: "LED glow face mask", kind: "substring" },
  },
];

export const stores: S["StoreHit"][] = [
  {
    id: 4101, domain: "glowbeam.example.test", myshopify_domain: "glowbeam-dev.myshopify.com", last_crawled_at: at(6), stale: false,
    top_product_id: PRODUCT_ID, match: { field: "domain", text: "glowbeam.example.test", kind: "prefix" },
  },
  {
    id: 4102, domain: "nightglow.example.test", myshopify_domain: "glowhaus-store.myshopify.com", last_crawled_at: at(74), stale: true,
    top_product_id: id(1), match: { field: "domain", text: "nightglow.example.test", kind: "substring" },
  },
  {
    id: 4103, domain: "glowlane.example.test", myshopify_domain: null, last_crawled_at: null, stale: false, top_product_id: null,
    match: { field: "domain", text: "glowlane.example.test", kind: "prefix" },
  },
];

export const suppliers: S["SupplierHit"][] = [
  { id: 88, name: "Shenzhen Glowtech Co.", platform: "cj", top_product_id: PRODUCT_ID, match: { field: "name", text: "Shenzhen Glowtech Co.", kind: "prefix" } },
  { id: 89, name: "Glow Supply Trading", platform: "cj", top_product_id: null, match: { field: "name", text: "Glow Supply Trading", kind: "prefix" } },
];

export interface SearchMock {
  /** Answer the first `failures` requests with a 503 problem (the palette retries once). */
  failures?: number;
  /** Queries that never get an answer. */
  hold?: string[];
  /** Nothing collected yet: every answer is empty with `catalog_empty`. */
  catalogEmpty?: boolean;
}

/** The product page's and the shell's calls, plus GET /v1/search. Returns each search's `q`, in order. */
export async function mockSearchApi(page: Page, options: SearchMock = {}): Promise<string[]> {
  const queries: string[] = [];
  let failures = options.failures ?? 0;
  await mockProductApi(page);
  await page.route(
    (url) => url.pathname === "/api/v1/search",
    async (route) => {
      const q = new URL(route.request().url()).searchParams.get("q") ?? "";
      queries.push(q);
      if (options.hold?.includes(q)) return;
      if (failures > 0) {
        failures -= 1;
        return route.fulfill({ status: 503, contentType: "application/problem+json", json: problem(503, "e2e-search-503") });
      }
      const has = (text: string) => !options.catalogEmpty && text.toLowerCase().includes(q.toLowerCase());
      const body: S["SearchResults"] = {
        products: products.filter((p) => has(p.title) || has(p.match.text)),
        stores: stores.filter((s) => has(s.domain) || has(s.myshopify_domain ?? "")),
        suppliers: suppliers.filter((s) => has(s.name)),
        catalog_empty: !!options.catalogEmpty,
      };
      return route.fulfill({ json: body });
    },
  );
  return queries;
}

/** Opens the palette with Ctrl+K from Daily Pulse and returns its input. */
export async function openPalette(page: Page) {
  await page.goto("/");
  await page.locator("html[data-app-ready=true]").waitFor();
  await page.keyboard.press("Control+K");
  return page.getByRole("combobox");
}
