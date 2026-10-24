import { describe, expect, test } from "vitest";

import { retryOutcome } from "./retry";

// imp-135: which error a pressed Retry left on screen decides what is announced and where focus goes.
describe("retryOutcome", () => {
  const pressed = { name: "pressed" };
  const replacement = { name: "replacement" };
  const other = { name: "other" };

  test("a pressed error still shown failed (a stale line stays while refreshing)", () => {
    expect(retryOutcome(pressed, new Set([other, pressed]), new Set([other, pressed]))).toBe(pressed);
  });

  test("an error shown since the press failed in its place (a panel error leaves while refreshing)", () => {
    expect(retryOutcome(pressed, new Set([other, replacement]), new Set([other, pressed]))).toBe(replacement);
  });

  test("no new error: the retry restored its panel, even beside an error from another call", () => {
    expect(retryOutcome(pressed, new Set(), new Set([pressed]))).toBeNull();
    expect(retryOutcome(pressed, new Set([other]), new Set([other, pressed]))).toBeNull();
  });
});
