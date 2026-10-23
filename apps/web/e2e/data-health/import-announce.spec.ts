import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-055/056 (aud-004 C2-01, C2-02): the CSV import panel announces what is happening (progress politely,
// errors assertively, never both) and keeps a keyboard user's focus when the focused control leaves.
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };
const COMMIT = /\/api\/v1\/admin\/sources\/[^/]+\/import$/;
const PREVIEW = /\/api\/v1\/admin\/sources\/[^/]+\/import\/preview$/;

async function openPanel(page: Page) {
  await page.goto("/admin/data-health");
  const panel = page.getByRole("region", { name: "CSV import" });
  await expect(panel.getByRole("button", { name: "Choose CSV…" })).toBeVisible();
  return panel;
}

/** Enter on the focused Choose button opens the picker; the file is checked at once. */
async function chooseByKeyboard(page: Page, choose: Locator) {
  await expect(choose).toBeFocused();
  const chooser = page.waitForEvent("filechooser");
  await page.keyboard.press("Enter");
  await (await chooser).setFiles(file);
}

async function expectRing(control: Locator) {
  await expect(control).toBeFocused();
  expect(await control.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
}

test("a preview transport error is announced once, assertively, and Retry keeps focus", async ({ page }) => {
  await mockAdminApi(page);
  let down = true;
  await page.route(PREVIEW, (route) => (down ? route.abort("connectionrefused") : route.fallback()));
  const panel = await openPanel(page);

  await panel.getByRole("button", { name: "Choose CSV…" }).focus();
  await chooseByKeyboard(page, panel.getByRole("button", { name: "Choose CSV…" }));
  await expect(panel).toContainText("The API didn't answer while checking the file.");
  await expect(panel.getByRole("alert")).toHaveText("The API didn't answer while checking the file. Select Retry to try again.");
  await expect(panel.getByRole("status")).toHaveText("");

  // Tab reaches Retry with a ring; a retry that fails again brings focus back to the new Retry, not the page.
  await page.keyboard.press("Tab");
  const retry = panel.getByRole("button", { name: "Retry" });
  await expectRing(retry);
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("alert")).toHaveText(/didn't answer while checking/);
  await expectRing(retry);

  // The API is back: the summary replaces the error (polite), the alert empties and Import takes focus.
  down = false;
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("status")).toHaveText("3 valid rows · 1 invalid row");
  await expect(panel.getByRole("alert")).toHaveText("");
  await expectRing(panel.getByRole("button", { name: "Import 3 rows" }));
});

test("a commit 503 replaces the stale preview summary with an assertive error", async ({ page }) => {
  await mockAdminApi(page);
  let release!: () => void;
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route(COMMIT, async (route) => {
    await held;
    await route.fulfill({
      status: 503,
      json: { type: "about:blank", title: "Service Unavailable", status: 503, code: "unavailable", detail: "The API is restarting. Try again in a minute.", request_id: "e2e-503", errors: [] },
    });
  });
  const panel = await openPanel(page);
  await panel.locator('input[type="file"]').setInputFiles(file);
  await expect(panel.getByRole("status")).toHaveText("3 valid rows · 1 invalid row");

  const importButton = panel.getByRole("button", { name: "Import 3 rows" });
  await importButton.focus();
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("status")).toHaveText("Importing rates.csv…"); // pending has its own message
  release();

  await expect(panel.getByRole("alert")).toHaveText("The API is restarting. Try again in a minute. Select Retry to try again.");
  await expect(panel.getByRole("status")).toHaveText(""); // no stale "3 valid rows", no second copy of the error
  await expectRing(importButton); // the preview is still accurate, so Import stays and keeps focus
});

test("success and repeat move focus to Open runs and announce the outcome politely", async ({ page }) => {
  await mockAdminApi(page);
  const panel = await openPanel(page);
  const choose = panel.getByRole("button", { name: "Choose CSV…" });
  await choose.focus();
  await chooseByKeyboard(page, choose);
  await page.keyboard.press("Tab");
  await expect(panel.getByRole("button", { name: "Import 3 rows" })).toBeFocused();
  await page.keyboard.press("Enter");

  const openRuns = panel.getByRole("button", { name: "Open runs" });
  await expect(panel.getByRole("status")).toHaveText(/^Imported into Frankfurter FX as run #501: 3 new, 0 updated, 0 unchanged\./);
  await expectRing(openRuns);
  await expect(panel.getByRole("alert")).toHaveText("");

  // The same bytes again, all by keyboard: the skipped run's outcome also lands focus on Open runs.
  await page.keyboard.press("Shift+Tab");
  await chooseByKeyboard(page, choose);
  await page.keyboard.press("Tab");
  await expect(panel.getByRole("button", { name: "Import 3 rows" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("status")).toHaveText("This exact file was already imported as run #501. Nothing new was written.");
  await expectRing(openRuns);
});

test("an import that finishes after focus moved elsewhere leaves focus there", async ({ page }) => {
  await mockAdminApi(page);
  let release!: () => void;
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route(COMMIT, async (route) => {
    await held;
    await route.fallback();
  });
  const panel = await openPanel(page);
  await panel.locator('input[type="file"]').setInputFiles(file);
  await panel.getByRole("button", { name: "Import 3 rows" }).focus();
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("status")).toHaveText("Importing rates.csv…");

  const elsewhere = panel.getByLabel("Source");
  await elsewhere.focus();
  release();
  await expect(panel.getByRole("status")).toHaveText(/^Imported into Frankfurter FX as run #501/);
  await expect(elsewhere).toBeFocused();
});
