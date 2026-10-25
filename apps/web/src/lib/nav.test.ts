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

  test("hrefs are unique; Phase 1 builds Data Health on Phase 0, and UX-2, UX-1 and UX-10 ship Discover, Matching and Settings in Phase 2, P2-29 Google popular", () => {
    const hrefs = allNavItems.map((i) => i.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
    expect(allNavItems.filter(isBuilt).map((i) => i.href)).toEqual(["/", "/discover", "/google-popular", "/admin/data-health", "/admin/matching", "/admin/ui", "/settings"]);
    expect(resolveRoute("/admin/ui")).toMatchObject({ group: "Admin", item: { label: "UI gallery" } });
  });

  // imp-001: the coming-soon pages, the palette hints and the phase progress bar all read this one constant.
  test("the build is in Phase 1", () => {
    expect(CURRENT_PHASE).toBe(1);
  });
});
