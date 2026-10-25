import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { healthySources, mockAdminApi, NOW, problem } from "../data-health/fixtures";

// Fixture /v1/boards for the Boards e2e tests and screenshots, never a database restore. The mock keeps writes like
// the API (DEC-319): names unique per workspace (archived included, 409), every write bumps updated_at, adds append,
// a move renumbers 0…n−1, cards page by [position, product_id], and send-to-testing skips products with an open test.

type S = components["schemas"];
type Board = Omit<S["Board"], "item_count">;
type Item = S["BoardItem"];
const at = (hours: number) => new Date(NOW.getTime() - hours * 3_600_000).toISOString();
const COLORS = ["#d97706", "#7c3aed", "#0891b2", "#16a34a", "#db2777", "#2563eb", "#ca8a04"];
const svg = (fill: string) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 120"><rect width="160" height="120" fill="#1f2125"/><circle cx="80" cy="54" r="28" fill="${fill}"/><rect x="48" y="90" width="64" height="10" rx="5" fill="${fill}" opacity=".55"/></svg>`;
export const BOARD = (n: number) => `b0a4d000-0000-4000-8000-${String(n).padStart(12, "0")}`;
export const PRODUCT = (n: number) => `5e7a0c11-0000-4000-8000-${String(n).padStart(12, "0")}`;
/** A product with an open test: send-to-testing skips it. */
export const OPEN_TEST = PRODUCT(3);

const NAMES = ["", "Sunset projection lamp", "Magnetic car phone mount", "Posture corrector brace", "Galaxy star projector", "Mini waffle maker", "Cloud pillow slides", "Pet hair remover roller", "Self-cleaning slicker brush", "Collapsible dog bowl", "LED bottle cap light"];
const card = (n: number, position: number, over: Partial<Item> = {}): Item => ({
  product_id: PRODUCT(n),
  name: NAMES[n],
  image_url: `https://cdn.example.test/b/${n}.svg`,
  position,
  note: null,
  added_at: at(30 + n * 5),
  ...over,
});

export function fixtureBoards(): { boards: Board[]; items: Record<string, Item[]> } {
  const board = (n: number, name: string, hours: number, over: Partial<Board> = {}): Board => ({ id: BOARD(n), name, description: null, archived_at: null, created_at: at(400), updated_at: at(hours), ...over });
  return {
    boards: [
      board(1, "Q4 gift ideas", 2, { description: "Under $40, giftable, ships before Dec 10." }),
      board(2, "Pet niche", 26),
      board(3, "Bundles to test", 75),
      board(4, "Kitchen gadgets", 120),
      board(5, "Summer 2026", 900, { archived_at: at(500) }),
    ],
    items: {
      [BOARD(1)]: [
        card(1, 0, { note: "Best hook so far: sunset vibes for bedrooms. Check the 3-pack price." }),
        card(4, 1),
        card(5, 3, { note: "Holiday breakfast angle." }), // a gap at 2: a removal left it (DEC-319 b)
        card(6, 4),
        card(3, 5, { image_url: null }),
      ],
      [BOARD(2)]: [card(7, 0), card(8, 1, { note: "Pairs with the roller as a bundle." }), card(9, 2)],
      [BOARD(3)]: [card(10, 0, { image_url: null })],
      [BOARD(4)]: [],
      [BOARD(5)]: [card(2, 0), card(5, 1)],
    },
  };
}

export interface BoardsMock {
  boards?: Board[];
  items?: Record<string, Item[]>;
  /** GET /v1/boards never answers: the skeletons stay. */
  hold?: boolean;
  /** GET /v1/boards answers with this problem status. */
  status?: number;
  /** GET …/items answers with this problem status. */
  itemsStatus?: number;
  /** A note PATCH answers 503. */
  failNotes?: boolean;
  /** A move PATCH answers 503. */
  failMoves?: boolean;
}

