import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-152 (p1-53 leftover 1): GET /host lands before GET /sources. Until the names arrive the host card's
// latest-gap line and the Open gaps table hold their skeletons, so no source key ever renders and nothing
// rewraps when the names land. A MutationObserver from before navigation records every key that reaches the page.

const KEYS = ["google_trends", "shopify_stores", "fx_frankfurter"];

for (const [width, viewportHeight] of [
  [375, 812],
  [1440, 900],
] as const) {
  test(`host before sources at ${width}px: no source key renders, CLS stays low`, async ({ page }) => {
    await mockAdminApi(page, { delayMs: 1200 });
    let release!: () => void;
    const held = new Promise<void>((resolve) => (release = resolve));
    await page.route((url) => url.pathname === "/api/v1/admin/sources", async (route) => {
      await held;
      await route.fallback();
    });
    await page.setViewportSize({ width, height: viewportHeight });
    await page.addInitScript((keys) => {
      const w = window as unknown as { cls: number; keysSeen: string[] };
      w.cls = 0;
      w.keysSeen = [];
      new PerformanceObserver((list) => {
        for (const e of list.getEntries() as (PerformanceEntry & { value: number; hadRecentInput: boolean })[]) {
          if (!e.hadRecentInput) w.cls += e.value;
        }
      }).observe({ type: "layout-shift", buffered: true });
      new MutationObserver(() => {
        const text = document.body?.innerText ?? "";
        for (const k of keys) if (text.includes(k) && !w.keysSeen.includes(k)) w.keysSeen.push(k);
      }).observe(document, { subtree: true, childList: true, characterData: true });
    }, KEYS);
    await page.goto("/admin/data-health");

    const hostCard = page.getByRole("region", { name: "Collector host" });
    await expect(hostCard.locator("dl")).toBeVisible({ timeout: 15_000 }); // the host has landed, sources are held
    await expect(page.getByRole("button", { name: "CJ Dropshipping: open runs" })).toHaveCount(0);
    await page.waitForTimeout(300);
    expect.soft(await page.evaluate(() => (window as unknown as { keysSeen: string[] }).keysSeen)).toEqual([]);

    release();
    await expect(hostCard.getByText(/latest Google Trends/)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("region", { name: "Open gaps" })).toContainText("Google Trends");
    await expect(page.getByRole("img", { name: /^CJ Dropshipping, last 90 days/ })).toBeVisible();
    await expect(page.getByRole("region", { name: "Backups" }).locator("dl")).toBeVisible();
    await page.evaluate(() => document.fonts.ready);

    const { cls, keysSeen } = await page.evaluate(() => {
      const w = window as unknown as { cls: number; keysSeen: string[] };
      return { cls: w.cls, keysSeen: w.keysSeen };
    });
    console.log(`imp-152 ${width}: host before sources, CLS ${cls.toFixed(4)}`);
    expect(keysSeen).toEqual([]);
    expect(cls).toBeLessThan(0.05);
  });
}
