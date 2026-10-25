import { describe, expect, test } from "vitest";

import { checkKeyword, decide, normalizeKeyword, type Keyword } from "./keywords-model";

const AS_OF = "2026-10-24T02:00:00Z";
const NOW = "2026-10-25T09:00:00Z";
const k = (keyword: string, status: Keyword["status"], relevance: number | null = 0.5): Keyword => ({
  keyword, relevance, as_of: AS_OF, source: "title", status, decided_at: status === "candidate" ? null : AS_OF,
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
    expect(next[3]).toEqual({ keyword: "galaxy lamp", relevance: null, as_of: AS_OF, source: "manual", status: "confirmed", decided_at: NOW });
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
