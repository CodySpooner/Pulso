import { describe, expect, test } from "vitest";

import { authBypassFrom, isPlatformAdmin, parseAllowlist } from "./auth";

describe("auth fails closed", () => {
  test("the E2E bypass can never be on in production", () => {
    expect(authBypassFrom("production", "1")).toBe(false);
    expect(authBypassFrom("production", undefined)).toBe(false);
  });

  test("the E2E bypass needs the explicit flag outside production", () => {
    expect(authBypassFrom("development", "1")).toBe(true);
    expect(authBypassFrom("test", "1")).toBe(true);
    expect(authBypassFrom("development", undefined)).toBe(false);
    expect(authBypassFrom("development", "true")).toBe(false);
  });

  test("an empty or missing allowlist admits nobody", () => {
    expect(isPlatformAdmin("user_1", undefined)).toBe(false);
    expect(isPlatformAdmin("user_1", "")).toBe(false);
    expect(isPlatformAdmin("", " , ")).toBe(false);
  });

  test("the allowlist matches exact ids, trimmed", () => {
    expect(parseAllowlist(" user_1, user_2 ,,")).toEqual(new Set(["user_1", "user_2"]));
    expect(isPlatformAdmin("user_2", "user_1,user_2")).toBe(true);
    expect(isPlatformAdmin("user_12", "user_1")).toBe(false);
  });
});
