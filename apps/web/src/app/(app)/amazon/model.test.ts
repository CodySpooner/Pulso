import { describe, expect, it } from "vitest";

import type { components } from "@/lib/api/schema";

import { groupRows } from "./model";

type Row = components["schemas"]["AmazonRankRow"];

const row = (category: string, rank_kind: Row["rank_kind"], rank: number) => ({ category, rank_kind, rank }) as Row;
const shape = (rows: Row[]) => groupRows(rows).map((g) => [g.category, g.kind, g.rows.map((r) => r.rank)]);

describe("groupRows (DEC-286)", () => {
  it("gives each category and rank kind its own group, so two rank 1s never meet", () => {
    const rows = [row("Home", "bsr", 1), row("Home", "bsr", 2), row("Home", "movers", 1), row("Toys", "bsr", 1)];
    expect(shape(rows)).toEqual([
      ["Home", "bsr", [1, 2]],
      ["Home", "movers", [1]],
      ["Toys", "bsr", [1]],
    ]);
  });

  it("keeps a list cut by a page boundary as one group", () => {
    const pages = [[row("Home", "bsr", 1), row("Home", "bsr", 2)], [row("Home", "bsr", 3)]];
    expect(shape(pages.flat())).toEqual([["Home", "bsr", [1, 2, 3]]]);
    expect(groupRows([])).toEqual([]);
  });
});
