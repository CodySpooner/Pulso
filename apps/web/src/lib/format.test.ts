import { describe, expect, test } from "vitest";

import { formatDelta } from "./format";

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
  ] as const)("%d with good direction %s", (value, goodDirection, expected) => {
    expect(formatDelta(value, goodDirection)).toEqual(expected);
  });

  test("digits set the display precision", () => {
    expect(formatDelta(1234, "up", 0)).toEqual({ glyph: "▲", text: "+1234", tone: "positive" });
    expect(formatDelta(-0.4, "up", 0).text).toBe("±0");
  });
});
