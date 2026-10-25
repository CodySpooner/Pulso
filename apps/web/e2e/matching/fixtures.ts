import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { healthySources, mockAdminApi, NOW, problem } from "../data-health/fixtures";

// Fixture /v1/admin/matching responses for the Matching Queue e2e tests and screenshots, never a database restore.
// The mock keeps decisions like the API: a decided pair leaves the queue, and an undo puts it back.

type S = components["schemas"];
const at = (daysAgo: number) => new Date(NOW.getTime() - daysAgo * 86_400_000).toISOString();
const THINGS = ["Sunset projection lamp", "Galaxy star projector", "Magnetic phone mount", "Posture corrector", "Mini waffle maker", "Cloud slides", "Pet hair remover roller", "LED strip lights"];
const COLORS = ["#d97706", "#7c3aed", "#0891b2", "#16a34a", "#db2777", "#2563eb", "#ca8a04", "#dc2626"];
export const thresholds: S["Thresholds"] = {
  version: "m3-3f9a1c2e7b40",
  auto_link: 0.9,
  queue: 0.75,
  image_weight: 0.55,
  title_weight: 0.3,
  phash_weight: 0.15,
  markup_low: 1.2,
  markup_high: 8,
};
const PRODUCT = (i: number, side: string) => `0b1c2d3e-0000-4000-8000-${String(i * 10 + (side === "a" ? 1 : 2)).padStart(12, "0")}`;
export const title = (i: number, side: "a" | "b") => `${THINGS[i % THINGS.length]} ${side === "a" ? "· USB, 16 colours" : "for bedroom (CJ)"} #${i}`;

/** Pair i: a Shopify listing (side a) and a CJ listing (side b). Every 5th has two products (merge), every 7th
 *  a three-listing product on side a (split). Scores fall from 0.89 so the default sort is stable. */
export function item(i: number): S["QueueItem"] {
  return {
    id: 1000 + i,
    score: Math.round((0.89 - (i % 14) * 0.01) * 100) / 100,
    scorer_version: i % 6 === 5 ? "gtin-1" : thresholds.version,
    created_at: at(1 + (i % 9)),
    impact: i % 4 === 0,
    a: { listing_id: 2 * i + 1, title: title(i, "a"), source: "shopify_stores", image_url: `https://cdn.example.test/m/${i}-a-0.svg`, product_id: i % 5 === 0 || i % 7 === 0 ? PRODUCT(i, "a") : null },
    b: { listing_id: 2 * i + 2, title: title(i, "b"), source: "cj", image_url: `https://cdn.example.test/m/${i}-b-0.svg`, product_id: i % 5 === 0 ? PRODUCT(i, "b") : null },
  };
}

function member(i: number, n: number): S["Member"] {
  return { listing_id: 50_000 + i * 10 + n, title: `${THINGS[(i + n) % THINGS.length]} (store ${n})`, source: "shopify_stores", vendor: `store${n}.example`, image_url: `https://cdn.example.test/m/${i}-m${n}.svg` };
}

export function detail(i: number, over: Partial<S["CandidateDetail"]> = {}): S["CandidateDetail"] {
  const row = item(i);
  const side = (key: "a" | "b"): S["ListingDetail"] => {
    const cj = key === "b";
    const images = Array.from({ length: cj ? 4 : 2 }, (_, n) => `https://cdn.example.test/m/${i}-${key}-${n}.svg`);
    return {
      id: row[key].listing_id,
      title: row[key].title,
      url: `https://example.test/${key}/${i}`,
      source: row[key].source,
      source_name: cj ? "CJ Dropshipping" : "Shopify stores",
      vendor: cj ? "CJ supplier 4412" : "glowhaus.example",
      vendor_kind: cj ? "supplier" : "store",
      images,
      price: { min_minor: cj ? 642 : 2999, max_minor: cj ? 642 : 3499, currency: "USD", captured_at: at(0.2) },
      variants: cj ? 6 : 3,
      first_seen_at: at(cj ? 30 : 12),
      delisted_at: null,
      product_id: row[key].product_id,
    };
  };
  const clusters: S["Cluster"][] = [];
  if (row.a.product_id)
    clusters.push({
      product_id: row.a.product_id,
      name: THINGS[i % THINGS.length],
      first_seen_at: at(40),
      listings: i % 7 === 0 ? 3 : 2,
      members: Array.from({ length: i % 7 === 0 ? 3 : 2 }, (_, n) => member(i, n)),
      notes: 2,
      tags: 1,
    });
  if (row.b.product_id)
    clusters.push({ product_id: row.b.product_id, name: `${THINGS[i % THINGS.length]} (CJ)`, first_seen_at: at(20), listings: 1, members: [member(i, 9)], notes: 0, tags: 0 });
  return {
    id: row.id,
    status: "pending",
    superseded: false,
    score: row.score,
    scorer_version: row.scorer_version,
    image_cos: Math.min(1, row.score + 0.04),
    title_cos: Math.round((row.score - 0.08) * 100) / 100,
    phash_sim: 0.8594,
    price_sane: i % 3 !== 2,
    created_at: row.created_at,
    a: side("a"),
    b: side("b"),
    clusters,
    thresholds,
    ...over,
  };
}

