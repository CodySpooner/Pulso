import type { components } from "@/lib/api/schema";

// How a score's explanation reads on screen (imp-460, DEC-351; vault Intelligence/Score Definitions §7). The Product
// Page cards use it today; Discover's Trend cell and the Screener read the same wording.

export type Explanation = components["schemas"]["Explanation"];
type Input = components["schemas"]["Component"];
export type ScoreKind = "trend" | "saturation" | "opportunity";

// Trend and Saturation are 50 + 50 × Σ contribution / 3, so an input is 50/3 × its contribution in points (vault Trend
// Score). Opportunity's inputs hold their 0–100 values, so its contributions are already points (DEC-331 a).
const POINTS: Record<ScoreKind, number> = { trend: 50 / 3, saturation: 50 / 3, opportunity: 1 };

// Inputs by name; a demand family's G7 and acceleration name the family (`cj_stock_g7`).
const INPUTS: Record<string, string> = {
  g7: "Velocity growth",
  acc: "Acceleration",
  v7: "Velocity 7d",
  v7_prev: "Velocity, week before",
  gt_slope: "Search-interest slope",
  ads_growth: "Ad-count growth",
  shp_sellers: "Stores selling it",
  shp_seller_g28: "Seller growth 28d",
  ads_active: "Active ads",
  trend: "Momentum (Trend Score)",
  margin: "Margin vs your floor",
  saturation: "Room (100 − Saturation)",
  risk: "Safety (100 − Risk)",
  days_observed: "Days observed",
  age_days: "Days since launch",
};
const PENALTIES: Record<string, string> = { saturation: "Saturation penalty", margin_floor: "Margin below your floor" };
const FAMILIES: Record<string, string> = { cj_stock: "CJ stock", shp_inv: "Shopify inventory", shp_bump: "Shopify bumps" };
// A component's `source` is a sources.key, a score kind or the economics view (DEC-331 e).
const SOURCES: Record<string, string> = {
  cj: "CJ Dropshipping",
  shopify_stores: "Shopify stores",
  google_trends: "Google Trends",
  trend: "Trend Score",
  saturation: "Saturation",
  workspace_product_economics: "Your landed margin",
};

export const sourceLabel = (key: string) => SOURCES[key] ?? key;

export function inputLabel(name: string): string {
  if (INPUTS[name]) return INPUTS[name];
  const family = Object.keys(FAMILIES).find((f) => name.startsWith(`${f}_`));
  const rest = family ? name.slice(family.length + 1) : name;
  return family && INPUTS[rest] ? `${INPUTS[rest]} (${FAMILIES[family]})` : name;
}

/** Missing with no source reads "no source yet"; missing with one, "insufficient signal" (Score Definitions §7). */
export const missingWord = (source: string | null) => (source === null ? "No source yet" : "Insufficient signal");

export interface Reason {
  name: string;
  label: string;
  points: number;
  source: string;
  asOf: string | null;
  gap: boolean;
}

/** The three largest |contribution| among present inputs, in points (vault Trend Score, "top 3 reasons"). */
export function topReasons(e: Explanation, kind: ScoreKind, n = 3): Reason[] {
  return e.components
    .filter((c): c is Input & { contribution: number; source: string } => c.contribution != null && c.source !== null)
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    .slice(0, n)
    .map((c) => ({ name: c.name, label: inputLabel(c.name), points: POINTS[kind] * c.contribution, source: c.source, asOf: c.as_of ?? null, gap: c.gap ?? false }));
}

/** Each penalty as its own waterfall step: points off (negative), or its missing wording. */
export const penaltySteps = (e: Explanation) =>
  e.penalties.map((p) => ({
    name: p.name,
    label: PENALTIES[p.name] ?? p.name,
    points: p.missing || p.points == null ? null : -p.points,
    missing: p.missing ? missingWord(p.source) : null,
    source: p.source,
  }));

/** Missing inputs by wording, in the explanation's order. */
export function missingInputs(e: Explanation): { word: string; labels: string[] }[] {
  const groups = new Map<string, string[]>();
  for (const c of e.components.filter((c) => c.missing)) {
    const word = missingWord(c.source);
    groups.set(word, [...(groups.get(word) ?? []), inputLabel(c.name)]);
  }
  return [...groups].map(([word, labels]) => ({ word, labels }));
}

/** Confidence once the score has one (Opportunity, DEC-331 d); until freshness is built, the others show coverage. */
export function certainty(e: Explanation): { label: "Confidence" | "Coverage"; value: number; grade: string } {
  const value = e.confidence ?? e.coverage;
  // Grades from vault Features/Methodology & Confidence (thresholds a guess).
  const grade = value >= 0.75 ? "High" : value >= 0.5 ? "Medium" : "Low";
  return { label: e.confidence == null ? "Coverage" : "Confidence", value, grade };
}

/** The chips a score raises: duty not set (amber, from `cautions`) and the margin floor (from `reason`). */
export function chips(e: Explanation): string[] {
  return [
    ...(e.cautions.includes("duty_not_set") ? ["Duty not set"] : []),
    ...(e.reason === "margin below your floor" && e.penalties.some((p) => p.name === "margin_floor") ? ["Margin below your floor"] : []),
  ];
}

type Scored = { day: string; value: number | null; stage?: string | null; reason?: string | null; explanation?: { reason?: string | null } };
const insufficient = (reason?: string | null) => (reason ? `Insufficient signal · ${reason}` : "Insufficient signal");

/** What a card or cell says instead of a number: no row is "No source yet", a NULL row "Insufficient signal · why". */
export function unscored(latest: Scored | { reason: string }): string | null {
  if (!("day" in latest)) return "No source yet";
  if (latest.value != null || latest.stage) return null;
  return insufficient(latest.explanation?.reason ?? latest.reason);
}

/** Opportunity has no row: with no value, it's no source yet when no input has a source, else insufficient signal. */
export function unscoredOpportunity(value: number | null, e: Explanation): string | null {
  if (value != null) return null;
  return e.components.every((c) => c.source === null) ? "No source yet" : insufficient(e.reason);
}
