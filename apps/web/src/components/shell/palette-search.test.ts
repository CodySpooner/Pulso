import { describe, expect, test } from "vitest";

import { announce, searchView, type SearchResults } from "./palette-search";

const none: SearchResults = { products: [], stores: [], suppliers: [], catalog_empty: false };
const hits: SearchResults = {
  ...none,
  stores: [
    {
      id: 7, domain: "glowbeam.example.test", myshopify_domain: null, last_crawled_at: null, stale: false, top_product_id: null,
      match: { field: "domain", text: "glowbeam.example.test", kind: "prefix" },
    },
  ],
};
const settled = { isError: false, isFetching: false, isPlaceholderData: false };

describe("searchView", () => {
  test("under 2 characters the palette shows commands only", () => {
    expect(searchView("g", "g", { ...settled, data: hits })).toEqual({ kind: "off" });
  });

  test("the first query loads until its answer, through the debounce", () => {
    expect(searchView("gl", "g", settled)).toEqual({ kind: "loading" }); // still debouncing
    expect(searchView("gl", "gl", { ...settled, isFetching: true })).toEqual({ kind: "loading" });
    expect(searchView("gl", "gl", { ...settled, data: hits })).toEqual({ kind: "results", results: hits, stale: false });
  });

  test("results for an earlier query stay, marked stale, while a newer one loads", () => {
    expect(searchView("glow", "glo", { ...settled, data: hits })).toMatchObject({ kind: "results", stale: true });
    expect(searchView("glow", "glow", { ...settled, data: hits, isFetching: true, isPlaceholderData: true })).toMatchObject({ stale: true });
  });

  test("no matches is empty, or no source yet when nothing has been collected", () => {
    expect(searchView("zz", "zz", { ...settled, data: none })).toEqual({ kind: "empty" });
    expect(searchView("zz", "zz", { ...settled, data: { ...none, catalog_empty: true } })).toEqual({ kind: "no-source" });
    // An empty answer for an earlier query never claims the new one has no matches.
    expect(searchView("zzz", "zz", { ...settled, data: none })).toEqual({ kind: "loading" });
  });

  test("a failed search is an error once settled, and typing again loads", () => {
    expect(searchView("gl", "gl", { ...settled, isError: true })).toEqual({ kind: "error" });
    expect(searchView("gl", "gl", { ...settled, isError: true, isFetching: true })).toEqual({ kind: "loading" }); // retrying
    expect(searchView("glo", "gl", { ...settled, isError: true })).toEqual({ kind: "loading" });
    // A failed refresh of the same query keeps its results.
    expect(searchView("gl", "gl", { ...settled, isError: true, data: hits })).toMatchObject({ kind: "results" });
  });
});

describe("announce", () => {
  test("settled states are announced; loading and stale results are not", () => {
    const products = [{ id: "p", title: "Lamp", category: null, match: { field: "title" as const, text: "Lamp", kind: "exact" as const } }];
    expect(announce({ kind: "results", results: { ...hits, products: [...products, ...products] }, stale: false }, "la")).toBe(
      "2 products and 1 store for “la”",
    );
    expect(announce({ kind: "results", results: hits, stale: true }, "la")).toBe("");
    expect(announce({ kind: "loading" }, "la")).toBe("");
    expect(announce({ kind: "empty" }, "zz")).toBe("No products, stores or suppliers match “zz”");
    expect(announce({ kind: "error" }, "zz")).toBe("Search unavailable. Commands still work.");
  });
});
