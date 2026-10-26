import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { components } from "@/lib/api/schema";

import { ScoreExplanation } from "./score-explanation";
import { certainty, chips, inputLabel, missingInputs, penaltySteps, sourceLabel, topReasons, unscored, unscoredOpportunity, type Explanation } from "./score-model";

type Input = components["schemas"]["Component"];
const input = (name: string, source: string | null, contribution: number | null, more: Partial<Input> = {}): Input => ({
  name, family: "f", source, weight: 0.25, contribution, missing: contribution === null, ...more,
});
const explanation = (more: Partial<Explanation> = {}): Explanation => ({
  model_version: "000-8236875f835c", config_digest: "f".repeat(64), components: [], missing: [], coverage: 0.85, penalties: [], cautions: [], ...more,
});
// The vault's worked example (Intelligence/Trend Score), plus a negative input bigger than the smallest positive one.
const trend = explanation({
  components: [
    input("shp_inv_g7", "shopify_stores", 0.9205, { as_of: "2026-10-22T00:00:00Z" }),
    input("shp_inv_acc", "shopify_stores", 0.2835),
    input("gt_slope", "google_trends", 0.3318),
    input("shp_bump_g7", "shopify_stores", -0.45),
    input("ads_growth", null, null),
  ],
  missing: ["ads_growth"],
  penalties: [{ name: "saturation", source: "shopify_stores", raw: 73.3, points: 6.99, missing: false }],
});
const render = (kind: "trend" | "saturation" | "opportunity", e: Explanation) =>
  renderToStaticMarkup(createElement(TooltipProvider, null, createElement(ScoreExplanation, { kind, explanation: e })));
const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

describe("topReasons", () => {
  test("picks the three largest |contribution|, in points = 50/3 × contribution", () => {
    const reasons = topReasons(trend, "trend");
    expect(reasons.map((r) => r.name)).toEqual(["shp_inv_g7", "shp_bump_g7", "gt_slope"]);
    expect(reasons.map((r) => r.points)).toEqual([0.9205, -0.45, 0.3318].map((c) => (50 / 3) * c));
    expect(reasons[0]).toMatchObject({ label: "Velocity growth (Shopify inventory)", source: "shopify_stores", asOf: "2026-10-22T00:00:00Z" });
  });

  test("Opportunity's contributions are already points, and a missing input never ranks", () => {
    const o = explanation({ components: [input("trend", "trend", 30.49), input("margin", "workspace_product_economics", 29.3), input("risk", null, null)] });
    expect(topReasons(o, "opportunity").map((r) => [r.label, r.points])).toEqual([
      ["Momentum (Trend Score)", 30.49],
      ["Margin vs your floor", 29.3],
    ]);
  });

  test("render signed, with a glyph, never colour alone", () => {
    const html = render("trend", trend);
    expect(text(html)).toContain("▲ Velocity growth (Shopify inventory) +15.3 points");
    expect(text(html)).toContain("▼ Velocity growth (Shopify bumps) −7.5 points");
    // Saturation is worse when higher, so a rising input reads negative.
    expect(render("saturation", explanation({ components: [input("shp_sellers", "shopify_stores", 0.98)] }))).toMatch(/text-negative[^>]*>\+16\.3/);
  });
});

