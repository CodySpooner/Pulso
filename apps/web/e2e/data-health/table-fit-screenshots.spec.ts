import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// p1-53 review screenshots from fixtures only: the 1440px Sources table (missed slot on one line, Freshness on one
// line, no overflow) and the 375px first load against the loaded page, dark and light. Run with
// `pnpm --filter web e2e:screenshots e2e/data-health/table-fit`; output goes to docs/screenshots/p1-53/, with a
// `-linux` suffix when run in the Playwright Linux container (CI's font metrics).
const OUT = "../../docs/screenshots/p1-53";
const os = process.platform === "linux" ? "-linux" : "";

for (const theme of ["dark", "light"] as const) {
  test(`sources table 1440px ${theme}`, async ({ page }) => {
    await mockAdminApi(page);
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
    await page.goto("/admin/data-health");
    await expect(page.getByRole("link", { name: /^Missed Oct 22/ }).locator("visible=true")).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(300);
    await page.getByRole("region", { name: "Sources", exact: true }).screenshot({ path: `${OUT}/sources-1440-${theme}${os}.png` });
  });

  test(`first load 375px ${theme}`, async ({ page }) => {
    await mockAdminApi(page, { delayMs: 8000 });
    await page.setViewportSize({ width: 375, height: 812 });
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
    await page.goto("/admin/data-health");
    await expect(page.getByRole("region", { name: "Sources", exact: true }).locator(".bg-skeleton:visible").first()).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${OUT}/loading-375-${theme}${os}.png` });

    await expect(page.getByRole("img", { name: /^CJ Dropshipping, last 90 days/ })).toBeVisible({ timeout: 15_000 });
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${OUT}/loaded-375-${theme}${os}.png` });
  });
}
