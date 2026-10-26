import type { Page, Route } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { NOW, problem } from "../data-health/fixtures";
import { discoverItem, mockFeedApi } from "../products/fixtures";

// WF-2b: a stateful fixture of the watchlists API (DEC-314, DEC-322) over Discover's fixture products, for the e2e
// tests and screenshots, never a database restore. Writes change the store, so a reload reads them back.

type S = components["schemas"];
const at = (hoursAgo: number) => new Date(NOW.getTime() - hoursAgo * 3_600_000).toISOString();
export const MAIN = "a0000000-0000-4000-8000-000000000001";
export const PET = "a0000000-0000-4000-8000-000000000002";
/** A product added as "Glow lamp (old listing)", merged into product 12 since (DEC-314 d). */
export const MERGED_FROM = "b0000000-0000-4000-8000-000000000099";

interface Stored {
  list: string;
  product_id: string;
  name: string;
  added_at: string;
}
export interface WatchStore {
  lists: { id: string; name: string }[];
  items: Stored[];
}
export interface WatchMock {
  store?: WatchStore;
  /** Answer GET /v1/watchlists, or the items page, with this status; or never answer the items page. */
  listsStatus?: number;
  itemsStatus?: number;
  holdItems?: boolean;
}

export const CATALOG = Array.from({ length: 20 }, (_, i) => discoverItem(i));
const byId = new Map(CATALOG.map((p) => [p.id, p]));
const survivor = (id: string) => (id === MERGED_FROM ? CATALOG[12].id : id);

const DAY = 86_400_000;
const END = new Date(NOW.getTime() - DAY).toISOString().slice(0, 10); // yesterday: the newest closed UTC day
/** A row's 30-day velocity sparkline (imp-419). Product 5 has none (no source yet), 3 breaks for three days and once more,
 *  8 stops 3 days ago (stale) and 13 starts 9 days ago; the rest rise and dip on a wave. */
export function sparkOf(id: string): S["Spark"] | S["NoSource"] {
  const i = CATALOG.findIndex((p) => p.id === id);
  if (i === 5) return { value: null, reason: "No velocity in the last 30 days." };
  const missing = (back: number) => (i === 3 && ([17, 18, 19, 6].includes(back))) || (i === 8 && back < 3) || (i === 13 && back > 8);
  const points = Array.from({ length: 30 }, (_, n) => {
    const back = 29 - n;
    const day = new Date(Date.parse(END) - back * DAY).toISOString().slice(0, 10);
    return { day, value: missing(back) ? null : Math.round(20 + i * 3 + n * (1 + (i % 3)) + 9 * Math.sin((n + i) / 3)) };
  });
  const last = points.findLast((p) => p.value !== null)!;
  return {
    value: last.value!, source: "shopify_stores", source_name: "Shopify stores", as_of: new Date(Date.parse(last.day) + DAY).toISOString(),
    raw_payload_id: null, method: "Shopify updated_at bumps, a lower bound", stale: i === 8, family: "shp_bump", points,
  };
}

/** Main with products 0, 3, 5 (5 has no store yet: no source yet) and the merged one; Pet niche with 7; Q4 empty. */
export const watchStore = (): WatchStore => ({
  lists: [
    { id: MAIN, name: "Main" },
    { id: PET, name: "Pet niche" },
    { id: "a0000000-0000-4000-8000-000000000003", name: "Q4 gifts" },
  ],
  items: [
    ...[0, 3, 5].map((i, n) => ({ list: MAIN, product_id: CATALOG[i].id, name: CATALOG[i].title, added_at: at(24 * (n + 1)) })),
    { list: MAIN, product_id: MERGED_FROM, name: "Glow lamp (old listing)", added_at: at(24 * 6) },
    { list: PET, product_id: CATALOG[7].id, name: CATALOG[7].title, added_at: at(30) },
  ],
});

