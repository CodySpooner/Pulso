import type { components } from "@/lib/api/schema";

// A screen's definition: what GET /v1/screener runs and a saved screen stores (DEC-336), plus its columns (DEC-347).
// An unsaved one lives in the URL as base64url JSON (vault Features/Product Screener, Saved screens).

type Saved = components["schemas"]["ScreenIn"];
export type Filters = components["schemas"]["Filters"];
export type SortKey = NonNullable<Saved["sort"]>;
export type Column = NonNullable<Saved["columns"]>[number];
export type Stage = NonNullable<Filters["lifecycle"]>[number];
export type Range = Exclude<SortKey, "trend" | "opportunity">;

export interface Definition {
  filters: Filters;
  sort: SortKey;
  order: "desc" | "asc";
  columns: Column[] | null; // null: DEFAULT_COLUMNS
}

export const DEFAULT: Definition = { filters: {}, sort: "trend", order: "desc", columns: null };

/** Each range filter as typed, and `scale` to the API's unit: 40 % is 4000 bps, $25 is 2500, 4.5★ is 450. */
export const RANGES: Record<Range, { label: string; unit: string; scale: number; int?: true }> = {
  margin_bps: { label: "Landed margin", unit: "%", scale: 100, int: true },
  velocity: { label: "Velocity 7d", unit: "units", scale: 1 },
  acceleration: { label: "Acceleration", unit: "Δ growth", scale: 1 },
  saturation: { label: "Saturation", unit: "0–100", scale: 1 },
  price: { label: "Price", unit: "USD", scale: 100, int: true },
  supplier_rating: { label: "Supplier rating", unit: "★", scale: 100, int: true },
  ship_days_us: { label: "Ship days to US", unit: "days", scale: 1, int: true },
};

export const COLUMNS: Record<Column, string> = {
  lifecycle: "Lifecycle",
  trend: "Trend",
  opportunity: "Opportunity",
  velocity: "Velocity 7d",
  acceleration: "Acceleration",
  saturation: "Saturation",
  margin_bps: "Margin",
  price: "Price",
  supplier_rating: "Supplier rating",
  ship_days_us: "Ship to US",
};
export const DEFAULT_COLUMNS: Column[] = ["lifecycle", "trend", "opportunity", "velocity", "acceleration", "saturation", "margin_bps", "price", "ship_days_us"];
export const SORTS = Object.keys(COLUMNS).filter((c) => c !== "lifecycle") as SortKey[];
export const STAGES: Stage[] = ["emerging", "rising", "peaking", "declining", "dead"];
const BOUNDS = (Object.keys(RANGES) as Range[]).flatMap((k) => [`${k}_min`, `${k}_max`] as const);

type Loose = Record<string, unknown>;
const isObject = (v: unknown): v is Loose => typeof v === "object" && v !== null && !Array.isArray(v);

/** A definition from anything (a URL, a saved screen): known keys only, in one order, so equal screens encode equally.
 *  The API still validates each bound's range (422 invalid_filters). */
export function clean(raw: unknown): Definition {
  const given = isObject(raw) ? raw : {};
  const f = isObject(given.filters) ? given.filters : {};
  const filters: Filters = {};
  for (const key of BOUNDS) {
    const value = f[key];
    if (typeof value === "number" && Number.isFinite(value)) filters[key] = value;
  }
  const stages = Array.isArray(f.lifecycle) ? STAGES.filter((s) => (f.lifecycle as unknown[]).includes(s)) : [];
  if (stages.length) filters.lifecycle = stages;
  if (Number.isSafeInteger(f.category) && (f.category as number) > 0) filters.category = f.category as number;
  const columns = Array.isArray(given.columns) ? given.columns.filter((c): c is Column => typeof c === "string" && Object.hasOwn(COLUMNS, c)) : [];
  return {
    filters,
    sort: SORTS.includes(given.sort as SortKey) ? (given.sort as SortKey) : "trend",
    order: given.order === "asc" ? "asc" : "desc",
    columns: columns.length ? [...new Set(columns)] : null,
  };
}

// ponytail: btoa takes Latin-1 only; a definition is keys, numbers and stage names, never free text.
export const encode = (d: Definition) => btoa(JSON.stringify(clean(d))).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");

/** The definition in `?q=`, or null when there is none or it doesn't parse. */
export function decode(q: string | null): Definition | null {
  if (!q) return null;
  try {
    return clean(JSON.parse(atob(q.replaceAll("-", "+").replaceAll("_", "/"))));
  } catch {
    return null;
  }
}

export const same = (a: Definition, b: Definition) => encode(a) === encode(b);

/** The URL's query string, without `?`: the saved screen's id, and the definition while it differs from that screen. */
export function screenSearch(screen: string | null, definition: Definition | null): string {
  const params = new URLSearchParams();
  if (screen) params.set("screen", screen);
  if (definition) params.set("q", encode(definition));
  return params.toString();
}

/** The filter bounds set, as their metric keys (lifecycle and category as themselves), in RANGES order. */
export const conditionsOf = (f: Filters): (Range | "lifecycle" | "category")[] => [
  ...(Object.keys(RANGES) as Range[]).filter((k) => f[`${k}_min`] != null || f[`${k}_max`] != null),
  ...(f.lifecycle ? (["lifecycle"] as const) : []),
  ...(f.category != null ? (["category"] as const) : []),
];
