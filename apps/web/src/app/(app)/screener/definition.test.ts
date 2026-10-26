import { describe, expect, it } from "vitest";

import { clean, conditionsOf, decode, DEFAULT, encode, same, screenSearch, type Definition } from "./definition";

const EARLY: Definition = {
  filters: { lifecycle: ["emerging", "rising"], margin_bps_min: 4000, ship_days_us_max: 10, velocity_min: 2.5, category: 7 },
  sort: "margin_bps",
  order: "asc",
  columns: ["trend", "margin_bps", "lifecycle"],
};

describe("a screen definition in the URL", () => {
  it("round-trips: decode(encode(d)) equals d", () => {
    for (const d of [DEFAULT, EARLY, { ...DEFAULT, filters: { acceleration_min: -0.25, risk_max: 30 } }]) {
      expect(decode(encode(d))).toEqual(clean(d));
      expect(same(decode(encode(d))!, d)).toBe(true);
    }
    expect(decode(encode(EARLY))).toEqual(EARLY);
  });

  it("is URL-safe base64 without padding", () => {
    expect(encode(EARLY)).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(new URLSearchParams(screenSearch("abc", EARLY)).get("q")).toBe(encode(EARLY));
    expect(screenSearch(null, null)).toBe("");
  });

  it("is equal whatever the key order, and nulls are unset", () => {
    const reordered = { columns: EARLY.columns, order: "asc", sort: "margin_bps", filters: { category: 7, velocity_min: 2.5, ship_days_us_max: 10, margin_bps_min: 4000, lifecycle: ["rising", "emerging"], price_min: null } };
    expect(same(clean(reordered), EARLY)).toBe(true);
    expect(same(EARLY, { ...EARLY, order: "desc" })).toBe(false);
  });

  it("reads a broken or hostile URL as nothing, or keeps only what it knows", () => {
    for (const q of [null, "", "!!", btoa("not json")]) expect(decode(q)).toBeNull();
    expect(decode(btoa("[1]"))).toEqual(DEFAULT); // JSON, but not a definition
    const hostile = { filters: { margin_bps_min: "4000; DROP", price_max: Infinity, lifecycle: ["booming"], category: -1, __proto__x: 1, constructor: 2 }, sort: "risk", order: "sideways", columns: ["toString", "trend", "trend"] };
    expect(clean(hostile)).toEqual({ filters: {}, sort: "trend", order: "desc", columns: ["trend"] });
  });

  it("lists the conditions set, ranges first", () => {
    expect(conditionsOf(EARLY.filters)).toEqual(["margin_bps", "velocity", "ship_days_us", "lifecycle", "category"]);
    expect(conditionsOf({ price_max: 0 })).toEqual(["price"]); // 0 is a bound, not unset
  });
});
