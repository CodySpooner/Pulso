import type { InfiniteData } from "@tanstack/react-query";

import type { components } from "@/lib/api/schema";

type Page = components["schemas"]["PopularPage"];
type Row = components["schemas"]["PopularRow"];
export type Action = "hide" | "show";

/** The row's brand rule as the page reads it: a shown major brand has a show rule, a hidden one a hide rule (DEC-277). */
export const ruleOf = (row: Row): Action | null => (row.hidden_by === "you" ? "hide" : row.major_brand && row.hidden_by === null ? "show" : null);

/** Rows of `brand` once its rule is `next`: patched in place with every brand shown, else dropped when hidden. */
export function patchPages(data: InfiniteData<Page>, brand: string, next: Action | null, all: boolean): InfiniteData<Page> {
  const norm = brand.toLowerCase();
  return {
    ...data,
    pages: data.pages.map((page) => ({
      ...page,
      rows: page.rows.flatMap((row) => {
        if (row.brand?.toLowerCase() !== norm) return [row];
        const hidden_by = next === "hide" ? "you" : next === null && row.major_brand ? "major" : null;
        return !all && hidden_by ? [] : [{ ...row, hidden_by }];
      }),
    })),
  };
}
