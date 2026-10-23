import { afterEach, describe, expect, it, vi } from "vitest";

import { copyText } from "./copy-button";

afterEach(() => vi.unstubAllGlobals());

describe("copyText", () => {
  it("writes the value and reports success", async () => {
    const writeText = vi.fn(async () => {});
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    await expect(copyText("err-123")).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith("err-123");
  });

  it("reports a denied write instead of rejecting", async () => {
    const writeText = vi.fn(() => Promise.reject(new DOMException("Write permission denied.", "NotAllowedError")));
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    await expect(copyText("err-123")).resolves.toBe(false);
    // Retry stays possible: a second click tries again.
    await expect(copyText("err-123")).resolves.toBe(false);
    expect(writeText).toHaveBeenCalledTimes(2);
  });

  it("reports a missing clipboard API (insecure origins) instead of throwing", async () => {
    vi.stubGlobal("navigator", {});
    await expect(copyText("err-123")).resolves.toBe(false);
  });
});
