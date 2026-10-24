import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi, sources } from "./fixtures";

// imp-172 owner review screenshots from fixtures only: Frankfurter FX's never-run drawer with its "CSV import panel"
// button keyboard-focused, then the import panel after one Enter (FX selected, Choose CSV… focused), and the sentence
// a source that can also run reads (Run now, or the CSV import panel).
// 1440px and 375px, dark and light.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/drawer-import`; output goes to docs/screenshots/imp-172/.
const OUT = "../../docs/screenshots/imp-172";

async function shoot(page: Page, name: string) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${OUT}/${name}.png` });
}

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`drawer CSV import panel button, then the panel ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      const panel = page.getByRole("region", { name: "CSV import" });
      await panel.getByLabel("Source").selectOption("cj");
      await page.getByRole("button", { name: "Frankfurter FX: open runs" }).locator("visible=true").focus();
      await page.keyboard.press("Enter");
      const drawer = page.getByRole("dialog", { name: "Frankfurter FX" });
      await expect(drawer).toBeFocused(); // where the drawer puts focus on open
      const link = drawer.getByRole("button", { name: "CSV import panel" });
      await expect(link).toBeVisible(); // once FX's (empty) runs load
      await page.keyboard.press("Tab");
      await page.keyboard.press("Tab");
      await expect(link).toBeFocused();
      await shoot(page, `drawer-link-${width}-${theme}`);

      await page.keyboard.press("Enter");
      await expect(page.getByRole("dialog")).toBeHidden();
      await expect(panel.getByRole("button", { name: "Choose CSV…" })).toBeFocused();
      await expect(panel.getByLabel("Source")).toHaveValue("fx_frankfurter");
      await shoot(page, `panel-${width}-${theme}`);
    });
  }
}

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`drawer naming Run now and the CSV import panel ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page, {
        host: { live_runs_allowed: true },
        sources: sources.map((s) => (s.key === "fx_frankfurter" ? { ...s, enabled: true, status: "active" } : s)),
      });
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      await page.getByRole("button", { name: "Frankfurter FX: open runs" }).locator("visible=true").click();
      await expect(page.getByRole("dialog", { name: "Frankfurter FX" }).getByRole("button", { name: "CSV import panel" })).toBeVisible();
      await shoot(page, `drawer-both-${width}-${theme}`);
    });
  }
}
