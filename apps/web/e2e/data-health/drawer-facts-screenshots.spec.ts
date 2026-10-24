import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-098 review screenshots from fixtures only: the Shopify and CJ run drawers with wrapped facts and grouped
// counts, at 1440px and 375px, dark and light. Run with `pnpm --filter web e2e:screenshots e2e/data-health/drawer-facts`.
const OUT = "../../docs/screenshots/imp-098";

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    for (const [slug, name] of [
      ["shopify", "Shopify stores"],
      ["cj", "CJ Dropshipping"],
    ]) {
      test(`${slug} drawer facts ${width}px ${theme}`, async ({ page }) => {
        await mockAdminApi(page);
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
        await page.goto("/admin/data-health");
        await page.getByRole("button", { name: `${name}: open runs` }).first().click();
        await expect(page.getByRole("dialog", { name })).toContainText("#9001");
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(500);
        await page.screenshot({ path: `${OUT}/drawer-${slug}-${width}-${theme}.png` });
      });
    }
  }
}

// imp-127/119/128/131: facts in the table's and the pill's words (Blocked, Overdue, Disabled), FX's never-run state
// naming CSV import, and the Shopify targets table scrolled into view.
const OUT_127 = "../../docs/screenshots/imp-127";

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    for (const [slug, name] of [
      ["shopify", "Shopify stores"],
      ["trends", "Google Trends"],
      ["fx", "Frankfurter FX"],
    ]) {
      test(`imp-127 ${slug} drawer ${width}px ${theme}`, async ({ page }) => {
        await mockAdminApi(page);
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
        await page.goto("/admin/data-health");
        await page.getByRole("button", { name: `${name}: open runs` }).first().click();
        const drawer = page.getByRole("dialog", { name });
        await expect(drawer).toContainText(slug === "fx" ? "No runs yet" : "Payload");
        if (slug === "shopify") await drawer.getByRole("region", { name: "Run 412 targets" }).scrollIntoViewIfNeeded();
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(500);
        await page.screenshot({ path: `${OUT_127}/drawer-${slug}-${width}-${theme}.png` });
      });
    }
  }
}
