import { useEffect, useState } from "react";
import { keepPreviousData } from "@tanstack/react-query";

import { useApiReady } from "@/components/data-health/api";
import { $api, isProblem } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

// Global search in the Ctrl+K palette (UX-9, DEC-252): the state logic, kept apart from the rows so it can be tested.

export type SearchResults = components["schemas"]["SearchResults"];

/** The API answers nothing under 2 characters, so the palette doesn't ask. */
export const MIN_QUERY = 2;
/** The API's cap once trimmed, in characters (code points, as Python counts), not UTF-16 units. */
export const MAX_QUERY = 100;
export const tooLong = (term: string) => [...term].length > MAX_QUERY;
export const DEBOUNCE_MS = 150;
/** Prefix of every search row's cmdk value: the palette's filter shows those rows for any query. */
export const SEARCH_VALUE = "search:";
/** A search row's cmdk score. Below any real command match, so the search groups sort under the commands. */
export const SEARCH_SCORE = 1e-6;

export function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

export type SearchView =
  | { kind: "off" } // under 2 characters: commands only
  | { kind: "loading" } // nothing to show for this query yet
  | { kind: "results"; results: SearchResults; stale: boolean } // stale: for an earlier query, a newer one is on its way
  | { kind: "empty" }
  | { kind: "no-source" } // nothing has been collected yet
  | { kind: "error" }
  | { kind: "too-long" }; // past the API's cap, such as a pasted product URL: never asked (XR-33)

interface QueryState {
  data?: SearchResults;
  isError: boolean;
  isFetching: boolean;
  isPlaceholderData: boolean;
}

/** GET /v1/search for the typed `term` once typing pauses, and what it shows: the palette's search, and the rule
 *  builder's product picker (imp-527), which share its cache. */
export function useSearch(term: string) {
  const debounced = useDebounced(term, DEBOUNCE_MS);
  const search = $api.useQuery(
    "get",
    "/v1/search",
    { params: { query: { q: debounced } } },
    {
      enabled: useApiReady() && debounced.length >= MIN_QUERY && !tooLong(debounced),
      placeholderData: keepPreviousData, // the last results stay while the next query loads
      staleTime: 60_000,
      // A 4xx won't change on a retry.
      retry: (failures, error) => !(isProblem(error) && error.status < 500) && failures < 1,
    },
  );
  return { search, view: searchView(term, debounced, search) };
}

/** What the search groups show for the typed `term`, given the query for its debounced value. */
export function searchView(term: string, debounced: string, query: QueryState): SearchView {
  if (term.length < MIN_QUERY) return { kind: "off" };
  if (tooLong(term)) return { kind: "too-long" };
  const pending = term !== debounced || query.isFetching;
  const { data } = query;
  if (!data) return query.isError && !pending ? { kind: "error" } : { kind: "loading" };
  const stale = pending || query.isPlaceholderData;
  if (data.products.length + data.stores.length + data.suppliers.length > 0) return { kind: "results", results: data, stale };
  // An empty answer for an earlier query says nothing about this one.
  if (stale) return { kind: "loading" };
  return { kind: data.catalog_empty ? "no-source" : "empty" };
}

const counted = (n: number, noun: string) => (n ? [`${n} ${noun}${n === 1 ? "" : "s"}`] : []);

/** The polite live region's text: settled states only, so typing doesn't chatter. */
export function announce(view: SearchView, term: string): string {
  switch (view.kind) {
    case "results": {
      if (view.stale) return "";
      const { products, stores, suppliers } = view.results;
      const parts = [...counted(products.length, "product"), ...counted(stores.length, "store"), ...counted(suppliers.length, "supplier")];
      const list = parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts.at(-1)}` : parts[0];
      return `${list} for “${term}”`;
    }
    case "empty":
      return `No products, stores or suppliers match “${term}”`;
    case "no-source":
      return "Nothing collected yet. Search fills in once the collectors have run.";
    case "error":
      return "Search unavailable. Commands still work.";
    case "too-long":
      return `Too long to search: up to ${MAX_QUERY} characters.`;
    default:
      return "";
  }
}
