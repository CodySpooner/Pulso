import { afterEach, describe, expect, it, vi } from "vitest";

import { copyText, results } from "./copy-button";

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

describe("copy results", () => {
  it("a failure says what happened, why and what to do next", () => {
    expect(results.failed.text).toBe("Couldn’t copy");
    // A cause true for every failure copyText reports (no API or a refused write, never "blocked"), then an
    // imperative next step the user can take without the clipboard API.
    expect(results.failed.hint).toBe("The clipboard isn’t available here. Select the ID to copy it.");
    expect("hint" in results.copied).toBe(false);
  });

  it("a failure stays about 5 s: long enough to read with its cause and next step", () => {
    // About 200 words a minute (300 ms a word) plus a second to notice it.
    const words = `${results.failed.text} ${results.failed.hint}`.split(/\s+/).length;
    expect(results.failed.ms).toBeGreaterThanOrEqual(1000 + words * 300);
    expect(results.failed.ms).toBe(5000);
    expect(results.failed.ms).toBeGreaterThan(results.copied.ms);
  });
});
