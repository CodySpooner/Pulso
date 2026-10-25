import type { components } from "@/lib/api/schema";

// The Trends tab's keyword rules, mirroring POST /v1/products/{id}/keywords (DEC-281), for the optimistic update and
// the add field's message. The API's answer replaces the optimistic list.

export type Keyword = components["schemas"]["Keyword"];
export type TrendsBudget = components["schemas"]["TrendsBudget"];
export type Decision = "confirmed" | "rejected";
export const MAX_KEYWORD_LENGTH = 100;

/** Lower case, a straight apostrophe, spacing collapsed: the API's normal form. */
export const normalizeKeyword = (text: string) => text.replaceAll("’", "'").toLowerCase().split(/\s+/).filter(Boolean).join(" ");

/** The list after deciding `text`: a listed keyword takes the status in place; a new one joins as typed in. Whether it
 *  is tracked waits for the API's answer, which counts the weekly Trends set the way the Monday job does. */
export function decide(list: Keyword[], text: string, status: Decision, now: string): Keyword[] {
  const keyword = normalizeKeyword(text);
  const decided = { status, decided_at: now, tracked: null, untracked_reason: null };
  if (list.some((k) => k.keyword === keyword)) return list.map((k) => (k.keyword === keyword ? { ...k, ...decided } : k));
  return [...list, { keyword, relevance: null, as_of: list[0]?.as_of ?? now, source: "manual", ...decided }];
}

/** A confirmed keyword's place in the weekly Google Trends set (KW-2): its marker's name, and the reason on hover. */
export function tracking(k: Keyword, budget: TrendsBudget): { label: string; reason: string } | null {
  if (k.status !== "confirmed" || k.tracked === null) return null;
  if (k.tracked) return { label: "Tracked", reason: "Tracked: fetched from Google Trends every Monday, 1 SerpApi search a week." };
  if (k.untracked_reason === "budget")
    return { label: "Not tracked: weekly set full", reason: `Not tracked: all ${budget.weekly_cap} weekly slots are used. It's saved, and joins when a slot frees.` };
  if (k.untracked_reason === "comma")
    return { label: "Not tracked: has a comma", reason: "Not tracked: Google Trends takes one keyword per search, and this one has a comma. Add it without the comma." };
  return { label: "Not tracked: tracking is off", reason: "Not tracked: Trends tracking for confirmed keywords is off, so nothing is fetched for them." };
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
