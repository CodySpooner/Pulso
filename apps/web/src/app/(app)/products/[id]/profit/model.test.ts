import { describe, expect, it } from "vitest";

import { cost, exponent, money, needs, parseMinor, pct, priceRange, reasons, request, share, signedMoney, toInput, type Calc } from "./model";

describe("money at the currency exponent", () => {
  it("formats JPY 0, USD 2 and KWD 3 decimals from minor units", () => {
    expect([exponent("JPY"), exponent("USD"), exponent("KWD")]).toEqual([0, 2, 3]);
    expect(money(2999)).toBe("$29.99");
    expect(money(667, "JPY")).toBe("¥667");
    expect(money(1250, "KWD")).toMatch(/^KWD\s1\.250$/);
  });

  it("signs costs and profit with U+2212, never a hyphen; zero is unsigned", () => {
    expect([cost(620), cost(0)]).toEqual(["−$6.20", "$0.00"]);
    expect(signedMoney(3)).toEqual({ glyph: "▲", text: "+$0.03", tone: "positive" });
    expect(signedMoney(-497)).toEqual({ glyph: "▼", text: "−$4.97", tone: "negative" });
    expect(signedMoney(0)).toEqual({ glyph: null, text: "$0.00", tone: "neutral" });
  });

  it("reads basis points as percents and a line as a share of the price", () => {
    expect([pct(290), pct(500), pct(2000), pct(25)]).toEqual(["2.9%", "5%", "20%", "0.25%"]);
    expect([share(620, 2999), share(0, 2999)]).toEqual(["20.7%", "0.0%"]);
  });
});

describe("parseMinor", () => {
  it("reads a typed price as integer minor units, without floats", () => {
    expect(["29.99", "$29.99", " 29.9 ", "29", "1,299.00", "0.07"].map((t) => parseMinor(t))).toEqual([2999, 2999, 2990, 2900, 129900, 7]);
    expect(parseMinor("1250", "JPY")).toBe(1250);
    expect(parseMinor("1.250", "KWD")).toBe(1250);
  });

  it("rejects more decimals than the exponent, signs, words and unsafe integers", () => {
    expect(["29.999", "-5", "abc", "", "1e3", "99999999999999999"].map((t) => parseMinor(t))).toEqual([null, null, null, null, null, null]);
    expect(parseMinor("12.5", "JPY")).toBeNull();
  });

  it("round-trips through the input text", () => {
    expect([toInput(2999), toInput(5), toInput(1250, "JPY"), toInput(1250, "KWD")]).toEqual(["29.99", "0.05", "1250", "1.250"]);
    expect(parseMinor(toInput(123456))).toBe(123456);
  });
});

describe("priceRange", () => {
  it("runs from about half to double in 50-cent steps that keep the anchor's cents", () => {
    expect(priceRange(2999)).toEqual({ min: 1549, max: 5999, step: 50 });
    const { min, max, step } = priceRange(1234);
    expect([(1234 - min) % step, (max - 1234) % step, min >= 617]).toEqual([0, 0, true]);
    expect(priceRange(30).min).toBeGreaterThan(0);
  });
});

describe("request", () => {
  it("sends only the inputs the owner changed", () => {
    const id = "3f6c1e52-8a7d-4b0e-9c21-5d4e8f7a6b13";
    expect(JSON.parse(JSON.stringify(request(id, { quantity: 1 })))).toEqual({ product_id: id, quantity: 1, ddp: false });
    expect(request(id, { quantity: 2, price: 5499, returns: 300, fee: 250, ad: 1200 })).toEqual({
      product_id: id, quantity: 2, ddp: false, price_minor: 5499, returns_bps: 300, payment_fee_bps: 250, ad_cost_minor: 1200,
    });
  });
});

describe("reasons", () => {
  const calc = (over: Partial<Calc>) => ({ quantity: 1, missing: [], ...over }) as Calc;

  it("puts every missing code in plain words, in the API's order", () => {
    const words = reasons(calc({ missing: ["freight_missing", "duty_not_set"] }));
    expect(words).toEqual([
      "Freight isn't quoted for this variant to the US at 1 unit per order.",
      "Duty isn't set: Settings has no US duty rate yet, and Pulso never assumes 0%.",
    ]);
  });

  it("names what a withheld result needs", () => {
    expect(needs(calc({ missing: ["freight_missing", "duty_not_set"] }))).toBe("Needs a freight quote and a duty rate");
    expect(needs(calc({ missing: ["fx_missing"] }))).toBe("Needs a USD exchange rate");
  });

  it("says why a one-unit store price doesn't price a bigger order", () => {
    expect(reasons(calc({ quantity: 3, missing: ["price_missing"] }))[0]).toBe(
      "No sell price for a 3-unit order: a one-unit store price never stands in for it. Enter the order's price.",
    );
    expect(reasons(calc({ missing: ["price_missing"] }))[0]).toMatch(/^No sell price: no store sells it in USD yet/);
  });
});
