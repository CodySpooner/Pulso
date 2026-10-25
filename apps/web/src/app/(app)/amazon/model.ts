import type { components } from "@/lib/api/schema";

type Row = components["schemas"]["AmazonRankRow"];
export type Kind = Row["rank_kind"];

export const KINDS: Record<Kind, string> = { bsr: "Best Sellers", movers: "Movers & Shakers" };

export interface Group {
  category: string;
  kind: Kind;
  rows: Row[];
}

/** Rows, ordered by list then rank as the API pages them, split into one group per category × rank kind: a rank only
 * compares within its own list (DEC-286). A list cut by a page boundary stays one group. */
export function groupRows(rows: Row[]): Group[] {
  const groups: Group[] = [];
  for (const row of rows) {
    const last = groups.at(-1);
    if (last?.category === row.category && last.kind === row.rank_kind) last.rows.push(row);
    else groups.push({ category: row.category, kind: row.rank_kind, rows: [row] });
  }
  return groups;
}
