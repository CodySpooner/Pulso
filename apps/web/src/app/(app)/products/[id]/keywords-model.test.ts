import { describe, expect, test } from "vitest";

import { checkKeyword, decide, normalizeKeyword, tracking, type Keyword, type TrendsBudget } from "./keywords-model";

const AS_OF = "2026-10-24T02:00:00Z";
const NOW = "2026-10-25T09:00:00Z";
const k = (keyword: string, status: Keyword["status"], relevance: number | null = 0.5): Keyword => ({
  keyword, relevance, as_of: AS_OF, source: "title", status, decided_at: status === "candidate" ? null : AS_OF,
  tracked: status === "confirmed" ? true : null, untracked_reason: null,
});
const list = [k("sunset projection lamp", "candidate", 0.833), k("sunset", "confirmed"), k("lamp", "rejected")];

describe("normalizeKeyword", () => {
  test("mirrors the API: lower case, a straight apostrophe, spacing collapsed", () => {
    expect(normalizeKeyword("  Women’s   Sunset LAMP \n")).toBe("women's sunset lamp");
  });
});

describe("decide", () => {
  test("a candidate takes its new status and decision time, in place", () => {
    const next = decide(list, "Sunset Projection Lamp", "confirmed", NOW);
    expect(next[0]).toEqual({ ...list[0], status: "confirmed", decided_at: NOW });
    expect(next.slice(1)).toEqual(list.slice(1));
  });

  test("a rejected keyword can be confirmed again, and a confirmed one rejected", () => {
    expect(decide(list, "lamp", "confirmed", NOW)[2]).toMatchObject({ status: "confirmed", decided_at: NOW });
    expect(decide(list, "sunset", "rejected", NOW)[1]).toMatchObject({ status: "rejected", decided_at: NOW });
  });

  test("a typed-in keyword joins as manual with no relevance (no title holds it yet)", () => {
    const next = decide(list, " Galaxy  Lamp ", "confirmed", NOW);
    expect(next).toHaveLength(4);
    expect(next[3]).toEqual({
      keyword: "galaxy lamp", relevance: null, as_of: AS_OF, source: "manual", status: "confirmed", decided_at: NOW, tracked: null, untracked_reason: null,
    });
  });

  test("whether a decided keyword is tracked waits for the API, which counts the weekly Trends set", () => {
    expect(decide(list, "sunset", "rejected", NOW)[1]).toMatchObject({ tracked: null, untracked_reason: null });
    expect(decide(list, "sunset", "confirmed", NOW)[1]).toMatchObject({ tracked: null });
  });
});

describe("checkKeyword", () => {
  test("names why a typed keyword can't be added, or null when it can", () => {
    expect(checkKeyword(list, "   ")).toBe("Type the words a shopper would search.");
    expect(checkKeyword(list, "!!! --")).toBe("A keyword needs at least one letter or digit.");
    expect(checkKeyword(list, "x".repeat(101))).toBe("Keywords are 100 characters at most.");
    expect(checkKeyword(list, " SUNSET ")).toBe("“sunset” is already confirmed.");
    expect(checkKeyword(list, "lamp")).toBeNull(); // rejected: adding it confirms it again
    expect(checkKeyword(list, "sunset projection lamp")).toBeNull();
  });
});

describe("tracking", () => {
  const budget: TrendsBudget = { enabled: true, weekly_used: 50, weekly_cap: 50, monthly_limit: 250, as_of: NOW };
  const out = (untracked_reason: Keyword["untracked_reason"]): Keyword => ({ ...k("lamp", "confirmed"), tracked: false, untracked_reason });

  test("names the marker and the reason for each place in the weekly set", () => {
    expect(tracking(k("sunset", "confirmed"), budget)).toEqual({
      label: "Tracked",
      reason: "Tracked: fetched from Google Trends every Monday, 1 SerpApi search a week.",
    });
    expect(tracking(out("budget"), budget)).toEqual({
      label: "Not tracked: weekly set full",
      reason: "Not tracked: all 50 weekly slots are used. It's saved, and joins when a slot frees.",
    });
    expect(tracking(out("disabled"), budget)?.reason).toBe("Not tracked: Trends tracking for confirmed keywords is off, so nothing is fetched for them.");
    expect(tracking(out("comma"), budget)?.label).toBe("Not tracked: has a comma");
  });

  test("no marker for a suggestion, a rejected keyword, or a decision the API hasn't answered", () => {
    expect(tracking(k("x", "candidate"), budget)).toBeNull();
    expect(tracking(k("x", "rejected"), budget)).toBeNull();
    expect(tracking({ ...k("x", "confirmed"), tracked: null }, budget)).toBeNull();
  });
});