describe("penalties", () => {
  test("each penalty is its own step after the reasons", () => {
    expect(penaltySteps(trend)).toEqual([{ name: "saturation", label: "Saturation penalty", points: -6.99, missing: null, source: "shopify_stores" }]);
    const html = text(render("trend", trend));
    expect(html).toMatch(/Top reasons .* Penalty ▼ Saturation penalty −7\.0 points/);
  });

  test("a missing penalty reads by its source, takes nothing off and shows no number", () => {
    const e = explanation({ penalties: [{ name: "saturation", source: "shopify_stores", raw: null, points: null, missing: true }] });
    expect(penaltySteps(e)[0]).toMatchObject({ points: null, missing: "Insufficient signal" });
    expect(text(render("trend", e))).toContain("Saturation penalty Insufficient signal");
  });

  test("the margin floor cut is a step, and its chip comes from reason + the penalty", () => {
    const capped = explanation({
      reason: "margin below your floor",
      penalties: [{ name: "margin_floor", source: "workspace_product_economics", raw: 0.24, points: 15, missing: false }],
    });
    expect(text(render("opportunity", capped))).toContain("Margin below your floor −15.0 points");
    expect(chips(capped)).toEqual(["Margin below your floor"]);
    expect(chips(explanation({ reason: "margin below your floor" }))).toEqual([]);
  });
});

describe("what reads instead of a number", () => {
  test("ads_growth, with no source, is no source yet; a missing input with one is insufficient signal", () => {
    const e = explanation({ components: [input("ads_growth", null, null), input("cj_stock_acc", "cj", null)], missing: ["ads_growth", "cj_stock_acc"] });
    expect(missingInputs(e)).toEqual([
      { word: "No source yet", labels: ["Ad-count growth"] },
      { word: "Insufficient signal", labels: ["Acceleration (CJ stock)"] },
    ]);
    expect(text(render("trend", e))).toContain("No source yet: Ad-count growth");
  });

  test("a NULL row is insufficient signal with its reason; no row is no source yet", () => {
    const row = { day: "2026-10-21", value: null, stage: null, explanation: { reason: "no velocity growth" } };
    expect(unscored(row)).toBe("Insufficient signal · no velocity growth");
    expect(unscored({ day: "2026-10-21", value: null, reason: "no velocity growth" })).toBe("Insufficient signal · no velocity growth"); // Discover's
    expect(unscored({ ...row, explanation: {} })).toBe("Insufficient signal");
    expect(unscored({ reason: "No source yet: nothing has scored this product." })).toBe("No source yet");
    expect(unscored({ day: "2026-10-21", value: 68.6, reason: null })).toBeNull();
    expect(unscored({ ...row, stage: "rising" })).toBeNull(); // a lifecycle row has a stage, not a value
  });

  test("Opportunity with no value is no source yet only when nothing has a source", () => {
    const none = explanation({ components: [input("trend", null, null), input("margin", null, null)], reason: "no trend, margin or saturation yet" });
    expect(unscoredOpportunity(null, none)).toBe("No source yet");
    const nullRow = explanation({ components: [input("trend", "trend", null), input("margin", null, null)], reason: "no trend, margin or saturation yet" });
    expect(unscoredOpportunity(null, nullRow)).toBe("Insufficient signal · no trend, margin or saturation yet");
    expect(unscoredOpportunity(65.7, nullRow)).toBeNull();
  });

  test("duty not set is an amber caution, from cautions", () => {
    expect(chips(explanation({ cautions: ["duty_not_set"] }))).toEqual(["Duty not set"]);
  });
});

describe("labels and certainty", () => {
  test("confidence once the score has one, else coverage", () => {
    expect(certainty(explanation({ confidence: 0.7 }))).toEqual({ label: "Confidence", value: 0.7, grade: "Medium" });
    expect(certainty(explanation())).toEqual({ label: "Coverage", value: 0.85, grade: "High" });
    expect(text(render("trend", trend))).toContain("Coverage 85% High");
  });

  test("sources and inputs read as words; an unknown one keeps its key", () => {
    expect(["trend", "saturation", "workspace_product_economics", "cj", "new_source"].map(sourceLabel)).toEqual([
      "Trend Score", "Saturation", "Your landed margin", "CJ Dropshipping", "new_source",
    ]);
    expect(["cj_stock_g7", "gt_slope", "shp_seller_g28", "new_input"].map(inputLabel)).toEqual(["Velocity growth (CJ stock)", "Search-interest slope", "Seller growth 28d", "new_input"]);
  });
});
