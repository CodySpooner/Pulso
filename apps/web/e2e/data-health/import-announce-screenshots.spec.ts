import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-055/056 owner review screenshots of the CSV import panel, from fixtures only: 1440px and 375px, dark
// and light; a preview the API didn't answer, a 503 on import, and focus on Open runs after an import.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/import-announce`; output: docs/screenshots/imp-055/.
const OUT = "../../docs/screenshots/imp-055";
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };
const problem503 = {
  type: "about:blank", title: "Service Unavailable", status: 503, code: "unavailable",
  detail: "The API is restarting. Try again in a minute.", request_id: "e2e-503", errors: [],
};

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`csv import announce ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      let failPreview = true;
      let failCommit = true;
      await page.route(/\/import\/preview$/, (route) => (failPreview ? route.abort("connectionrefused") : route.fallback()));
      await page.route(/\/sources\/[^/]+\/import$/, (route) => (failCommit ? route.fulfill({ status: 503, json: problem503 }) : route.fallback()));
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      const panel = page.getByRole("region", { name: "CSV import" });
      const shot = async (name: string) => {
        await page.evaluate(() => document.fonts.ready);
        await panel.evaluate((el) => el.scrollIntoView({ block: "center" })); // clear of the phone's bottom nav
        await page.waitForTimeout(300);
        await panel.screenshot({ path: `${OUT}/import-${name}-${width}-${theme}.png` });
      };

      // Keyboard throughout, so the focus ring shows where a keyboard user is.
      const choose = panel.getByRole("button", { name: "Choose CSV…" });
      await choose.focus();
      const chooser = page.waitForEvent("filechooser");
      await page.keyboard.press("Enter");
      await (await chooser).setFiles(file);
      await expect(panel.getByRole("alert")).toContainText("didn't answer while checking");
      await page.keyboard.press("Tab"); // Retry
      await shot("preview-error");

      failPreview = false;
      await page.keyboard.press("Enter");
      const importButton = panel.getByRole("button", { name: "Import 3 rows" });
      await expect(importButton).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(panel.getByRole("alert")).toContainText("The API is restarting.");
      await shot("commit-error");

      failCommit = false;
      await page.keyboard.press("Enter");
      await expect(panel.getByRole("button", { name: "Open runs" })).toBeFocused();
      await shot("done-focus");
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });
  }
}
