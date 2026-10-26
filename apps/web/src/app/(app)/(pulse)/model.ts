import type { components } from "@/lib/api/schema";

// Pure helpers for the Daily Pulse page (WF-6b, DEC-342) on GET /v1/pulse (DEC-337). A day is the UTC calendar date.

export type Pulse = components["schemas"]["Pulse"];
export type Sections = Pulse["sections"];
export type Section = Sections[keyof Sections];
export type CardId = Exclude<keyof Sections, "movers_up" | "movers_down"> | "movers";

const DAY = 86_400_000;

/** `?date=` when it names a real YYYY-MM-DD day; anything else reads as the latest day. */
export const dayParam = (raw: string | null) => (raw && /^\d{4}-\d{2}-\d{2}$/.test(raw) && !Number.isNaN(Date.parse(raw)) ? raw : null);

export const shiftDay = (day: string, by: number) => new Date(Date.parse(day) + by * DAY).toISOString().slice(0, 10);

export const utcDay = (ms: number) => new Date(ms).toISOString().slice(0, 10);

/** Stale (vault Design/UI States): the section's as of is more than 1.5 daily intervals before the day's cutoff. */
export const isStale = (asOf: string | null, cutoff: string) => asOf !== null && Date.parse(cutoff) - Date.parse(asOf) > 1.5 * DAY;

/** The latest scored day is before yesterday: the nightly scoring hasn't run since, so the collector host may be off. */
export const isBehind = (day: string, now: number) => day < shiftDay(utcDay(now), -1);

const SOURCES: Record<string, string> = {
  trend: "Trend Score",
  lifecycle: "Lifecycle",
  alerts: "Alerts",
  shopify_stores: "Shopify stores",
  cj: "CJ Dropshipping",
  google_trends: "Google Trends",
  workspace_product_economics: "Landed cost",
};
export const sourceNames = (keys: string[]) => keys.map((key) => SOURCES[key] ?? key).join(" · ");

export const sectionOf = (sections: Sections, id: CardId) => (id === "movers" ? sections.movers_up : sections[id]);

const CARDS: CardId[] = ["emerging", "movers", "new_in_stores", "alerts", "watchlists", "suppliers", "search", "margins"];

/** Card order: unread alerts lead (the note's phone order), populated sections next, no-source sections last. */
export function cardOrder(sections: Sections): CardId[] {
  const rank = (id: CardId) => (id === "alerts" && sections.alerts.unread > 0 ? -1 : sectionOf(sections, id).status === "no_source" ? 1 : 0);
  return [...CARDS].sort((a, b) => rank(a) - rank(b));
}

/** The sparkline's values over the 14 days to `day`, oldest first: a day without a score is null, so the line breaks. */
export function seriesValues(series: { day: string; value: number }[], day: string, days = 14): (number | null)[] {
  const byDay = new Map(series.map((point) => [point.day, point.value]));
  return Array.from({ length: days }, (_, i) => byDay.get(shiftDay(day, i - days + 1)) ?? null);
}
