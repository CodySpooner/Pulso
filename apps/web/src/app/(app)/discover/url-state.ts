// Discover's view, sort and filters live in the URL (vault Features/Discover), so a link reproduces the feed. Prices
// are whole USD in the URL and minor units at the API. A missing or unknown value falls back to the default, and the
// default is never written, so a clean URL means the default feed.

export const SORTS = { momentum: "Momentum", newest: "Newest", fewest_sellers: "Fewest stores" } as const;
export const SOURCES = { shopify_stores: "Shopify stores", cj: "CJ Dropshipping" } as const;
export const FIRST_SEEN = [7, 30, 90] as const;

export type Sort = keyof typeof SORTS;
export type View = "grid" | "table";

export interface Filters {
  category: number | null;
  price_min: number | null; // whole USD
  price_max: number | null;
  source: keyof typeof SOURCES | null;
  first_seen_days: (typeof FIRST_SEEN)[number] | null;
  has_sellers: boolean | null;
}

export interface FeedState extends Filters {
  view: View | null; // null: the viewer's remembered view
  sort: Sort;
}

export const NO_FILTERS: Filters = { category: null, price_min: null, price_max: null, source: null, first_seen_days: null, has_sellers: null };

const whole = (raw: string | null) => (raw !== null && /^\d{1,7}$/.test(raw) ? Number(raw) : null);
const oneOf = <T extends string>(raw: string | null, values: readonly T[]) => (values.includes(raw as T) ? (raw as T) : null);

export function parseFeed(params: URLSearchParams): FeedState {
  const days = whole(params.get("first_seen_days"));
  const sellers = params.get("has_sellers");
  return {
    view: oneOf(params.get("view"), ["grid", "table"]),
    sort: oneOf(params.get("sort"), Object.keys(SORTS) as Sort[]) ?? "momentum",
    category: whole(params.get("category")) || null,
    price_min: whole(params.get("price_min")),
    price_max: whole(params.get("price_max")),
    source: oneOf(params.get("source"), Object.keys(SOURCES) as (keyof typeof SOURCES)[]),
    first_seen_days: FIRST_SEEN.find((d) => d === days) ?? null,
    has_sellers: sellers === "true" ? true : sellers === "false" ? false : null,
  };
}

/** The query string for a state, without the `?`; defaults are left out. */
export function feedSearch(state: FeedState): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(state)) {
    if (value !== null && !(key === "sort" && value === "momentum")) params.set(key, String(value));
  }
  return params.toString();
}

/** The API query for a state: prices in minor units. */
export function apiQuery({ sort, category, price_min, price_max, source, first_seen_days, has_sellers }: FeedState) {
  const minor = (usd: number | null) => (usd === null ? null : usd * 100);
  const query = { sort, category, price_min: minor(price_min), price_max: minor(price_max), source, first_seen_days, has_sellers };
  return Object.fromEntries(Object.entries(query).filter(([, value]) => value !== null)) as Partial<typeof query>;
}

// Keyset pages over live keys (momentum, store count) can repeat a product whose key moved between loads; the first
// place wins, so each card and row keeps a unique key (XR-19, DEC-260 a).
export function joinPages<T extends { id: string }>(pages: readonly { items: readonly T[] }[] | undefined): T[] {
  const byId = new Map<string, T>();
  for (const item of (pages ?? []).flatMap((p) => p.items)) if (!byId.has(item.id)) byId.set(item.id, item);
  return [...byId.values()];
}

export const activeFilters = (state: Filters) => (Object.keys(NO_FILTERS) as (keyof Filters)[]).filter((key) => state[key] !== null);

const VIEW_KEY = "pulso.discover.view";

/** The view this viewer last picked, or null. Storage can be missing or throw (private mode, blocked site data). */
export function readView(storage: Pick<Storage, "getItem"> | undefined = globalThis.localStorage): View | null {
  try {
    return oneOf(storage?.getItem(VIEW_KEY) ?? null, ["grid", "table"]);
  } catch {
    return null;
  }
}

export function saveView(view: View, storage: Pick<Storage, "setItem"> | undefined = globalThis.localStorage) {
  try {
    storage?.setItem(VIEW_KEY, view);
  } catch {
    // ponytail: the choice lasts for this page only; the URL still carries it.
  }
}
