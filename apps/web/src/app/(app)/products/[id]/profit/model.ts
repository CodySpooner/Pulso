// Pure helpers for the Profit tab (UX-8 part b, DEC-256): money at its currency's exponent, a typed price read as
// minor units, the price slider's range, the scenario request and the R-16 missing reasons in words. No profit
// maths here: every number the tab shows is one POST /v1/profit/calc returned (DEC-246).

import type { components } from "@/lib/api/schema";

export type Calc = components["schemas"]["ProfitCalc"];
export type Missing = Calc["missing"][number];
export type Trace = components["schemas"]["InputSource"];

const formats = new Map<string, Intl.NumberFormat>();
function currencyFormat(currency: string) {
  let format = formats.get(currency);
  if (!format) formats.set(currency, (format = new Intl.NumberFormat("en-US", { style: "currency", currency })));
  return format;
}

/** The decimals Intl gives a currency: JPY 0, USD 2, KWD 3. */
export const exponent = (currency: string) => currencyFormat(currency).resolvedOptions().maximumFractionDigits ?? 2;

/** Minor units formatted at the edge only, with the currency's exponent: 2999 → "$29.99". */
export const money = (minor: number, currency = "USD") => currencyFormat(currency).format(minor / 10 ** exponent(currency));

/** A cost line, signed with U+2212: 620 → "−$6.20"; zero stays "$0.00". */
export const cost = (minor: number, currency = "USD") => (minor > 0 ? `−${money(minor, currency)}` : money(minor, currency));

/** Profit with its sign and glyph, so the tone is never colour alone (AGENTS.md §7). */
export function signedMoney(minor: number, currency = "USD") {
  if (minor === 0) return { glyph: null, text: money(0, currency), tone: "neutral" } as const;
  return minor > 0
    ? ({ glyph: "▲", text: `+${money(minor, currency)}`, tone: "positive" } as const)
    : ({ glyph: "▼", text: `−${money(-minor, currency)}`, tone: "negative" } as const);
}

const rate = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 2 });
const fixed = new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
/** A rate in basis points: 290 → "2.9%". */
export const pct = (bps: number) => rate.format(bps / 10_000);
/** A line as a share of the sell price, for the breakdown's display column: 620 of 2999 → "20.7%". */
export const share = (minor: number, price: number) => fixed.format(minor / price);

/** A typed amount as integer minor units, or null: "29.99" → 2999. Digits only, at most the exponent's decimals. */
export function parseMinor(text: string, currency = "USD"): number | null {
  const e = exponent(currency);
  const match = text.trim().replace(/^\$/, "").replaceAll(",", "").match(/^(\d+)(?:\.(\d*))?$/);
  if (!match || (match[2] ?? "").length > e) return null;
  const minor = Number(match[1]) * 10 ** e + Number((match[2] ?? "").padEnd(e, "0") || 0);
  return Number.isSafeInteger(minor) ? minor : null;
}

/** Minor units as an input's text, without the symbol: 2999 → "29.99". */
export function toInput(minor: number, currency = "USD"): string {
  const e = exponent(currency);
  if (e === 0) return String(minor);
  const digits = String(minor).padStart(e + 1, "0");
  return `${digits.slice(0, -e)}.${digits.slice(-e)}`;
}

/** The price slider: from about half to double the anchor in 50-cent steps that keep its cents (…49, …99). */
export function priceRange(anchor: number, step = 50) {
  return { min: anchor - step * Math.floor(anchor / 2 / step), max: anchor + step * Math.ceil(anchor / step), step };
}

/** What the owner changed; `undefined` means the default the endpoint applies (Settings, the market price). */
export interface Scenario {
  quantity: number;
  price?: number;
  returns?: number;
  fee?: number;
  ad?: number;
}

export const DEFAULTS: Scenario = { quantity: 1 };

/** The calc request for a scenario: unchanged inputs stay out, so the server applies its defaults. `supplier` is the
 *  listing chosen on the Suppliers tab (`?supplier=`); without one the server costs the best complete margin. */
export const request = (id: string, s: Scenario, supplier: number | null = null) => ({
  product_id: id,
  supplier_listing_id: supplier ?? undefined,
  quantity: s.quantity,
  ddp: false, // a DDP toggle is backlog; the client types it as required (it has a default)
  price_minor: s.price,
  returns_bps: s.returns,
  payment_fee_bps: s.fee,
  ad_cost_minor: s.ad,
});

const units = (q: number) => `${q} ${q === 1 ? "unit" : "units"}`;

const REASONS: Record<Missing, (calc: Calc) => string> = {
  price_missing: (c) =>
    c.quantity > 1
      ? `No sell price for a ${c.quantity}-unit order: a one-unit store price never stands in for it. Enter the order's price.`
      : "No sell price: Pulso has no market price for it yet. Enter your price to see profit.",
  supplier_cost_missing: () => "No supplier cost: Pulso hasn't captured a price for the supplier listing yet.",
  freight_missing: (c) => `Freight isn't quoted for this variant to the US at ${units(c.quantity)} per order.`,
  freight_variant_mismatch: () => "Freight is quoted for another variant of the supplier listing, not this one.",
  duty_not_set: () => "Duty isn't set: Settings has no US duty rate yet, and Pulso never assumes 0%.",
  fx_missing: () => "No USD exchange rate within 4 days of the supplier price's date.",
  amount_out_of_range: () => "An amount is too large to compute.",
};

/** Every reason the margin is withheld (R-16), in plain words and the API's order. */
export const reasons = (calc: Calc) => calc.missing.map((code) => REASONS[code](calc));

const NEEDS: Record<Missing, string> = {
  price_missing: "a sell price",
  supplier_cost_missing: "a supplier price",
  freight_missing: "a freight quote",
  freight_variant_mismatch: "a freight quote for this variant",
  duty_not_set: "a duty rate",
  fx_missing: "a USD exchange rate",
  amount_out_of_range: "smaller amounts",
};
const and = new Intl.ListFormat("en-US", { type: "conjunction" });

/** What a withheld result waits for: "Needs a freight quote and a duty rate". */
export const needs = (calc: Calc) => `Needs ${and.format(calc.missing.map((code) => NEEDS[code]))}`;

/** The few words a breakdown line shows in place of its amount. */
export const GAPS: Record<Missing, string> = {
  price_missing: "Enter a price",
  supplier_cost_missing: "No supplier price",
  freight_missing: "Not quoted",
  freight_variant_mismatch: "Not quoted for this variant",
  duty_not_set: "Not set",
  fx_missing: "No USD rate",
  amount_out_of_range: "Too large",
};