export const summary: S["QueueSummary"] = {
  pending: 0,
  stored_sources: ["cj", "shopify_stores"],
  auto_linked: 412,
  last_auto_link_at: at(0.45),
  matcher_enabled: true,
};

const svg = (fill: string) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><rect width="120" height="120" fill="#1f2125"/><circle cx="60" cy="52" r="26" fill="${fill}"/><rect x="34" y="84" width="52" height="10" rx="5" fill="${fill}" opacity=".55"/></svg>`;

export interface MatchingMock {
  count?: number;
  /** GET candidates never answers: the skeletons stay. */
  hold?: boolean;
  /** GET candidates answers with this problem status. */
  status?: number;
  /** Pairs whose detail fails (503). */
  failDetail?: number[];
  /** Pairs whose detail says superseded. */
  superseded?: number[];
  /** Pairs whose images fail to load. */
  brokenImages?: number[];
  /** Pairs with no stored image on side A, so the image components are missing. */
  noImages?: number[];
  summary?: Partial<S["QueueSummary"]>;
}

export async function mockMatchingApi(page: Page, options: MatchingMock = {}) {
  const all = Array.from({ length: options.count ?? 24 }, (_, i) => item(i));
  const decided = new Map<number, number>(); // candidate → decision id
  const posts: Record<string, unknown>[] = [];
  const undos: number[] = [];
  let next = 9000;
  await mockAdminApi(page, { sources: healthySources });
  await page.route("https://cdn.example.test/**", (route) => {
    const name = new URL(route.request().url()).pathname.split("/").pop() ?? "";
    const i = Number.parseInt(name, 10);
    if (options.brokenImages?.includes(1000 + i)) return route.fulfill({ status: 404, body: "" });
    return route.fulfill({ contentType: "image/svg+xml", body: svg(COLORS[(i + name.length) % COLORS.length]) });
  });
  await page.route("**/api/v1/admin/matching/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api/, "");
    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body });
    if (request.method() === "GET" && path === "/v1/admin/matching/candidates") {
      if (options.hold) return;
      if (options.status) return route.fulfill({ status: options.status, contentType: "application/problem+json", json: problem(options.status, "e2e-matching") });
      const open = all.filter((row) => !decided.has(row.id));
      // Keyset like the API: the cursor is the last id served, so decisions never shift a page.
      const after = Number(url.searchParams.get("cursor") ?? 0);
      const limit = Number(url.searchParams.get("limit") ?? 50);
      const version = url.searchParams.get("version");
      const rows = open.filter((row) => row.id > after && (!version || row.scorer_version === version));
      const page = rows.slice(0, limit);
      return json({
        items: page,
        next_cursor: rows.length > limit ? String(page.at(-1)!.id) : null,
        summary: { ...summary, pending: open.length, ...options.summary },
        facets: { source_pairs: all.length ? ["cj+shopify_stores"] : [], versions: [...new Set(all.map((row) => row.scorer_version))].sort() },
        thresholds,
      } satisfies S["QueuePage"]);
    }
    const one = path.match(/^\/v1\/admin\/matching\/candidates\/(\d+)$/);
    if (one) {
      const id = Number(one[1]);
      if (options.failDetail?.includes(id)) return route.fulfill({ status: 503, contentType: "application/problem+json", json: problem(503, "e2e-detail") });
      const found = detail(id - 1000, { superseded: options.superseded?.includes(id) ?? false });
      if (options.noImages?.includes(id)) Object.assign(found, { a: { ...found.a, images: [] }, image_cos: null, phash_sim: null });
      return json(found);
    }
    if (request.method() === "POST" && path === "/v1/admin/matching/decisions") {
      const body = request.postDataJSON() as Record<string, unknown>;
      posts.push(body);
      const id = next++;
      if (typeof body.candidate_id === "number") decided.set(body.candidate_id, id);
      const pair = typeof body.candidate_id === "number" ? item(body.candidate_id - 1000) : null;
      return json(
        {
          id,
          action: String(body.action),
          product_id: body.action === "reject" || body.action === "unlink" ? null : String(body.into ?? pair?.a.product_id ?? PRODUCT(0, "a")),
          listing_ids: pair ? [pair.a.listing_id, pair.b.listing_id] : ((body.listing_ids as number[]) ?? []),
          decided_at: NOW.toISOString(),
        } satisfies S["Decision"],
        201,
      );
    }
    const undo = path.match(/^\/v1\/admin\/matching\/decisions\/(\d+)\/undo$/);
    if (request.method() === "POST" && undo) {
      const id = Number(undo[1]);
      undos.push(id);
      for (const [candidate, decision] of decided) if (decision === id) decided.delete(candidate);
      return json({ id: next++, action: "undo", product_id: null, listing_ids: [], decided_at: NOW.toISOString() } satisfies S["Decision"], 201);
    }
    return json(problem(404, "e2e-matching-404"), 404);
  });
  return { posts, undos, all, failLists: (status = 503) => (options.status = status) };
}
