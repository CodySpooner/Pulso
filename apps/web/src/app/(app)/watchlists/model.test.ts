import { QueryClient } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { applyWatch, isMerged, listed, patchWatch, pickList, sparkGaps, sparkLabel, undoWindow, type List, type Removal, type Spark } from "./model";

const product = (id: string, watched = false, watchlist_ids: string[] = []) => ({ id, title: id, watched, watchlist_ids });
const list = (id: string, name: string): List => ({ id, name, position: 0, created_at: "2026-10-25T00:00:00Z", item_count: 0 });

describe("undoWindow", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());
  const setup = () => {
    const sent: Removal[] = [];
    const shown: (Removal | null)[] = [];
    return { sent, shown, window: undoWindow((r) => sent.push(r), (r) => shown.push(r)) };
  };
  const removal = (id: string): Removal => ({ list: "main", ids: [id], text: `Removed ${id}` });

  it("hides at once and commits after 5 seconds", () => {
    const { sent, shown, window } = setup();
    window.remove(removal("a"));
    expect(shown).toEqual([removal("a")]);
    vi.advanceTimersByTime(4999);
    expect(sent).toEqual([]);
    vi.advanceTimersByTime(1);
    expect(sent).toEqual([removal("a")]);
    expect(shown.at(-1)).toBeNull();
  });

  it("an undo inside the window sends nothing, ever", () => {
    const { sent, shown, window } = setup();
    window.remove(removal("a"));
    vi.advanceTimersByTime(4000);
    window.undo();
    vi.advanceTimersByTime(10_000);
    expect(sent).toEqual([]);
    expect(shown).toEqual([removal("a"), null]);
    window.undo(); // nothing pending: a no-op
    expect(shown).toHaveLength(2);
  });

  it("a second removal commits the first; leaving the page commits the second", () => {
    const { sent, window } = setup();
    window.remove(removal("a"));
    window.remove(removal("b"));
    expect(sent).toEqual([removal("a")]);
    window.flush();
    expect(sent).toEqual([removal("a"), removal("b")]);
    vi.advanceTimersByTime(10_000);
    expect(sent).toHaveLength(2); // the timers were cleared
  });
});

describe("patchWatch", () => {
  it("stars the product in a Discover feed, a product header and a watchlist row alike", () => {
    const feed = { pages: [{ items: [product("p1"), product("p2")], next_cursor: null }], pageParams: [null] };
    const next = patchWatch(feed, "p2", () => ({ watched: true, watchlist_ids: ["main"] }));
    expect(next.pages[0].items[1]).toEqual(product("p2", true, ["main"]));
    expect(next.pages[0].items[0]).toBe(feed.pages[0].items[0]); // untouched rows keep their identity
    expect(patchWatch(product("p2"), "p2", listed("main", true, true))).toEqual(product("p2", true, ["main"]));
    const page = { items: [{ product_id: "old", product: product("p2", false, ["pet"]) }] };
    expect(patchWatch(page, "p2", listed("main", true, true)).items[0].product).toEqual(product("p2", true, ["pet", "main"]));
  });

  it("returns the same object when nothing changes", () => {
    const feed = { items: [product("p1", true, ["main"])] };
    expect(patchWatch(feed, "p1", listed("main", true, true))).toBe(feed);
    expect(patchWatch(feed, "other", listed("main", false, true))).toBe(feed);
  });

  it("a list other than Main leaves the star as it is", () => {
    expect(patchWatch(product("p1", true, ["main", "pet"]), "p1", listed("pet", false, false))).toEqual(product("p1", true, ["main"]));
  });
});

describe("applyWatch", () => {
  it("optimistically stars every cached read and keeps each one's fetch time", () => {
    const client = new QueryClient();
    client.setQueryData(["get", "/v1/products/{product_id}", { id: "p1" }], product("p1"), { updatedAt: 1000 });
    client.setQueryData(["get", "/v1/products", {}], { pages: [{ items: [product("p1"), product("p2")] }] }, { updatedAt: 2000 });
    client.setQueryData(["get", "/v1/watchlists", {}], [list("main", "Main")], { updatedAt: 3000 });
    applyWatch(client, "p1", (w) => ({ ...w, watched: true }));
    const header = client.getQueryState(["get", "/v1/products/{product_id}", { id: "p1" }]);
    expect(header?.data).toEqual(product("p1", true));
    expect(header?.dataUpdatedAt).toBe(1000);
    const feed = client.getQueryState<{ pages: { items: ReturnType<typeof product>[] }[] }>(["get", "/v1/products", {}]);
    expect(feed?.data?.pages[0].items.map((p) => p.watched)).toEqual([true, false]);
    expect(feed?.dataUpdatedAt).toBe(2000);
    // A rollback is the same patch with the old value.
    applyWatch(client, "p1", (w) => ({ ...w, watched: false }));
    expect(client.getQueryData(["get", "/v1/products/{product_id}", { id: "p1" }])).toEqual(product("p1"));
  });
});

describe("the merged note and the list shown", () => {
  it("flags an item whose product now reads as another", () => {
    expect(isMerged({ product_id: "old", product: { ...product("survivor") } as never })).toBe(true);
    expect(isMerged({ product_id: "p1", product: { ...product("p1") } as never })).toBe(false);
  });

  it("shows the URL's list, else Main, else the first", () => {
    const lists = [list("q4", "Q4"), list("main", "Main")];
    expect(pickList(lists, "q4")?.id).toBe("q4");
    expect(pickList(lists, "gone")?.id).toBe("main");
    expect(pickList([list("q4", "Q4")], null)?.id).toBe("q4");
    expect(pickList([], null)).toBeUndefined();
    expect(pickList(undefined, "q4")).toBeUndefined();
  });
});

describe("sparkline words (imp-419)", () => {
  const points = (values: (number | null)[]) => values.map((value, i) => ({ day: `2026-10-${String(i + 1).padStart(2, "0")}`, value }));
  const spark = (values: (number | null)[]): Spark => ({
    value: 1, source: "shopify_stores", source_name: "Shopify stores", as_of: "2026-10-22T00:00:00Z", raw_payload_id: null, method: null, stale: false, family: "shp_inv", points: points(values),
  });

  it("names each run of days without a value after the first value; days before it aren't gaps", () => {
    expect(sparkGaps(points([null, null, 4, null, null, null, 5, null, 6, null]))).toEqual(["Oct 4 → Oct 6", "Oct 8", "Oct 10"]);
    expect(sparkGaps(points([null, 3, 4]))).toEqual([]);
  });

  it("says the first and last values and where the line breaks", () => {
    expect(sparkLabel(spark([12.4, null, 1033.6]))).toBe("Velocity, last 3 days: 12/7d to 1,034/7d, no data Oct 2");
    expect(sparkLabel(spark([null, 7]))).toBe("Velocity, last 2 days: 7/7d");
  });
});
