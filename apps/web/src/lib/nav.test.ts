import { describe, expect, test } from "vitest";

import { allNavItems, CURRENT_PHASE, isBuilt, resolveRoute } from "./nav";

// SPEC §10 routes (dynamic segments filled with an example id).
const SPEC_ROUTES = [
  "/", "/discover", "/screener", "/products/123", "/compare", "/stores", "/stores/abc", "/ads", "/niches",
  "/calendar", "/watchlists", "/boards", "/alerts", "/testing", "/studio", "/ask", "/profit", "/track-record",
  "/admin/data-health", "/admin/matching", "/settings",
];

describe("nav config", () => {
  test.each(SPEC_ROUTES)("covers %s", (path) => {
    expect(resolveRoute(path)).toBeDefined();
  });

  test("detail routes highlight their parent", () => {
    expect(resolveRoute("/products/123")).toMatchObject({ activeHref: "/discover", group: "Discover", detail: "Product" });
    expect(resolveRoute("/stores/abc")).toMatchObject({ activeHref: "/stores", detail: "Store" });
    expect(resolveRoute("/discover/")?.item.href).toBe("/discover");
  });

  test("unknown paths do not resolve", () => {
    for (const path of ["/nope", "/products", "/products/1/extra", "/admin"]) expect(resolveRoute(path)).toBeUndefined();
  });

  test("hrefs are unique; Phase 1 builds Data Health on Phase 0, and UX-2, UX-1 and UX-10 ship Discover, Matching and Settings in Phase 2, P2-29 Google popular, AMZ-1b Amazon ranks", () => {
    const hrefs = allNavItems.map((i) => i.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
    expect(allNavItems.filter(isBuilt).map((i) => i.href)).toEqual(["/", "/discover", "/google-popular", "/amazon", "/admin/data-health", "/admin/matching", "/admin/ui", "/settings"]);
    expect(resolveRoute("/admin/ui")).toMatchObject({ group: "Admin", item: { label: "UI gallery" } });
  });

  // imp-001: the coming-soon pages, the palette hints and the phase progress bar all read this one constant.
  test("the build is in Phase 3", () => {
    expect(CURRENT_PHASE).toBe(3);
  });

  // DEC-284: the running phase's routes stay coming-soon until a task ships them.
  test("a route of the phase in progress is not built", () => {
    expect(isBuilt(resolveRoute("/stores")!.item)).toBe(false);
    expect(isBuilt(resolveRoute("/stores/abc")!.item)).toBe(false);
    expect(isBuilt({ phase: CURRENT_PHASE - 1 })).toBe(true);
  });

  // DEC-302 (a): the Shopify crawler stays off (DEC-261), so Store Spy has no source and stays unbuilt past Phase 3.
  test("a route with no source stays unbuilt after its phase, and its detail route says so too", () => {
    const stores = resolveRoute("/stores")!.item;
    expect(stores.noSource).toMatch(/Shopify store crawler stays off/);
    expect(resolveRoute("/stores/abc")!.item.noSource).toBe(stores.noSource);
    expect(isBuilt({ phase: CURRENT_PHASE - 1, noSource: stores.noSource })).toBe(false);
    expect(allNavItems.filter((i) => i.noSource).map((i) => i.href)).toEqual(["/stores"]);
  });
});
