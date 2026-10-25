import { describe, expect, it } from "vitest";

import type { components } from "@/lib/api/schema";

import { patchPages, ruleOf } from "./model";

type Row = components["schemas"]["PopularRow"];
type Page = components["schemas"]["PopularPage"];

const row = (rank: number, brand: string | null, major = false, hidden_by: Row["hidden_by"] = null) => ({ rank, brand, major_brand: major, hidden_by }) as Row;
const pages = (...rows: Row[]) => ({ pages: [{ rows: rows.slice(0, 2) }, { rows: rows.slice(2) }] as Page[], pageParams: [null, "2"] });
const ranks = (data: { pages: Page[] }) => data.pages.flatMap((p) => p.rows.map((r) => [r.rank, r.hidden_by]));

describe("patchPages (DEC-277 optimistic update)", () => {
  const data = pages(row(1, "Acme"), row(2, "Indie"), row(3, "ACME"), row(4, null), row(5, "BigCo", true, "major"));

  it("drops every spelling of a brand you hide from every loaded page, unless every brand is shown", () => {
    expect(ranks(patchPages(data, "acme", "hide", false))).toEqual([[2, null], [4, null], [5, "major"]]);
    expect(ranks(patchPages(data, "acme", "hide", true))).toEqual([[1, "you"], [2, null], [3, "you"], [4, null], [5, "major"]]);
  });

  it("clears a rule back to the major-brand rule, and a show rule exempts a major brand", () => {
    const hidden = pages(row(1, "Acme", false, "you"), row(5, "BigCo", true, "you"));
    expect(ranks(patchPages(hidden, "Acme", null, true))).toEqual([[1, null], [5, "you"]]);
    expect(ranks(patchPages(hidden, "bigco", null, true))).toEqual([[1, "you"], [5, "major"]]);
    expect(ranks(patchPages(hidden, "bigco", "show", false))).toEqual([[1, "you"], [5, null]]);
  });
});

describe("ruleOf", () => {
  it("reads the rule a row's flags imply", () => {
    expect(ruleOf(row(1, "Acme", false, "you"))).toBe("hide");
    expect(ruleOf(row(1, "BigCo", true, null))).toBe("show");
    expect(ruleOf(row(1, "BigCo", true, "major"))).toBeNull();
    expect(ruleOf(row(1, "Acme"))).toBeNull();
  });
});
