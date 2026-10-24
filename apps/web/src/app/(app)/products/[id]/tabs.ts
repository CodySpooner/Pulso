import { ChartLine, CircleDollarSign, LayoutDashboard, Store, Truck } from "lucide-react";

// The product page tabs in validation order (vault Features/Product Page). Each body arrives with its own Phase 2
// task; until then its panel names the task and shows no number.
export const TABS = [
  { value: "overview", label: "Overview", task: "UX-4", icon: LayoutDashboard, summary: "Key stats, notes and tags on one screen." },
  { value: "trends", label: "Trends", task: "UX-5", icon: ChartLine, summary: "Order velocity, search interest, price and store count over time, with collection gaps marked." },
  { value: "suppliers", label: "Suppliers", task: "UX-6", icon: Truck, summary: "Every matched supplier with unit cost, US shipping and the best-margin and fastest-shipping picks." },
  { value: "sellers", label: "Sellers", task: "UX-7", icon: Store, summary: "Every store selling it, its price and when it started, with the price spread." },
  { value: "profit", label: "Profit", task: "UX-8", icon: CircleDollarSign, summary: "Landed cost after shipping, duty and fees, with margin, break-even ROAS and break-even CPA." },
] as const;

export type Tab = (typeof TABS)[number]["value"];

/** One feature flag per tab (AGENTS.md §3). ponytail: flipped in code, like nav.ts's CURRENT_PHASE; an env flag
 *  when one has to flip without a deploy. */
export const TAB_FLAGS: Record<Tab, boolean> = { overview: true, trends: true, suppliers: true, sellers: true, profit: true };

/** The tab `?tab=` shows. An unknown or flagged-off value falls back to Overview, never an error. */
export function resolveTab(value: string | null, flags: Record<Tab, boolean> = TAB_FLAGS): Tab {
  const tab = TABS.find((t) => t.value === value);
  return tab && flags[tab.value] ? tab.value : "overview";
}
