// Pure helpers for the Suppliers tab (UX-6, DEC-264): the chosen supplier in the URL, and the words the table uses.
// No cost maths here: every money number is the one POST /v1/profit/calc returns for that supplier (DEC-246).

import type { Stat } from "@/components/pulso/metric";
import type { components } from "@/lib/api/schema";

import { needs, type Calc, type Missing } from "../profit/model";

type Schemas = components["schemas"];
// openapi-fetch drops a key typed only `null` from responses (DEC-238 g), so a NoSource arrives as `{reason}`.
type Gap = { reason: string; value?: null };
export type Row = Omit<Schemas["SupplierRow"], "stock" | "rating" | "orders" | "years_active" | "moq"> & {
  stock: Stat;
  years_active: Stat;
  moq: Stat;
  rating: Schemas["Rating"] | Gap;
  orders: Schemas["Orders"] | Gap;
};
export type Page = Omit<Schemas["SuppliersPage"], "rows" | "picks"> & { rows: Row[]; picks: { best_margin: Row | null; fastest: Row | null } };

const PARAM = "supplier";

/** The supplier listing the page costs Profit with, or null: a positive integer id only. */
export function parseSupplier(params: URLSearchParams): number | null {
  const value = params.get(PARAM);
  return value && /^[1-9]\d{0,17}$/.test(value) && Number.isSafeInteger(Number(value)) ? Number(value) : null;
}

/** The query string with `supplier` set (or dropped for null) and every other parameter kept, without the `?`. */
export function supplierSearch(search: string, id: number | null): string {
  const params = new URLSearchParams(search);
  if (id === null) params.delete(PARAM);
  else params.set(PARAM, String(id));
  return params.toString();
}

/** Delivery days as the table shows them: "8–12 d", "5 d", "8+ d". */
export function days(min: number | null, max: number | null): string | null {
  if (min === null && max === null) return null;
  if (min === null || min === max) return `${max ?? min} d`;
  return max === null ? `${min}+ d` : `${min}–${max} d`;
}

/** A margin cell's few words for why it is withheld, in the API's order (R-16). */
const SHORT: Record<Missing, string> = {
  price_missing: "No market price",
  supplier_cost_missing: "No supplier price",
  freight_missing: "Freight not quoted",
  freight_variant_mismatch: "Other variant quoted",
  duty_not_set: "Duty not set",
  fx_missing: "No USD rate",
  amount_out_of_range: "Too large",
};
export const short = (calc: Calc) => SHORT[calc.missing[0] ?? "amount_out_of_range"];

/** Inputs every row lacks, which the page explains once: a market price and a duty rate are not per supplier. */
export function shared(rows: Row[]): Missing[] {
  const codes: Missing[] = ["price_missing", "duty_not_set"];
  return rows.length ? codes.filter((code) => rows.every((row) => row.cost.missing.includes(code))) : [];
}

/** Why there is no Best margin pick, or null when there is one (or nothing to pick from). */
export function noBestMargin(page: Page): string | null {
  if (page.picks.best_margin || !page.rows.length) return null;
  const stocked = page.rows.filter((row) => row.in_stock);
  if (!stocked.length) return "Every supplier is out of stock.";
  const missing = [...new Set(stocked.flatMap((row) => row.cost.missing))];
  return `No supplier has complete costs. ${needs({ ...stocked[0].cost, missing })}.`;
}

export const noFastest = (page: Page) =>
  page.picks.fastest || !page.rows.length ? null : "No in-stock supplier has a US freight quote with delivery days yet.";

/** Hundredths of a star: 470 → "4.7". */
export const stars = (value: number) => (value / 100).toFixed(1);

const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
export const count = (n: number) => compact.format(n);

/** What an order count means: lifetime sales, or a window of days. */
export const ordersBasis = (orders: Schemas["Orders"]) => (orders.semantics === "lifetime" ? "lifetime" : `${orders.window_days} d`);
