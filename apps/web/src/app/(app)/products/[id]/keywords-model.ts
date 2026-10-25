import type { components } from "@/lib/api/schema";

// The Trends tab's keyword rules, mirroring POST /v1/products/{id}/keywords (DEC-281), for the optimistic update and
// the add field's message. The API's answer replaces the optimistic list.

export type Keyword = components["schemas"]["Keyword"];
export type Decision = "confirmed" | "rejected";
export const MAX_KEYWORD_LENGTH = 100;

/** Lower case, a straight apostrophe, spacing collapsed: the API's normal form. */
export const normalizeKeyword = (text: string) => text.replaceAll("’", "'").toLowerCase().split(/\s+/).filter(Boolean).join(" ");

/** The list after deciding `text`: a listed keyword takes the status in place; a new one joins as typed in. */
export function decide(list: Keyword[], text: string, status: Decision, now: string): Keyword[] {
  const keyword = normalizeKeyword(text);
  if (list.some((k) => k.keyword === keyword)) return list.map((k) => (k.keyword === keyword ? { ...k, status, decided_at: now } : k));
  return [...list, { keyword, relevance: null, as_of: list[0]?.as_of ?? now, source: "manual", status, decided_at: now }];
}

/** Why a typed keyword can't be added, or null when it can. */
export function checkKeyword(list: Keyword[], text: string): string | null {
  const keyword = normalizeKeyword(text);
  if (!keyword) return "Type the words a shopper would search.";
  if (!/[\p{L}\p{N}]/u.test(keyword)) return "A keyword needs at least one letter or digit.";
  if (text.trim().length > MAX_KEYWORD_LENGTH) return `Keywords are ${MAX_KEYWORD_LENGTH} characters at most.`;
  if (list.some((k) => k.keyword === keyword && k.status === "confirmed")) return `“${keyword}” is already confirmed.`;
  return null;
}
