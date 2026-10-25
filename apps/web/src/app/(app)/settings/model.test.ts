import { describe, expect, test } from "vitest";

import {
  apiFieldErrors,
  bpsToPercent,
  dollarsToMinor,
  errors,
  fieldError,
  isDirty,
  minorToDollars,
  percentToBps,
  toBody,
  toDraft,
  type Draft,
  type Settings,
} from "./model";

const saved: Settings = {
  workspace_id: "5d0e7a8c-1b2f-4c3d-9e8f-7a6b5c4d3e2f",
  default_country: "US",
  currency: "USD",
  payment_fee_bps: 290,
  payment_fee_fixed_minor: 30,
  shopify_fee_bps: 0,
  default_cpa_minor: 1500,
  target_margin_bps: 2000,
  duty_default_bps: null,
  returns_bps: 500,
  customs_fee_minor: 0,
};
const edit = (draft: Draft, values: Partial<Draft["values"]>, dutySet = draft.dutySet): Draft => ({ values: { ...draft.values, ...values }, dutySet });

describe("percent ↔ basis points", () => {
  test.each([
    ["2.9", 290],
    ["2.90", 290],
    ["0.05", 5],
    [".5", 50],
    ["5.", 500],
    ["100", 10_000],
    [" 20 ", 2000],
    ["0", 0],
    ["1000", 100_000],
  ])("%s%% is %i bps", (text, bps) => {
    expect(percentToBps(text)).toBe(bps);
  });

  test.each(["", ".", "-1", "2.999", "1e2", "2,9", "abc", "12345678"])("%j is not a percentage", (text) => {
    expect(percentToBps(text)).toBeNull();
  });

  test.each([
    [290, "2.9"],
    [2000, "20"],
    [5, "0.05"],
    [250, "2.5"],
    [0, "0"],
    [100_000, "1000"],
    [10_001, "100.01"],
  ])("%i bps reads %s", (bps, text) => {
    expect(bpsToPercent(bps)).toBe(text);
    expect(percentToBps(text)).toBe(bps);
  });

  test("every bps round-trips exactly, with no float drift", () => {
    for (let bps = 0; bps <= 10_000; bps++) expect(percentToBps(bpsToPercent(bps))).toBe(bps);
  });
});

describe("dollars ↔ minor units", () => {
  test.each([
    ["0.30", 30],
    ["15", 1500],
    ["15.5", 1550],
    ["0.07", 7],
    ["999999999.99", 99_999_999_999],
  ])("$%s is %i cents", (text, minor) => {
    expect(dollarsToMinor(text)).toBe(minor);
  });

  test.each(["", "-0.30", "0.305", "$1", "1,000", "1000000000"])("%j is not an amount", (text) => {
    expect(dollarsToMinor(text)).toBeNull();
  });

  test.each([
    [30, "0.30"],
    [1500, "15.00"],
    [7, "0.07"],
    [0, "0.00"],
  ])("%i cents reads $%s", (minor, text) => {
    expect(minorToDollars(minor)).toBe(text);
    expect(dollarsToMinor(text)).toBe(minor);
  });
});

describe("validation", () => {
  const draft = toDraft(saved);

  test("saved settings are valid and not dirty", () => {
    expect(errors(draft)).toEqual({});
    expect(isDirty(draft, saved)).toBe(false);
    expect(isDirty(edit(draft, { payment_fee_bps: "2.90", payment_fee_fixed_minor: "0.3" }), saved)).toBe(false);
  });

  test.each([
    ["payment_fee_bps", "", "Enter a percentage. Use 0 for none."],
    ["payment_fee_bps", "-1", "Can't be negative."],
    ["payment_fee_bps", "2.999", "Use at most 2 decimals."],
    ["payment_fee_bps", "abc", "Enter a number, like 2.9."],
    ["returns_bps", "100.01", "Enter 100% or less."],
    ["target_margin_bps", "101", "Enter 100% or less."],
    ["payment_fee_fixed_minor", "", "Enter an amount. Use 0 for none."],
    ["payment_fee_fixed_minor", "0.305", "Use whole cents: at most 2 decimals."],
    ["default_cpa_minor", "$15", "Enter an amount in dollars, like 0.30."],
    ["customs_fee_minor", "-2", "Can't be negative."],
  ] as const)("%s = %j: %s", (key, text, message) => {
    const bad = edit(draft, { [key]: text });
    expect(fieldError(bad, key)).toBe(message);
    expect(toBody(bad)).toBeNull();
  });

  test("100% and 0 are allowed; duty can pass 100% up to 1,000%", () => {
    const set = edit(draft, { returns_bps: "100", shopify_fee_bps: "0", duty_default_bps: "150" }, true);
    expect(errors(set)).toEqual({});
    expect(fieldError(edit(set, { duty_default_bps: "1000.01" }), "duty_default_bps")).toBe("Enter 1,000% or less.");
  });
});

describe("duty: not set is never 0", () => {
  test("a null duty opens unset with an empty box and sends null", () => {
    const draft = toDraft(saved);
    expect(draft.dutySet).toBe(false);
    expect(draft.values.duty_default_bps).toBe("");
    expect(toBody(draft)?.duty_default_bps).toBeNull();
  });

  test("setting it needs a rate; 0% is a rate and is sent as 0", () => {
    const set = edit(toDraft(saved), {}, true);
    expect(fieldError(set, "duty_default_bps")).toBe("Enter a duty rate. 0% is a valid rate.");
    expect(isDirty(set, saved)).toBe(true);
    const zero = edit(set, { duty_default_bps: "0" });
    expect(toBody(zero)?.duty_default_bps).toBe(0);
  });

  test("a saved 0% opens set, and unsetting it is a change to null", () => {
    const zero = { ...saved, duty_default_bps: 0 };
    const draft = toDraft(zero);
    expect([draft.dutySet, draft.values.duty_default_bps]).toEqual([true, "0"]);
    const unset = edit(draft, {}, false);
    expect(isDirty(unset, zero)).toBe(true);
    expect(toBody(unset)?.duty_default_bps).toBeNull();
  });
});

test("the body carries every editable field in API units", () => {
  const draft = edit(toDraft(saved), { payment_fee_bps: "3.4", default_cpa_minor: "12.5", duty_default_bps: "25" }, true);
  expect(toBody(draft)).toEqual({
    payment_fee_bps: 340,
    payment_fee_fixed_minor: 30,
    shopify_fee_bps: 0,
    default_cpa_minor: 1250,
    target_margin_bps: 2000,
    duty_default_bps: 2500,
    returns_bps: 500,
    customs_fee_minor: 0,
  });
});

test("API 422 errors map to the fields they name; others are dropped", () => {
  expect(
    apiFieldErrors([
      { loc: ["body", "returns_bps"], msg: "Input should be less than or equal to 10000", type: "less_than_equal" },
      { loc: ["body", "returns_bps"], msg: "second", type: "x" },
      { loc: ["body", "workspace_id"], msg: "Extra inputs are not permitted", type: "extra_forbidden" },
      { loc: ["body"], msg: "x", type: "x" },
    ]),
  ).toEqual({ returns_bps: "Input should be less than or equal to 10000" });
});
