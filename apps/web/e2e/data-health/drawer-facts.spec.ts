import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-098 (aud-011 B11-03/B11-04): every run-drawer fact reads in full on a phone (touch has no hover),
// and its counts are grouped like the Sources table's.

for (const theme of ["dark", "light"] as const) {
  for (const width of [1440, 375]) {
    test(`drawer facts wrap and group counts at ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      await page.setViewportSize({ width, height: width < 1024 ? 812 : 900 });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");

      for (const name of ["Shopify stores", "CJ Dropshipping"]) {
        await page.getByRole("button", { name: `${name}: open runs` }).first().click();
        const drawer = page.getByRole("dialog", { name });
        await expect(drawer).toContainText("#9001"); // the newest run is expanded, targets loaded
        const clipped = await drawer.locator("dd").evaluateAll((dds) => dds.filter((dd) => dd.scrollWidth > dd.clientWidth).map((dd) => dd.textContent));
        expect(clipped).toEqual([]);
        const key = drawer.locator("dt", { hasText: /^Key$/ }).locator("+ dd > span");
        await expect(key).toHaveCSS("font-family", /mono/i);
        expect(await key.evaluate((el) => el.getClientRects().length)).toBe(1); // one unbroken line
        expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);

        if (name === "CJ Dropshipping") {
          const fact = (label: string) => drawer.locator("dt", { hasText: new RegExp(`^${label}$`) }).locator("+ dd");
          await expect(fact("Quota")).toHaveText("2,650 / 50,000");
          await expect(fact("Rows")).toHaveText("1,240 fetched · 36 inserted · 112 updated · 1,092 unchanged");
          await expect(fact("Requests")).toHaveText("26 · last code 200");
        }
        await page.keyboard.press("Escape");
        await expect(drawer).toBeHidden();
      }
    });
  }
}
