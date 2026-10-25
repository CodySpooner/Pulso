import type { Tab } from "./tabs";

// imp-368 (DEC-309): a withheld landed margin's one next action. Duty, the card's amber label whenever it is a gap,
// and a workspace with no settings row yet are closed in Settings. A missing supplier price or freight quote goes to
// Suppliers, since Profit has nothing to cost without one. A market price, a USD rate or a too-large amount goes to Profit.
const SUPPLIER_GAPS = ["supplier_cost_missing", "freight_missing", "freight_variant_mismatch"];

export type MarginFix = { label: string; href: string } | { label: string; tab: Tab };

export function marginFix(missing: string[]): MarginFix {
  if (missing.includes("duty_not_set")) return { label: "Set duty", href: "/settings#duty" };
  if (!missing.length) return { label: "Open Settings", href: "/settings" };
  if (missing.some((code) => SUPPLIER_GAPS.includes(code))) return { label: "Open Suppliers", tab: "suppliers" };
  return { label: missing.includes("price_missing") ? "Enter a price" : "Open Profit", tab: "profit" };
}
