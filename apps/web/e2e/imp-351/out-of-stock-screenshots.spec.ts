import { expect, test } from "@playwright/test";

import { PRODUCT_ID } from "../products/fixtures";
import { mockProfitApi, outOfStock } from "../products/profit-fixtures";

// imp-351 owner review: the Profit tab when no supplier is in stock, so its default costs the best out-of-stock listing
// and marks it. Fixtures only (the E2E auth bypass). Run with `pnpm --filter web e2e:screenshots e2e/imp-351`; output:
// docs/screenshots/imp-351/. Tall viewports, as in profit-screenshots.spec.ts.
const OUT = "../../docs/screenshots/imp-351";

for (const theme of ["dark", "light"] as const)
  for (const [width, height] of [
    [1440, 1300],
    [375, 2700],
  ])
    test(`out of stock ${width}px ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await mockProfitApi(page, { body: outOfStock });
      await page.goto(`/products/${PRODUCT_ID}?tab=profit`);
      await expect(page.getByRole("region", { name: "Scenario" }).getByText("Out of stock")).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${OUT}/out-of-stock-${width}-${theme}.png` });
    });
