import { Bell, Gauge, PackageCheck, PackageX, Tag, TrendingUp, Truck, type LucideIcon } from "lucide-react";

import { sourceLabel } from "@/app/(app)/admin/matching/model";
import { money } from "@/app/(app)/products/[id]/profit/model";
import { MAX_QUERY, MIN_QUERY, type SearchView } from "@/components/shell/palette-search";
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
  velocity_spike: { label: "Velocity", icon: TrendingUp, title: "Velocity spiked" },
  saturation_cross: { label: "Saturation", icon: Gauge, title: "Saturation crossed" },
};

interface Value {
  value?: unknown;
  currency?: unknown;
  as_of?: unknown;
  source?: unknown;
}

const humanize = (type: string) => type.replace(/[._]+/g, " ").replace(/^./, (c) => c.toUpperCase());
const stock = (inStock: boolean) => (inStock ? "In stock" : "Out of stock");
const count = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

/** One alert in words: a sentence, the signed % change and old → new where it has them, its source and entity. A
 *  score alert (DEC-353) names its product, reads units /7d or Saturation points, and a velocity rise is good news. */
export function describeAlert(alert: Alert) {
  const type = TYPES[alert.type];
  const { old, new: now, threshold, product } = alert.payload as { old?: Value; new?: Value; threshold?: { threshold?: unknown; direction?: unknown }; product?: unknown };
  const [from, to] = [old?.value, now?.value];
  const currency = typeof now?.currency === "string" ? now.currency : "USD";
  const numbers = typeof from === "number" && typeof to === "number";
  const saturation = alert.type === "saturation_cross";
  const units = saturation || alert.type === "velocity_spike";
  // The engine's own % (pulso_core.alerts.past): from the reference, a 0 reference read as 1.
  const pct = numbers && !saturation ? ((to - from) * 100) / Math.max(from, 1) : null;
  const show = (value: number) => (units ? count.format(value) : money(value, currency));
  const change = numbers
    ? `${show(from)} → ${show(to)}${alert.type === "velocity_spike" ? " /7d" : ""}`
    : typeof from === "boolean" && typeof to === "boolean"
      ? `${stock(from)} → ${stock(to)}`
      : null;
  const crossed = saturation && typeof threshold?.threshold === "number" && `Saturation ${threshold.direction === "below" ? "fell below" : "rose above"} ${threshold.threshold}`;
  const entity =
    typeof product === "string" ? product : alert.entity_type === "supplier_offer" ? `offer ${alert.entity_id}` : `${alert.entity_type.replaceAll("_", " ")} ${alert.entity_id}`;
  return {
    icon: type?.icon ?? Bell,
    title: crossed || (pct !== null && (pct < 0 ? type?.down : type?.up)) || type?.title || humanize(alert.type),
    pct,
    good: alert.type === "velocity_spike" ? ("up" as const) : ("down" as const),
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

export const FIRES =
  "An alert fires once when a supplier’s price or freight moves past a rule’s threshold, an offer runs out of stock or comes back, a product’s velocity spikes or its Saturation crosses a line.";

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

/** The builder's sentence: When [target] [verb] [params]. `target` is "product" (any of its suppliers, or the product
 *  itself for a score rule), a listing id, or "watchlist:<id>" (score rules, DEC-353). */
export interface Draft {
  target: string;
  type: RuleType;
  pct: string;
  name: string;
  minVolume: string;
  threshold: string;
  direction: "above" | "below";
}

export const VERBS: Record<RuleType, string> = {
  supplier_price_change: "changes price by",
  freight_change: "changes freight by",
  supplier_stock_out: "goes out of stock",
  back_in_stock: "comes back in stock",
  velocity_spike: "velocity rises by",
  saturation_cross: "Saturation crosses",
};

export const hasPct = (type: string) => type === "supplier_price_change" || type === "freight_change";
/** Score rules watch a product or a watchlist, not supplier offers (DEC-353). */
export const isScore = (type: string) => type === "velocity_spike" || type === "saturation_cross";
const isStock = (type: string) => type === "supplier_stock_out" || type === "back_in_stock";

/** A new draft's values: a 5% supplier price change, and each score rule's starting params (DEC-353). */
export const DRAFT: Omit<Draft, "name" | "target"> = { type: "supplier_price_change", pct: "5", minVolume: "10", threshold: "65", direction: "above" };
export const defaultPct = (type: string) => (type === "velocity_spike" ? "50" : "5");

// The params go to the API as typed (blank reads 0), so its 422 is the one place a bad value is explained. A stock
// rule sends the API's default, 5, which its evaluation ignores; velocity_spike's window is the API's 7 days.
function paramsOf(draft: Draft): RuleIn["params"] {
  if (draft.type === "velocity_spike") return { pct: Number(draft.pct), min_volume: Number(draft.minVolume) };
  if (draft.type === "saturation_cross") return { threshold: Number(draft.threshold), direction: draft.direction };
  return { pct: hasPct(draft.type) ? Number(draft.pct) : 5 };
}

/** The rule's threshold in words: "±5%", "+50% · ≥10 /7d", "above 65"; null for stock rules. */
function limitOf(type: string, params: { [key: string]: unknown }) {
  if (type === "velocity_spike") return `+${params.pct ?? 50}% · ≥${params.min_volume ?? 10} /7d`;
  if (type === "saturation_cross") return `${params.direction === "below" ? "below" : "above"} ${params.threshold}`;
  return hasPct(type) ? `±${params.pct ?? 5}%` : null;
}

/** The name a rule gets when none is typed, in the Testing defaults' "Scope: what" style. */
export function autoName(draft: Draft, product: string) {
  const limit = limitOf(draft.type, { pct: draft.pct.trim(), min_volume: draft.minVolume.trim(), threshold: draft.threshold.trim(), direction: draft.direction });
  return `${product}: ${TYPES[draft.type].label.toLowerCase()}${limit ? ` ${limit.split(" · ")[0]}` : ""}`;
}

export function createBody(draft: Draft, product: { id: string; name: string }): RuleIn {
  const listed = draft.target.startsWith("watchlist:");
  const [targetType, targetId] = draft.target === "product" ? (["product", product.id] as const) : listed ? (["watchlist", draft.target.slice(10)] as const) : (["supplier_offer", draft.target] as const);
  return {
    name: draft.name.trim() || autoName(draft, product.name),
    type: draft.type,
    target_type: targetType,
    target_id: targetId,
    params: paramsOf(draft),
    enabled: true,
  };
}

/** A rule's type and target are fixed once made (the API's PATCH takes neither). */
export const patchBody = (draft: Draft, rule: Rule) => ({ name: draft.name.trim(), ...(!isStock(rule.type) && { params: paramsOf(draft) }) });

export const draftOf = (rule: Rule): Draft => ({
  ...DRAFT,
  target: rule.target_type === "supplier_offer" ? String(rule.target_id) : "product",
  type: rule.type as RuleType,
  pct: String(rule.params.pct ?? defaultPct(rule.type)),
  minVolume: String(rule.params.min_volume ?? DRAFT.minVolume),
  threshold: String(rule.params.threshold ?? DRAFT.threshold),
  direction: rule.params.direction === "below" ? "below" : "above",
  name: rule.name,
});

const OFFLINE = "The Pulso API didn’t answer. When it runs on your PC, this also means the PC is off.";

type Field = "pct" | "min_volume" | "threshold" | "direction" | "name";
type Errors = Partial<Record<Field | "form", string>>;

/** imp-585: each field's range in words (the API's Params and Name), for Pydantic's out-of-range, wrong-type, missing
 *  and length messages, matched by their `type`. Any other message keeps the API's text. */
const COPY: Record<Field, string> = {
  pct: "Enter a % above 0, up to 1,000.",
  min_volume: "Enter 0 to 1,000,000 units.",
  threshold: "Saturation runs from 0 to 100.",
  direction: "Choose above or below.",
  name: "Give the rule a name, up to 120 characters.",
};
const PLAIN = /^(greater_than|less_than|float_|finite_number|missing|literal_error|string_too_)/;

/** A failed save's messages, each beside its field: the params' and name's 422s, anything else under the form. */
export function fieldErrors(error: unknown): Errors {
  if (!isProblem(error)) return { form: OFFLINE };
  const out: Errors = {};
  for (const { loc, msg, type } of error.errors as { loc?: unknown[]; msg?: string; type?: string }[]) {
    const name = (Object.keys(COPY) as Field[]).find((field) => loc?.includes(field));
    out[name ?? "form"] ??= name && PLAIN.test(type ?? "") ? COPY[name] : msg;
  }
  return Object.keys(out).length ? out : { form: error.detail };
}

// imp-527: the builder's first step from the Rules tab, a product search through the palette's (or a watchlist).

const SEARCHING = { kind: "loading", text: "Searching products…", busy: true } as const;
const noMatch = (term: string) => ({ kind: "empty", text: `No products match “${term}”`, detail: "Try fewer words, or part of a listing’s title." }) as const;

/** The picker's line under its search, from the palette's view counting products only. For results it shows no
 *  line and the text is the live region's (empty while an earlier query's products stay under the spinner). */
export function pickerStatus(view: SearchView, term: string): { kind: string; text: string; detail?: string; busy?: true } {
  switch (view.kind) {
    case "off":
      return { kind: "hint", text: `Type ${MIN_QUERY} or more characters to search products.` };
    case "loading":
      return SEARCHING;
    case "results": {
      const n = view.results.products.length;
      if (!n) return view.stale ? SEARCHING : noMatch(term);
      return view.stale ? { kind: "results", text: "", busy: true } : { kind: "results", text: `${n} ${n === 1 ? "product" : "products"} for “${term}”` };
    }
    case "empty":
      return noMatch(term);
    case "no-source":
      return { kind: "no-source", text: "No products collected yet", detail: "Search fills in once the collectors have run." };
    case "too-long":
      return { kind: "too-long", text: `Too long to search: ${[...term].length} characters`, detail: `Up to ${MAX_QUERY}. Try a few words of the title.` };
    case "error":
      return { kind: "error", text: "Search unavailable", detail: "Retry, or choose Create alert on a product’s page." };
  }
}

export function targetOf(rule: Rule) {
  if (rule.target_type === "test") return { label: "Products in Testing", detail: "every open test", href: "/testing" };
  if (rule.target_type === "watchlist") return { label: rule.watchlist_name ?? "Watchlist", detail: "every product on it", href: `/watchlists?list=${rule.target_id}` };
  const tab = rule.type === "velocity_spike" ? "?tab=trends" : isScore(rule.type) ? "" : "?tab=suppliers";
  return {
    label: rule.product_name ?? `Product ${rule.product_id ?? rule.target_id}`,
    detail: rule.target_type === "supplier_offer" ? `offer ${rule.target_id}` : isScore(rule.type) ? "this product" : "any supplier",
    href: rule.product_id ? `/products/${rule.product_id}${tab}` : null,
  };
}

export const threshold = (rule: Rule) => limitOf(rule.type, rule.params);

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
