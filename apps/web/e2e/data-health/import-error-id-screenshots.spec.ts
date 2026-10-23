import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-077 owner review screenshots of the CSV import error line, from fixtures only: 1440px and 375px, dark
// and light; a 503 on import with focus on Copy error ID, then a denied copy with its hint.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/import-error-id`; output: docs/screenshots/imp-077/.
const OUT = "../../docs/screenshots/imp-077";
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };
const problem503 = {
  type: "about:blank", title: "Service Unavailable", status: 503, code: "unavailable",
  detail: "The API is restarting. Try again in a minute.", request_id: "3f2b8c1e-7d4a-4e9b-9c5f-1a2b3c4d5e6f", errors: [],
};

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`csv import error id ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      await page.addInitScript(() => {
        navigator.clipboard.writeText = () => Promise.reject(new DOMException("Write permission denied.", "NotAllowedError"));
      });
      await page.route(/\/sources\/[^/]+\/import$/, (route) => route.fulfill({ status: 503, json: problem503 }));
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      const panel = page.getByRole("region", { name: "CSV import" });
      const shot = async (name: string) => {
        await page.evaluate(() => document.fonts.ready);
        await panel.evaluate((el) => el.scrollIntoView({ block: "center" })); // clear of the phone's bottom nav
        await page.waitForTimeout(300);
        // The page, not the panel, so the copy hint's tooltip (portalled outside the panel) is in the picture.
        await page.screenshot({ path: `${OUT}/import-${name}-${width}-${theme}.png` });
      };

      await panel.locator('input[type="file"]').setInputFiles(file);
      await panel.getByRole("button", { name: "Import 3 rows" }).focus();
      await page.keyboard.press("Enter");
      await expect(panel.getByRole("alert")).toContainText("The API is restarting.");
      const copy = panel.getByRole("button", { name: /^(Copy error ID|Couldn’t copy)/ });
      await copy.focus(); // keyboard focus, so the ring shows
      await shot("commit-error");

      await page.keyboard.press("Enter");
      await expect(page.getByRole("tooltip")).toBeVisible();
      await shot("copy-failed");
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });
  }
}
