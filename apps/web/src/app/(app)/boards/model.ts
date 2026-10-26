// Pure helpers for Boards (WF-3b, DEC-329): the API reads, a card move as update_board_item renumbers it (DEC-319 b)
// with its optimistic update and rollback, a card note's autosave, and the words of a card's stats (imp-454).

import type { QueryClient, QueryKey, UseMutationOptions } from "@tanstack/react-query";

import { $api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type Board = components["schemas"]["Board"];
// openapi-fetch drops a key typed only `null` from responses, so each NoSource arrives as `{reason}` (DEC-238 g).
type Loose<T> = T extends { reason: string } ? Omit<T, "value"> & { value?: null } : T;
export type Item = { [K in keyof components["schemas"]["BoardItem"]]: Loose<components["schemas"]["BoardItem"][K]> };
export type ItemPage = Omit<components["schemas"]["BoardItemPage"], "items"> & { items: Item[] };
export type Score = Item["trend"];
export type Stage = NonNullable<components["schemas"]["LatestScore"]["stage"]>;
export interface Move {
  product_id: string;
  position: number;
}

export const boardsInit = (archived: boolean) => ({ params: { query: { archived } } });
export const boardsKey = (archived: boolean) => $api.queryOptions("get", "/v1/boards", boardsInit(archived)).queryKey;
// ponytail: the first 100 cards (the API's largest page). They're a prefix of the board's order, so a move inside
// them sends the right 0-based place; page the board once one holds more.
export const itemsInit = (board_id: string, limit = 100) => ({ params: { path: { board_id }, query: { limit } } });
export const itemsKey = (board_id: string) => $api.queryOptions("get", "/v1/boards/{board_id}/items", itemsInit(board_id)).queryKey;

/** The cards after moving one to a 0-based place (past the end means last), renumbered 0…n−1 as the API does. */
export function moved(items: Item[], productId: string, to: number): Item[] {
  const from = items.findIndex((i) => i.product_id === productId);
  if (from < 0) return items;
  const rest = items.filter((_, i) => i !== from);
  rest.splice(Math.max(0, Math.min(to, rest.length)), 0, items[from]);
  return rest.map((item, position) => ({ ...item, position }));
}

/** useMutation options for a move: the card moves before the API answers, and a failure restores the order it had.
 *  The page refetches either way, so the server's order wins. */
export function moveOptions(client: QueryClient, key: QueryKey, send: (move: Move) => Promise<Item>): UseMutationOptions<Item, unknown, Move, ItemPage | undefined> {
  return {
    mutationFn: send,
    onMutate: async ({ product_id, position }) => {
      await client.cancelQueries({ queryKey: key });
      const before = client.getQueryData<ItemPage>(key);
      client.setQueryData<ItemPage>(key, (page) => page && { ...page, items: moved(page.items, product_id, position) });
      return before;
    },
    onError: (_error, _move, before) => void (before && client.setQueryData(key, before)),
    onSettled: () => client.invalidateQueries({ queryKey: key }),
  };
}

export type SaveState = "saved" | "pending" | "saving" | "error";

/** A note's autosave: a pause in typing (or `flush`, on blur and Retry) saves the latest text, one save at a time.
 *  A failed save keeps its text and waits for Retry or more typing; it never retries on its own. */
export function autosave(save: (text: string) => Promise<unknown>, onState: (state: SaveState) => void, delay = 800) {
  let unsaved: string | null = null;
  let busy = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const flush = async () => {
    clearTimeout(timer);
    if (busy || unsaved === null) return;
    const text = unsaved;
    unsaved = null;
    busy = true;
    onState("saving");
    try {
      await save(text);
      busy = false;
      if (unsaved === null) onState("saved");
      else void flush(); // typed while saving
    } catch {
      busy = false;
      unsaved ??= text;
      onState("error");
    }
  };
  return {
    change(text: string) {
      unsaved = text;
      onState("pending");
      clearTimeout(timer);
      timer = setTimeout(flush, delay);
    },
    flush,
  };
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", trailingZeroDisplay: "stripIfInteger" });
export const money = (minor: number) => usd.format(minor / 100);
const pct = (bps: number) => `${(bps / 100).toFixed(1)}%`;
export const STAGES: Record<Stage, string> = { emerging: "Emerging", rising: "Rising", peaking: "Peaking", declining: "Declining", dead: "Dead" };

/** A score's words: its rounded value or its stage; "Insufficient signal" for a stored row without one; "No source
 *  yet" when nothing has scored the product. Never 0 (DEC-040). */
export function scoreText(score: Score): string {
  if (!("model_version" in score)) return "No source yet";
  if (score.stage) return STAGES[score.stage];
  return score.value == null ? "Insufficient signal" : String(Math.round(score.value));
}

/** The best landed margin's words, $ and % with a loss in U+2212 as on the Profit tab. R-16 withholds an incomplete
 *  one: "Duty not set" names the one gap Settings closes, anything else is "No source yet" (Discover's BestMargin). */
export function marginText(margin: Item["best_margin_minor"]): string {
  if ("reason" in margin) return margin.missing.includes("duty_not_set") ? "Duty not set" : "No source yet";
  return `${money(margin.value)} · ${pct(margin.margin_bps)}`.replaceAll("-", "−");
}

/** The card's freshness dot: the oldest as-of among its stats, stale when a traced one is (vault Features/Boards). */
export function freshness(item: Item): { as_of: string | null; stale: boolean } {
  const traced = [item.price_min_minor, item.price_max_minor, item.best_margin_minor].filter((s) => "source" in s);
  const scores = [item.trend, item.saturation, item.lifecycle].filter((s) => "model_version" in s);
  const times = [...traced, ...scores].map((s) => s.as_of);
  return {
    as_of: times.length ? times.reduce((a, b) => (Date.parse(b) < Date.parse(a) ? b : a)) : null,
    stale: traced.some((s) => s.stale),
  };
}
