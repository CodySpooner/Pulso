import { expect, test, type Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";

import { cjPreview, importPreview, mockAdminApi } from "./fixtures";

type S = components["schemas"];

// imp-116, imp-117, imp-129: the Row errors table has a visible heading, keeps its Problem column readable at
// phone width, and stays beside the outcome after an import that skipped rows. Fixtures only.
const csv = (rate: string) => ({ name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from(`date,base,quote,rate\n2026-01-01,USD,JPY,${rate}\n`) });
const SKIPPED = "5 rate Invalid rate. Use a finite positive decimal number below 10,000,000,000 with up to 8 decimal places.";
const clean: S["ImportPreview"] = { ...importPreview, invalid: 0, error_count: 0, errors: [] };

async function openPanel(page: Page, preview: () => S["ImportPreview"] = () => importPreview) {
  await mockAdminApi(page);
  await page.route(/\/import\/preview$/, (route) => route.fulfill({ json: preview() }));
  await page.goto("/admin/data-health");
  return page.getByRole("region", { name: "CSV import" });
}

test("a visible Row errors heading names the table", async ({ page }) => {
  const panel = await openPanel(page);
  await panel.locator('input[type="file"]').setInputFiles(csv("150"));
  const heading = panel.getByRole("heading", { name: "Row errors", level: 3 });
  await expect(heading).toBeVisible();
  const table = panel.getByRole("region", { name: "Row errors" });
  await expect(table).toHaveAttribute("aria-labelledby", (await heading.getAttribute("id"))!);
  await expect(table.getByRole("columnheader")).toHaveText(["Row", "Column", "Problem"]);
  await expect(table.getByRole("row", { name: SKIPPED })).toBeVisible();
});

for (const width of [375, 640, 768]) {
  test(`at ${width}px Problem keeps at least 12rem and nothing scrolls sideways`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const panel = await openPanel(page, () => cjPreview);
    await panel.getByLabel("Source").selectOption("cj");
    await panel.locator('input[type="file"]').setInputFiles(csv("150"));
    const table = panel.getByRole("region", { name: "Row errors" });
    await expect(table.getByRole("row", { name: "19 cj_product_id or sku One identifier required", exact: true })).toBeVisible();
    const problem = await table.getByRole("columnheader", { name: "Problem" }).evaluate((el) => el.getBoundingClientRect().width);
    expect(problem).toBeGreaterThanOrEqual(12 * 16);
    expect(await table.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  });
}

test("after an import that skipped rows they stay beside the outcome, until another file or source", async ({ page }) => {
  let preview = importPreview;
  const panel = await openPanel(page, () => preview);
  const table = panel.getByRole("region", { name: "Row errors" });
  await panel.locator('input[type="file"]').setInputFiles(csv("150"));
  await expect(table.getByRole("row")).toHaveCount(2); // before Import: 1 skipped row
  await panel.getByRole("button", { name: "Import 3 rows" }).focus();
  await page.keyboard.press("Enter");

  // After Import: still 1, next to the outcome; announcements and the Open runs focus are unchanged (DEC-145).
  await expect(panel.getByRole("status")).toHaveText("Imported into Frankfurter FX as run #501: 3 new, 0 updated, 0 unchanged. Rows with errors were skipped (1 error).");
  await expect(panel.getByRole("button", { name: "Open runs" })).toBeFocused();
  await expect(table.getByRole("row")).toHaveCount(2);
  await expect(table.getByRole("row", { name: SKIPPED })).toBeVisible();
  await expect(panel.getByRole("heading", { name: "Row errors", level: 3 })).toBeVisible();
  await page.keyboard.press("Tab"); // the skipped rows come right after Open runs, focusable to scroll
  await expect(table).toBeFocused();
  await expect(table).toHaveCSS("outline-style", "solid");

  // Another source clears them with the outcome.
  await panel.getByLabel("Source").selectOption("cj");
  await expect(panel).not.toContainText("Rows with errors were skipped");
  await expect(table).toHaveCount(0);

  // So does another file: its own check decides what shows.
  await panel.getByLabel("Source").selectOption("fx_frankfurter");
  await panel.locator('input[type="file"]').setInputFiles(csv("151"));
  await panel.getByRole("button", { name: "Import 3 rows" }).click();
  await expect(table.getByRole("row", { name: SKIPPED })).toBeVisible();
  preview = clean;
  await panel.locator('input[type="file"]').setInputFiles(csv("152"));
  await expect(panel.getByRole("button", { name: "Import 3 rows" })).toBeVisible();
  await expect(panel).not.toContainText("Rows with errors were skipped");
  await expect(table).toHaveCount(0);
});
