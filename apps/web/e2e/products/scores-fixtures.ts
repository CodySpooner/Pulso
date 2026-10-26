import type { components } from "../../src/lib/api/schema";
import { NOW } from "../data-health/fixtures";

// imp-460: fixture GET /v1/products/{id}/scores responses, never a database restore. The scored day is the day before
// Data Health's NOW (2026-10-22T14:00Z), as the nightly job writes it; its inputs end at 00:00Z.

type S = components["schemas"];
const DAY = "2026-10-21";
const CUTOFF = "2026-10-22T00:00:00Z";
const at = (hoursAgo: number) => new Date(NOW.getTime() - hoursAgo * 3_600_000).toISOString();
const base = { config_digest: "f".repeat(64), cautions: [], penalties: [], missing: [] } satisfies Partial<S["Explanation"]>;
const input = (name: string, family: string, source: string | null, weight: number, more: Partial<S["Component"]> = {}): S["Component"] => ({
  name, family, source, weight, weight_eff: 0, raw: null, z: null, normalization: null, contribution: null, as_of: null, missing: true, gap: false,
  ai_derived: false, prompt_version: null, ...more,
});
/** A present input: weight_eff after renormalisation over `present`, contribution = weight_eff × z. */
const present = (name: string, family: string, source: string, weight: number, presentWeight: number, z: number, raw: number, hoursAgo = 14) =>
  input(name, family, source, weight, { weight_eff: weight / presentWeight, z, raw, contribution: (weight / presentWeight) * z, as_of: at(hoursAgo), missing: false });

// The vault's worked example (Intelligence/Trend Score, Opportunity Score): Trend 68.6, Saturation 73.3, Opportunity 65.7.
const TREND = "000-8236875f835c";
export const trend: S["StoredScore"] = {
  kind: "trend", day: DAY, value: 68.6, stage: null, model_version: TREND, as_of: CUTOFF,
  explanation: {
    ...base, model_version: TREND, coverage: 0.85, missing: ["ads_growth"],
    components: [
      present("shp_inv_g7", "shp_inv", "shopify_stores", 0.4, 0.85, 1.956, 0.368),
      present("shp_inv_acc", "shp_inv", "shopify_stores", 0.2, 0.85, 1.205, 0.268),
      present("gt_slope", "gt_interest", "google_trends", 0.25, 0.85, 1.128, 0.384, 62),
      input("ads_growth", "ads", null, 0.15),
    ],
    penalties: [{ name: "saturation", source: "shopify_stores", raw: 73.3, points: 6.99, missing: false }],
  },
};
const SATURATION = "000-719f633dfc99";
export const saturation: S["StoredScore"] = {
  kind: "saturation", day: DAY, value: 73.3, stage: null, model_version: SATURATION, as_of: CUTOFF,
  explanation: {
    ...base, model_version: SATURATION, coverage: 0.7222, missing: ["ads_active"], panel_size: 41,
    components: [
      present("shp_sellers", "shp_sellers", "shopify_stores", 0.4, 0.65, 1.6, 2.565),
      present("shp_seller_g28", "shp_sellers", "shopify_stores", 0.25, 0.65, 1.08, 0.405),
      input("ads_active", "ads", null, 0.25),
    ],
  },
};
const LIFECYCLE = "000-5a1c0e9f2b7d";
export const lifecycle: S["StoredScore"] = {
  kind: "lifecycle", day: DAY, value: null, stage: "rising", model_version: LIFECYCLE, as_of: CUTOFF,
  explanation: { ...base, model_version: LIFECYCLE, coverage: 1, components: [], reason: "growing", pending: "peaking" },
};
const OPPORTUNITY = "000-de3f6e76320d";
export const opportunity: S["Opportunity"] = {
  value: 65.7, as_of: at(14),
  explanation: {
    ...base, model_version: OPPORTUNITY, coverage: 0.9, confidence: 0.7, cautions: ["duty_not_set"], missing: ["risk"],
    components: [
      present("trend", "momentum", "trend", 0.4, 0.9, 68.6, 68.6),
      present("margin", "margin", "workspace_product_economics", 0.3, 0.9, 87.9, 0.5275, 9),
      present("saturation", "room", "saturation", 0.2, 0.9, 26.7, 73.3),
      input("risk", "safety", null, 0.1),
    ],
  },
};

const page = (latest: S["LatestScores"], o: S["Opportunity"]): S["ProductScores"] => ({
  id: "3f6c1e52-8a7d-4b0e-9c21-5d4e8f7a6b13", range: "7d", start: "2026-10-16", latest, opportunity: o, history: [], next_cursor: null,
});
export const scores = page({ trend, saturation, lifecycle }, opportunity);

const NO_ROW = { value: null, reason: "No source yet: nothing has scored this product." } as const;
/** Nothing has scored the product, and the workspace has no settings: every card reads no source yet. */
export const scoresNone = page(
  { trend: NO_ROW, saturation: NO_ROW, lifecycle: NO_ROW },
  {
    value: null, as_of: null,
    explanation: {
      ...base, model_version: OPPORTUNITY, coverage: 0, confidence: 0, reason: "no trend, margin or saturation yet", missing: ["trend", "margin", "saturation", "risk"],
      components: [input("trend", "momentum", null, 0.4), input("margin", "margin", null, 0.3), input("saturation", "room", null, 0.2), input("risk", "safety", null, 0.1)],
    },
  },
);

const unscored = (kind: S["StoredScore"]["kind"], model_version: string, reason: string): S["StoredScore"] => ({
  kind, day: DAY, value: null, stage: null, model_version, as_of: CUTOFF, explanation: { ...base, model_version, coverage: 0, components: [], reason },
});
/** NULL rows keep their reason; the margin is costed but under the floor, so Opportunity is capped at 25. */
export const scoresUnscored = page(
  { trend: unscored("trend", TREND, "no velocity growth"), saturation: unscored("saturation", SATURATION, "no seller count"), lifecycle: unscored("lifecycle", LIFECYCLE, "insufficient history") },
  {
    value: 25, as_of: at(9),
    explanation: {
      ...base, model_version: OPPORTUNITY, coverage: 0.3, confidence: 0.3, reason: "margin below your floor", missing: ["trend", "saturation", "risk"],
      components: [
        input("trend", "momentum", "trend", 0.4),
        present("margin", "margin", "workspace_product_economics", 0.3, 0.3, 40, 0.24, 9),
        input("saturation", "room", "saturation", 0.2),
        input("risk", "safety", null, 0.1),
      ],
      penalties: [{ name: "margin_floor", source: "workspace_product_economics", raw: 0.24, points: 15, missing: false }],
    },
  },
);
/** The nightly job last ran 5 days ago: each row's as of is stale. */
export const scoresStale = page(
  {
    trend: { ...trend, day: "2026-10-16", as_of: "2026-10-17T00:00:00Z" },
    saturation: { ...saturation, day: "2026-10-16", as_of: "2026-10-17T00:00:00Z" },
    lifecycle: { ...lifecycle, day: "2026-10-16", as_of: "2026-10-17T00:00:00Z" },
  },
  opportunity,
);
