import { describe, expect, test } from "vitest";

import { formatAgo, formatDelta, formatDuration, formatUtc } from "./format";

// The delta rule (vault Design/Design System): glyph = direction, colour = good or bad for the owner,
// a value that rounds to zero is flat, and minus is U+2212.
describe("formatDelta", () => {
  test.each([
    [12.44, "up", { glyph: "▲", text: "+12.4", tone: "positive" }],
    [-3.06, "up", { glyph: "▼", text: "−3.1", tone: "negative" }],
    [8, "down", { glyph: "▲", text: "+8.0", tone: "negative" }],
    [-8, "down", { glyph: "▼", text: "−8.0", tone: "positive" }],
    [8, "neutral", { glyph: "▲", text: "+8.0", tone: "neutral" }],
    [0.04, "up", { glyph: null, text: "±0.0", tone: "neutral" }],
    [-0.04, "down", { glyph: null, text: "±0.0", tone: "neutral" }],
    [0, "up", { glyph: null, text: "±0.0", tone: "neutral" }],
    [-0, "down", { glyph: null, text: "±0.0", tone: "neutral" }],
  ] as const)("%d with good direction %s", (value, goodDirection, expected) => {
    expect(formatDelta(value, goodDirection)).toEqual(expected);
  });

  // Missing or non-finite is an em dash with no direction, never coerced to zero (vault Design/Typography).
  test.each([null, undefined, Number.NaN, Infinity, -Infinity])("%s is missing in every good direction", (value) => {
    for (const goodDirection of ["up", "down", "neutral"] as const) {
      expect(formatDelta(value, goodDirection)).toEqual({ glyph: null, text: "—", tone: "neutral", missing: true });
    }
  });

  test("digits set the display precision", () => {
    expect(formatDelta(1234, "up", 0)).toEqual({ glyph: "▲", text: "+1234", tone: "positive" });
    expect(formatDelta(-0.4, "up", 0).text).toBe("±0");
  });
});

describe("time", () => {
  const now = Date.parse("2026-10-22T14:00:00Z");
  test.each([
    ["2026-10-22T13:59:30Z", "just now"],
    ["2026-10-22T13:56:00Z", "4m ago"],
    ["2026-10-22T11:00:00Z", "3h ago"],
    ["2026-10-20T13:00:00Z", "2d ago"],
    ["2026-10-22T15:30:00Z", "in 1h"],
  ])("formatAgo(%s)", (iso, text) => {
    expect(formatAgo(iso, now)).toBe(text);
  });

  test("formatUtc is a 24-hour UTC stamp", () => {
    expect(formatUtc("2026-10-22T09:05:00+02:00")).toBe("Oct 22, 07:05 UTC");
  });

  test.each([
    [42_000, "42s"],
    [185_000, "3m 05s"],
    [3_720_000, "1h 02m"],
  ])("formatDuration(%i)", (ms, text) => {
    expect(formatDuration(ms)).toBe(text);
  });
});
