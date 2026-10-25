import { Bell, PackageCheck, PackageX, Tag, Truck, type LucideIcon } from "lucide-react";

import { sourceLabel } from "@/app/(app)/admin/matching/model";
import { money } from "@/app/(app)/products/[id]/profit/model";
import { isProblem } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatAgo, formatUtc } from "@/lib/format";

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

// WF-4c (p4-27, DEC-339): the Rules tab and the sentence-style builder.

export type Rule = components["schemas"]["RuleOut"];
type RuleIn = components["schemas"]["RuleIn"];
export type RuleType = RuleIn["type"];

/** The builder's sentence: When [target] [verb] [pct] %. `target` is "product" (any of its suppliers) or a listing id. */
export interface Draft {
  target: string;
  type: RuleType;
  pct: string;
  name: string;
}

export const VERBS: Record<RuleType, string> = {
  supplier_price_change: "changes price by",
  freight_change: "changes freight by",
  supplier_stock_out: "goes out of stock",
  back_in_stock: "comes back in stock",
};

export const hasPct = (type: string) => type === "supplier_price_change" || type === "freight_change";

// The % goes to the API as typed (blank reads 0), so its 422 is the one place a bad value is explained. A stock rule
// sends the API's default, 5, which its evaluation ignores.
const pctOf = (draft: Draft) => ({ pct: hasPct(draft.type) ? Number(draft.pct) : 5 });

/** The name a rule gets when none is typed, in the Testing defaults' "Scope: what" style. */
export const autoName = (draft: Draft, product: string) => `${product}: ${TYPES[draft.type].label.toLowerCase()}${hasPct(draft.type) ? ` ±${draft.pct.trim()}%` : ""}`;

export function createBody(draft: Draft, product: { id: string; name: string }): RuleIn {
  const offer = draft.target !== "product";
  return {
    name: draft.name.trim() || autoName(draft, product.name),
    type: draft.type,
    target_type: offer ? "supplier_offer" : "product",
    target_id: offer ? draft.target : product.id,
    params: pctOf(draft),
    enabled: true,
  };
}

/** A rule's type and target are fixed once made (the API's PATCH takes neither). */
export const patchBody = (draft: Draft, rule: Rule) => ({ name: draft.name.trim(), ...(hasPct(rule.type) && { params: pctOf(draft) }) });

export const draftOf = (rule: Rule): Draft => ({
  target: rule.target_type === "supplier_offer" ? String(rule.target_id) : "product",
  type: rule.type as RuleType,
  pct: String(rule.params.pct ?? 5),
  name: rule.name,
});

const OFFLINE = "The Pulso API didn’t answer. When it runs on your PC, this also means the PC is off.";

/** A failed save's messages, each beside its field: the pct and name 422s, anything else under the form. */
export function fieldErrors(error: unknown): { pct?: string; name?: string; form?: string } {
  if (!isProblem(error)) return { form: OFFLINE };
  const out: { pct?: string; name?: string; form?: string } = {};
  for (const { loc, msg } of error.errors as { loc?: unknown[]; msg?: string }[]) {
    const field = loc?.includes("pct") ? "pct" : loc?.includes("name") ? "name" : "form";
    out[field] ??= msg;
  }
  return Object.keys(out).length ? out : { form: error.detail };
}

export function targetOf(rule: Rule) {
  if (rule.target_type === "test") return { label: "Products in Testing", detail: "every open test", href: "/testing" };
  return {
    label: rule.product_name ?? `Product ${rule.product_id ?? rule.target_id}`,
    detail: rule.target_type === "supplier_offer" ? `offer ${rule.target_id}` : "any supplier",
    href: rule.product_id ? `/products/${rule.product_id}?tab=suppliers` : null,
  };
}

export const threshold = (rule: Rule) => (hasPct(rule.type) ? `±${rule.params.pct ?? 5}%` : null);

/** The last evaluation in words (DEC-040: no source yet, never zero; DEC-335 d: a held gap and its span). */
export function statusLine(rule: Pick<Rule, "status" | "skipped" | "last_evaluated_at">, now: number) {
  if (rule.status === "no_source") return { text: "No source yet", tone: "muted" } as const;
  if (rule.status === "skipped") return { text: `1 evaluation skipped: ${gapSpan(rule.skipped)}`, tone: "warning" } as const;
  if (!rule.status || !rule.last_evaluated_at) return { text: "Not evaluated yet", tone: "muted" } as const;
  return { text: `Evaluated ${formatAgo(rule.last_evaluated_at, now)}`, tone: "ok" } as const;
}

/** "Until unmuted" is a far-future muted_until: the API's null means unmuted. */
export const FOREVER = "9999-01-01T00:00:00Z";
export const MUTES = [
  ["24 hours", 24],
  ["7 days", 168],
  ["Until unmuted", null],
] as const;
export const muteUntil = (hours: number | null, now: number) => (hours === null ? FOREVER : new Date(now + hours * 3_600_000).toISOString());

export function mutedLabel(until: string | null, now: number) {
  if (!until || Date.parse(until) <= now) return null;
  return Date.parse(until) >= Date.parse(FOREVER) ? "Muted until you unmute" : `Muted until ${formatUtc(until)}`;
}
