import { describe, expect, test } from "vitest";

import { resolveTab, TAB_FLAGS, TABS } from "./tabs";

describe("resolveTab", () => {
  test.each(TABS.map((t) => t.value))("?tab=%s deep-links to its tab", (value) => {
    expect(resolveTab(value)).toBe(value);
  });

  test.each([null, "", "risk", "Trends", "constructor", "__proto__", "overview "])("%j falls back to overview", (value) => {
    expect(resolveTab(value)).toBe("overview");
  });

  test("a flagged-off tab falls back to overview", () => {
    expect(resolveTab("profit", { ...TAB_FLAGS, profit: false })).toBe("overview");
    expect(resolveTab("trends", { ...TAB_FLAGS, profit: false })).toBe("trends");
  });
});
