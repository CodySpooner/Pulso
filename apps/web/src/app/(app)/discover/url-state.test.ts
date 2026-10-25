import { describe, expect, test } from "vitest";

import { activeFilters, apiQuery, feedSearch, joinPages, NO_FILTERS, parseFeed, readView, saveView, type FeedState } from "./url-state";

const parse = (search: string) => parseFeed(new URLSearchParams(search));
const DEFAULT: FeedState = { view: null, sort: "momentum", ...NO_FILTERS };

describe("Discover URL state", () => {
  test("a clean URL is the default feed, and the default writes a clean URL", () => {
    expect(parse("")).toEqual(DEFAULT);
    expect(feedSearch(DEFAULT)).toBe("");
  });

  test.each([
    "view=table",
    "view=grid&sort=newest",
    "sort=fewest_sellers&category=7&price_min=20&price_max=60",
    "source=cj&first_seen_days=30&has_sellers=false",
    "view=table&sort=newest&category=503&price_min=0&source=shopify_stores&first_seen_days=7&has_sellers=true",
  ])("%s round-trips", (search) => {
    const state = parse(search);
    expect(feedSearch(state)).toBe(search);
    expect(parse(feedSearch(state))).toEqual(state);
  });

  test("unknown or malformed values fall back to the default", () => {
    expect(parse("view=list&sort=trend&category=abc&price_min=-5&price_max=1e3&source=amazon&first_seen_days=14&has_sellers=yes")).toEqual(DEFAULT);
    expect(parse("category=0").category).toBeNull();
  });

  test("the API gets minor units and no nulls; filters count without sort or view", () => {
    const state = parse("view=table&sort=newest&price_min=20&has_sellers=false");
    expect(apiQuery(state)).toEqual({ sort: "newest", price_min: 2000, has_sellers: false });
    expect(activeFilters(state)).toEqual(["price_min", "has_sellers"]);
  });
});

describe("remembered view", () => {
  test("saves and reads back the viewer's choice", () => {
    const store = new Map<string, string>();
    const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) };
    expect(readView(storage)).toBeNull();
    saveView("table", storage);
    expect(readView(storage)).toBe("table");
    store.set("pulso.discover.view", "list");
    expect(readView(storage)).toBeNull();
  });

  test("storage that throws never breaks the page", () => {
    const blocked = {
      getItem: () => {
        throw new DOMException("denied", "SecurityError");
      },
      setItem: () => {
        throw new DOMException("full", "QuotaExceededError");
      },
    };
    expect(readView(blocked)).toBeNull();
    expect(() => saveView("grid", blocked)).not.toThrow();
  });
});

describe("joined pages", () => {
  test("XR-19: a product that moved into a later page between loads renders once, at its first place", () => {
    const pages = [{ items: [{ id: "p", n: 1 }, { id: "q", n: 1 }] }, { items: [{ id: "q", n: 2 }, { id: "r", n: 1 }] }];
    expect(joinPages(pages)).toEqual([{ id: "p", n: 1 }, { id: "q", n: 1 }, { id: "r", n: 1 }]);
    expect(joinPages(undefined)).toEqual([]);
  });
});
