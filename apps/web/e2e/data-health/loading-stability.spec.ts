import { expect, test, type Locator } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-082 (aud-011 B11-01): the first-load skeletons reserve the loaded layout, so nothing jumps when the
// fixture data lands. Layout shifts are summed from navigation until the CJ coverage row renders.

const height = async (l: Locator) => (await l.boundingBox())!.height;
const noPageScrollX = () => document.documentElement.scrollWidth <= document.documentElement.clientWidth;

for (const theme of ["dark", "light"] as const) {
  for (const [width, viewportHeight] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`first load keeps the layout stable at ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page, { delayMs: 2500 });
      await page.setViewportSize({ width, height: viewportHeight });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => {
        localStorage.setItem("theme", t);
        const w = window as unknown as { cls: number };
        w.cls = 0;
        new PerformanceObserver((list) => {
          for (const e of list.getEntries() as (PerformanceEntry & { value: number; hadRecentInput: boolean })[]) {
            if (!e.hadRecentInput) w.cls += e.value;
          }
        }).observe({ type: "layout-shift", buffered: true });
      }, theme);
      await page.goto("/admin/data-health");

      const sources = page.getByRole("region", { name: "Sources", exact: true });
      const coverage = page.getByRole("region", { name: "Coverage" });
      await expect(sources.locator(".bg-skeleton:visible").first()).toBeVisible();
      await expect(page.getByRole("button", { name: "CJ Dropshipping: open runs" })).toHaveCount(0); // still loading
      const loading = { sources: await height(sources), coverage: await height(coverage) };
      expect(await page.evaluate(noPageScrollX)).toBe(true);

      await expect(page.getByRole("img", { name: /^CJ Dropshipping, last 90 days/ })).toBeVisible({ timeout: 15_000 });
      await page.evaluate(() => document.fonts.ready);
      const loaded = { sources: await height(sources), coverage: await height(coverage) };
      const cls = await page.evaluate(() => (window as unknown as { cls: number }).cls);
      console.log(`imp-082 ${width} ${theme}: CLS ${cls.toFixed(3)} · Sources ${loading.sources}→${loaded.sources} · Coverage ${loading.coverage}→${loaded.coverage}`);

      expect(cls).toBeLessThan(0.1);
      expect(loading.sources / loaded.sources).toBeGreaterThanOrEqual(0.85);
      expect(loading.coverage / loaded.coverage).toBeGreaterThanOrEqual(0.85);
      expect(await page.evaluate(noPageScrollX)).toBe(true);
    });
  }
}
