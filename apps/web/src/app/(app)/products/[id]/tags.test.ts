import { describe, expect, test } from "vitest";

import { addTag, MAX_TAGS } from "./tags";

describe("addTag", () => {
  test("trims, collapses inner spaces and keeps the set sorted case-insensitively", () => {
    expect(addTag(["TikTok", "winner"], "  q4   test ")).toEqual({ tags: ["q4 test", "TikTok", "winner"] });
    expect(addTag([], "Zeta")).toEqual({ tags: ["Zeta"] });
    expect(addTag(["b"], "A")).toEqual({ tags: ["A", "b"] });
  });

  test("an empty or blank input changes nothing", () => {
    const tags = ["winner"];
    expect(addTag(tags, "")).toEqual({ tags });
    expect(addTag(tags, "   ")).toEqual({ tags });
  });

  test("a repeat that differs only in case is refused, naming the existing tag", () => {
    expect(addTag(["Winner"], " winner")).toEqual({ error: "Already tagged “Winner”." });
  });

  test("at most 20 tags of 80 characters", () => {
    const full = Array.from({ length: MAX_TAGS }, (_, i) => `t${i}`);
    expect(addTag(full, "one more")).toEqual({ error: "20 tags at most. Remove one first." });
    expect(addTag([], "x".repeat(81))).toEqual({ error: "Tags are 80 characters at most." });
    expect(addTag([], "x".repeat(80))).toEqual({ tags: ["x".repeat(80)] });
  });
});