export async function mockBoardsApi(page: Page, options: BoardsMock = {}) {
  const data = fixtureBoards();
  const boards = options.boards ?? data.boards;
  const items = options.items ?? data.items;
  const calls: { method: string; path: string; body: unknown }[] = [];
  let made = 100;
  await mockAdminApi(page, { sources: healthySources });
  await page.route("https://cdn.example.test/b/**", (route) => {
    const n = Number.parseInt(new URL(route.request().url()).pathname.split("/").pop()!, 10);
    return route.fulfill({ contentType: "image/svg+xml", body: svg(COLORS[n % COLORS.length]) });
  });
  const out = (b: Board): S["Board"] => ({ ...b, item_count: (items[b.id] ?? []).length });
  const bump = (b: Board) => (b.updated_at = NOW.toISOString());
  const sorted = (id: string) => (items[id] ?? []).sort((a, b) => a.position - b.position || a.product_id.localeCompare(b.product_id));

  await page.route("**/api/v1/boards**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api/, "");
    const method = request.method();
    const body = request.postDataJSON() as Record<string, unknown> | null;
    calls.push({ method, path, body });
    const json = (value: unknown, status = 200) => route.fulfill({ status, json: value });
    const fail = (status: number, code: string, detail: string) => route.fulfill({ status, contentType: "application/problem+json", json: { ...problem(status, `e2e-boards-${code}`), code, detail } });
    const taken = (name: string, except?: string) => boards.some((b) => b.name === name && b.id !== except);

    if (path === "/v1/boards" && method === "GET") {
      if (options.hold) return;
      if (options.status) return fail(options.status, "unavailable", "The API is restarting. Try again.");
      const archived = url.searchParams.get("archived") === "true";
      return json(boards.filter((b) => (b.archived_at != null) === archived).sort((a, b) => b.updated_at.localeCompare(a.updated_at)).map(out));
    }
    if (path === "/v1/boards" && method === "POST") {
      const name = String(body!.name).trim();
      if (taken(name)) return fail(409, "conflict", "The request conflicts with existing data.");
      const board: Board = { id: BOARD(made++), name, description: (body!.description as string) ?? null, archived_at: null, created_at: NOW.toISOString(), updated_at: NOW.toISOString() };
      boards.push(board);
      items[board.id] = [];
      return json(out(board), 201);
    }
    const [, , , id, rest, pid, tail] = path.split("/"); // "", v1, boards, {id}, items|archive|unarchive, {product_id}|send-to-testing
    const board = boards.find((b) => b.id === id);
    if (!board) return fail(404, "not_found", "Board not found.");
    if (!rest && method === "PATCH") {
      if (typeof body!.name === "string" && taken(body!.name.trim(), id)) return fail(409, "conflict", "The request conflicts with existing data.");
      if (typeof body!.name === "string") board.name = body!.name.trim();
      if ("description" in body!) board.description = body!.description as string | null;
      bump(board);
      return json(out(board));
    }
    if (rest === "archive" || rest === "unarchive") {
      board.archived_at = rest === "archive" ? (board.archived_at ?? NOW.toISOString()) : null;
      bump(board);
      return json(out(board));
    }
    if (rest !== "items") return fail(404, "not_found", "Not found.");
    const cards = sorted(id);
    if (!pid && method === "GET") {
      if (options.itemsStatus) return fail(options.itemsStatus, "unavailable", "The API is restarting. Try again.");
      const limit = Number(url.searchParams.get("limit") ?? 50);
      const cursor = url.searchParams.get("cursor");
      const after = cursor ? (JSON.parse(cursor) as [number, string]) : null;
      const page = cards.filter((c) => !after || c.position > after[0] || (c.position === after[0] && c.product_id > after[1]));
      const last = page.length > limit ? page[limit - 1] : null;
      return json({ items: page.slice(0, limit), next_cursor: last ? JSON.stringify([last.position, last.product_id]) : null } satisfies S["BoardItemPage"]);
    }
    if (!pid && method === "POST") {
      const ids = body!.product_ids as string[];
      const added = ids.filter((p) => !cards.some((c) => c.product_id === p));
      let next = Math.max(-1, ...cards.map((c) => c.position)) + 1;
      for (const p of added) cards.push(card(Number(p.slice(-12)), next++, { added_at: NOW.toISOString() }));
      items[id] = cards;
      bump(board);
      return json({ added, skipped: ids.filter((p) => !added.includes(p)) });
    }
    if (pid === "send-to-testing") {
      const ids = body!.product_ids as string[];
      bump(board);
      const created = ids.filter((p) => p !== OPEN_TEST).map((product_id, i) => ({ id: 200 + i, product_id, stage: "idea" }));
      return json({ created, skipped: ids.filter((p) => p === OPEN_TEST) });
    }
    const one = cards.find((c) => c.product_id === pid);
    if (method === "DELETE") {
      items[id] = cards.filter((c) => c.product_id !== pid);
      bump(board);
      return json(out(board));
    }
    if (method === "PATCH" && one && tail === undefined) {
      if ("note" in body! && options.failNotes) return fail(503, "unavailable", "The API is restarting. Try again.");
      if ("position" in body! && options.failMoves) return fail(503, "unavailable", "The API is restarting. Try again.");
      if ("note" in body!) one.note = body!.note as string | null;
      if (typeof body!.position === "number") {
        const order = cards.filter((c) => c !== one);
        order.splice(body!.position, 0, one);
        order.forEach((c, i) => (c.position = i));
        items[id] = order;
      }
      bump(board);
      return json(one);
    }
    return fail(404, "not_found", "The product is not on this board.");
  });

  return {
    calls,
    boards,
    items,
    writes: (path?: RegExp) => calls.filter((c) => c.method !== "GET" && (!path || path.test(c.path))),
    set: (next: Partial<BoardsMock>) => Object.assign(options, next),
  };
}