/** The shell, Discover's feed and the watchlists API on one store. Returns the store and every watchlist write. */
export async function mockWatchlistsApi(page: Page, options: WatchMock = {}) {
  const store = options.store ?? watchStore();
  const writes: { method: string; path: string; body: unknown }[] = [];
  const watch = (id: string) => {
    const lists = store.lists.filter((l) => store.items.some((i) => i.list === l.id && survivor(i.product_id) === id)).map((l) => l.id);
    return { watched: lists.includes(store.lists.find((l) => l.name === "Main")?.id ?? ""), watchlist_ids: lists };
  };
  const list = (l: WatchStore["lists"][number]): S["Watchlist"] => ({
    ...l, position: store.lists.indexOf(l), created_at: at(200), item_count: store.items.filter((i) => i.list === l.id).length,
  });
  await mockFeedApi(page, { items: CATALOG.map((p) => ({ ...p, ...watch(p.id) })) });
  const reply = (route: Route, json: unknown, status = 200) => route.fulfill({ status, json });
  const fail = (route: Route, status: number, code = "unavailable") =>
    route.fulfill({ status, contentType: "application/problem+json", json: { ...problem(status, `e2e-watch-${status}`), code } });
  const handle = async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const [, , , resource, id, part, sub] = url.pathname.split("/"); // /api/v1/{watchlists|products}/{id}/{part}/{sub}
    const method = request.method();
    const body = request.postDataJSON() as Record<string, unknown> | null;
    if (method !== "GET") writes.push({ method, path: url.pathname, body });
    if (resource === "products") {
      const product = survivor(id);
      let main = store.lists.find((l) => l.name === "Main");
      const held = store.items.find((i) => i.list === main?.id && survivor(i.product_id) === product);
      if (method === "DELETE") {
        store.items = store.items.filter((i) => i !== held);
        return reply(route, held ? { watchlist_id: main!.id, product_id: held.product_id, added_at: held.added_at } : null);
      }
      if (!main) store.lists.push((main = { id: crypto.randomUUID(), name: "Main" }));
      if (!held) store.items.push({ list: main.id, product_id: product, name: byId.get(product)?.title ?? "Fixture product", added_at: NOW.toISOString() });
      return reply(route, { watchlist_id: main.id, product_id: product, added_at: (held ?? store.items.at(-1)!).added_at });
    }
    const target = store.lists.find((l) => l.id === id);
    if (!id) {
      if (method === "POST") {
        const name = String(body?.name).trim();
        if (store.lists.some((l) => l.name === name)) return fail(route, 409, "conflict");
        store.lists.push({ id: crypto.randomUUID(), name });
        return reply(route, list(store.lists.at(-1)!), 201);
      }
      if (options.listsStatus) return fail(route, options.listsStatus);
      return reply(route, store.lists.map(list));
    }
    if (!target) return fail(route, 404, "not_found");
    if (!part) {
      if (method === "PATCH") target.name = String(body?.name).trim();
      if (method === "DELETE") {
        const was = list(target);
        store.lists = store.lists.filter((l) => l !== target);
        store.items = store.items.filter((i) => i.list !== id);
        return reply(route, was);
      }
      return reply(route, list(target));
    }
    if (method === "GET") {
      if (options.holdItems) return;
      if (options.itemsStatus) return fail(route, options.itemsStatus);
      const rows = store.items
        .filter((i) => i.list === id)
        .sort((a, b) => b.added_at.localeCompare(a.added_at))
        .map((i) => ({ product_id: i.product_id, name: i.name, added_at: i.added_at, image_url: null, product: { ...byId.get(survivor(i.product_id))!, ...watch(survivor(i.product_id)) }, ...(url.searchParams.get("spark") === "velocity" && { spark: sparkOf(survivor(i.product_id)) }) }));
      return reply(route, { items: rows, next_cursor: null });
    }
    const ids = (body?.product_ids as string[] | undefined) ?? [];
    if (method === "DELETE") {
      store.items = store.items.filter((i) => !(i.list === id && i.product_id === sub));
    } else if (sub === "move") {
      for (const i of store.items) if (i.list === id && ids.includes(i.product_id)) i.list = String(body?.to);
    } else {
      for (const p of ids) if (!store.items.some((i) => i.list === id && i.product_id === p)) store.items.push({ list: id, product_id: p, name: byId.get(p)?.title ?? "Fixture product", added_at: NOW.toISOString() });
    }
    return reply(route, list(store.lists.find((l) => l.id === (sub === "move" ? body?.to : id))!));
  };
  await page.route(/\/api\/v1\/(watchlists|products\/[^/]+\/watch)(\/|\?|$)/, handle);
  return { store, writes };
}
