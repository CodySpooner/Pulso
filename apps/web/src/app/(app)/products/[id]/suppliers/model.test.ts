import { describe, expect, it } from "vitest";

import type { Calc } from "../profit/model";
import { days, noBestMargin, noFastest, parseSupplier, shared, short, stars, supplierSearch, type Page, type Row } from "./model";

const cost = (over: Partial<Calc> = {}) => ({ complete: true, missing: [], quantity: 1, ...over }) as Calc;
const row = (over: Partial<Row> = {}) => ({ listing_id: 1, in_stock: true, cost: cost(), ...over }) as Row;
const page = (rows: Row[], best: Row | null = null, fastest: Row | null = null) => ({ rows, picks: { best_margin: best, fastest } }) as Page;

describe("the chosen supplier in the URL", () => {
  it("reads a positive integer id only", () => {
    expect(parseSupplier(new URLSearchParams("tab=profit&supplier=88123"))).toBe(88123);
    for (const bad of ["", "0", "-4", "12a", "1.5", "007", "99999999999999999999"]) expect(parseSupplier(new URLSearchParams(`supplier=${bad}`))).toBeNull();
  });

  it("sets and drops it, keeping every other parameter", () => {
    expect(supplierSearch("?tab=suppliers&sellers=all", 88123)).toBe("tab=suppliers&sellers=all&supplier=88123");
    expect(supplierSearch("tab=profit&supplier=1", null)).toBe("tab=profit");
  });
});

describe("words", () => {
  it("days read as a range, one number or an open end", () => {
    expect([days(8, 12), days(5, 5), days(null, 9), days(8, null), days(null, null)]).toEqual(["8–12 d", "5 d", "9 d", "8+ d", null]);
  });

  it("a withheld margin names its first missing input", () => {
    expect(short(cost({ complete: false, missing: ["freight_missing", "duty_not_set"] }))).toBe("Freight not quoted");
    expect(short(cost({ complete: false, missing: ["price_missing"] }))).toBe("No market price");
  });

  it("stars from hundredths", () => {
    expect([stars(470), stars(500), stars(399)]).toEqual(["4.7", "5.0", "4.0"]);
  });
});

describe("page-wide gaps and empty picks", () => {
  const noPrice = cost({ complete: false, missing: ["price_missing"] });
  it("explains once what every row lacks: a market price or duty, never a per-supplier gap", () => {
    const rows = [row({ cost: cost({ complete: false, missing: ["price_missing", "freight_missing"] }) }), row({ cost: noPrice })];
    expect(shared(rows)).toEqual(["price_missing"]);
    expect(shared([row({ cost: noPrice }), row()])).toEqual([]);
    expect(shared([])).toEqual([]);
  });

  it("says why no supplier wins Best margin", () => {
    const quoted = row({ cost: cost({ complete: false, missing: ["duty_not_set"] }) });
    expect(noBestMargin(page([quoted, row({ in_stock: false })]))).toBe("No supplier has complete costs. Needs a duty rate.");
    expect(noBestMargin(page([row({ in_stock: false })]))).toBe("Every supplier is out of stock.");
    expect(noBestMargin(page([row()], row()))).toBeNull();
    expect(noBestMargin(page([]))).toBeNull();
    expect(noFastest(page([row()]))).toMatch(/no in-stock supplier has a US freight quote/i);
    expect(noFastest(page([row()], null, row()))).toBeNull();
  });
});
