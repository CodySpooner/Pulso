import { describe, expect, test } from "vitest";

import { allNavItems, isBuilt, resolveRoute } from "./nav";

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

  test("hrefs are unique and only Daily Pulse and the UI gallery are built in Phase 0", () => {
    const hrefs = allNavItems.map((i) => i.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
    expect(allNavItems.filter(isBuilt).map((i) => i.href)).toEqual(["/", "/admin/ui"]);
    expect(resolveRoute("/admin/ui")).toMatchObject({ group: "Admin", item: { label: "UI gallery" } });
  });
});
