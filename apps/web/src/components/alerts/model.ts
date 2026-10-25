import { Bell, PackageCheck, PackageX, Tag, Truck, type LucideIcon } from "lucide-react";

import { sourceLabel } from "@/app/(app)/admin/matching/model";
import { money } from "@/app/(app)/products/[id]/profit/model";
import type { components } from "@/lib/api/schema";

// Pure helpers for the bell, its popover and /alerts (WF-4b, DEC-333): the badge, the Today / Earlier split on the
// UTC day, an alert in words, and the page it opens.

export type Alert = components["schemas"]["AlertOut"];

/** The bell's badge: nothing at 0, capped at "99+". */
export const badge = (count: number) => (count <= 0 ? null : count > 99 ? "99+" : String(count));

/** The bell's accessible name says the exact count, past the badge's cap too. */
export const bellLabel = (count: number | undefined) => (count === undefined ? "Alerts" : `Alerts, ${count || "none"} unread`);

const utcDay = (iso: string) => new Date(iso).toISOString().slice(0, 10);

/** Today and Earlier by UTC calendar day (AGENTS.md §3), each in the API's newest-first order. */
export function groupByDay(alerts: Alert[], now: number) {
  const today = utcDay(new Date(now).toISOString());
  return [
    { label: "Today", items: alerts.filter((a) => utcDay(a.fired_at) === today) },
    { label: "Earlier", items: alerts.filter((a) => utcDay(a.fired_at) !== today) },
  ].filter((group) => group.items.length > 0);
}

export const TYPES: Record<string, { label: string; icon: LucideIcon; up?: string; down?: string; title?: string }> = {
  supplier_price_change: { label: "Supplier price", icon: Tag, title: "Supplier price changed", up: "Supplier price rose", down: "Supplier price fell" },
  freight_change: { label: "Freight", icon: Truck, title: "Freight changed", up: "Freight rose", down: "Freight fell" },
  supplier_stock_out: { label: "Stock-out", icon: PackageX, title: "Supplier ran out of stock" },
  back_in_stock: { label: "Back in stock", icon: PackageCheck, title: "Supplier back in stock" },
};

interface Value {
  value?: unknown;
  currency?: unknown;
  as_of?: unknown;
  source?: unknown;
}

const humanize = (type: string) => type.replace(/[._]+/g, " ").replace(/^./, (c) => c.toUpperCase());
const stock = (inStock: boolean) => (inStock ? "In stock" : "Out of stock");

/** One alert in words: a sentence, the signed % change and old → new where it has them, its source and entity. */
export function describeAlert(alert: Alert) {
  const type = TYPES[alert.type];
  const { old, new: now } = alert.payload as { old?: Value; new?: Value };
  const [from, to] = [old?.value, now?.value];
  const currency = typeof now?.currency === "string" ? now.currency : "USD";
  // The engine's own % (pulso_core.alerts.past): from the reference, a 0 reference read as 1.
  const pct = typeof from === "number" && typeof to === "number" ? ((to - from) * 100) / Math.max(from, 1) : null;
  const change =
    pct !== null ? `${money(from as number, currency)} → ${money(to as number, currency)}` : typeof from === "boolean" && typeof to === "boolean" ? `${stock(from)} → ${stock(to)}` : null;
  const entity = alert.entity_type === "supplier_offer" ? `offer ${alert.entity_id}` : `${alert.entity_type.replaceAll("_", " ")} ${alert.entity_id}`;
  return {
    icon: type?.icon ?? Bell,
    title: (pct !== null && (pct < 0 ? type?.down : type?.up)) || type?.title || humanize(alert.type),
    pct,
    change,
    meta: typeof now?.source === "string" ? `${sourceLabel(now.source)} · ${entity}` : entity,
    asOf: typeof now?.as_of === "string" ? now.as_of : null,
  };
}

/** The page an alert opens. The engine links a product's Suppliers tab as a path; the Product Page reads `?tab=`. */
export function entityHref(alert: Alert): string | null {
  const link = (alert.payload as { link?: unknown }).link;
  const product = typeof link === "string" ? /^\/products\/([\w-]+)(?:\/(\w+))?$/.exec(link) : null;
  if (product) return `/products/${product[1]}${product[2] ? `?tab=${product[2]}` : ""}`;
  if (alert.entity_type === "test") return `/testing?test=${encodeURIComponent(alert.entity_id)}`;
  if (alert.entity_type === "product") return `/products/${encodeURIComponent(alert.entity_id)}`;
  return null;
}

/** The newest evaluation of any rule; stale past 26 h, when the collector host has likely been off (vault note). */
export function lastEvaluation(rules: { last_evaluated_at: string | null }[], now: number) {
  const at = Math.max(...rules.map((r) => (r.last_evaluated_at ? Date.parse(r.last_evaluated_at) : 0)));
  return at > 0 ? { iso: new Date(at).toISOString(), stale: now - at > 26 * 3_600_000 } : null;
}

const day = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

/** A skipped evaluation's gap, `{reason: "gap", from, to}`, as UTC days. */
export function gapSpan(skipped: { [key: string]: unknown } | null) {
  const { from, to } = skipped ?? {};
  return typeof from === "string" && typeof to === "string" ? `data gap ${day.format(new Date(from))} → ${day.format(new Date(to))}` : "data gap";
}

export const FIRES = "An alert fires once when a supplier’s price or freight moves past a rule’s threshold, or an offer runs out of stock or comes back.";

/** How many rules are on, and how many of them have nothing to read yet (DEC-040: no source, never zero). */
export function rulesLine(rules: { enabled: boolean; status: string | null }[]) {
  const on = rules.filter((r) => r.enabled);
  const none = on.filter((r) => r.status === "no_source").length;
  if (on.length === 0) return "No rule is on yet.";
  return `${on.length} ${on.length === 1 ? "rule is" : "rules are"} on${none ? `, ${none} with no source yet` : ""}.`;
}
