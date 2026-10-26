import { expect, test, type Page } from "@playwright/test";

import { mockExport } from "../discover/export-fixtures";
import { mockTestingApi } from "./fixtures";

// p4-30 WF-7b: the Testing Board's Export CSV and E, against fixture tests and a fixture CSV (the E2E auth bypass).
const FILE = `pulso_testing_${new Date().toISOString().slice(0, 10)}.csv`;
const TESTS = { path: "/api/v1/tests", file: FILE };
const exportButton = (page: Page) => page.getByRole("button", { name: /^(Export CSV|Preparing|Downloaded)/ });
const card = (page: Page, title: string) => page.getByRole("article", { name: title });

test("Export CSV is the next Tab stop after the title, shows its focus ring, and downloads every test", async ({ page }) => {
  await mockTestingApi(page);
  const calls = await mockExport(page, ["file"], TESTS);
  await page.goto("/testing");
  await expect(card(page, "Sunset projection lamp")).toBeVisible();
  await expect(page.getByText("9 tests", { exact: true })).toBeVisible();
  await page.getByRole("heading", { level: 1, name: "Testing" }).focus();
  await page.keyboard.press("Tab");
  await expect(exportButton(page)).toBeFocused();
  expect(await exportButton(page).evaluate((el) => getComputedStyle(el).outlineStyle)).toBe("solid");
  const download = page.waitForEvent("download");
  await page.keyboard.press("Enter"); // 1 press
  expect((await download).suggestedFilename()).toBe(FILE);
  // The board has no filters: no page size or cursor, so the API streams every test, not the newest 100.
  expect(calls.map((url) => url.search)).toEqual(["?format=csv"]);
  await expect(exportButton(page)).toHaveText("Downloaded");
  await expect(page.getByRole("status").filter({ hasText: `Downloaded ${FILE}` })).toBeAttached();
});

test("E exports while focus is on the board, not from a card's menu or the drawer", async ({ page }) => {
  await mockTestingApi(page);
  const calls = await mockExport(page, ["file"], TESTS);
  await page.goto("/testing");
  await expect(exportButton(page)).toHaveAttribute("aria-keyshortcuts", "E");
  await card(page, "Sunset projection lamp").getByRole("button", { name: "Sunset projection lamp", exact: true }).focus();
  const download = page.waitForEvent("download");
  await page.keyboard.press("e");
  expect((await download).suggestedFilename()).toBe(FILE);
  expect(calls.map((url) => url.search)).toEqual(["?format=csv"]);

  await card(page, "Mini waffle maker").getByRole("button", { name: /^Move/ }).press("Enter");
  await expect(page.getByRole("menu")).toBeVisible();
  await page.keyboard.press("e"); // the menu's typeahead, not an export
  await page.keyboard.press("Escape");
  await card(page, "Posture corrector brace").getByRole("button", { name: "Posture corrector brace", exact: true }).press("Enter");
  await expect(page.getByRole("dialog", { name: "Posture corrector brace" })).toBeVisible();
  await page.keyboard.press("e");
  await page.getByLabel("Notes").press("e"); // typing in the drawer
  expect(calls).toHaveLength(1);
});

test("no tests: Export CSV is locked and says there is nothing to export", async ({ page }) => {
  await mockTestingApi(page, { items: [] });
  const calls = await mockExport(page, ["file"], TESTS);
  await page.goto("/testing");
  await expect(page.getByRole("heading", { name: /No tests yet/ })).toBeVisible();
  await expect(exportButton(page)).toHaveAttribute("aria-disabled", "true");
  await exportButton(page).focus(); // locked, still focusable, so its reason can show
  await expect(page.getByRole("tooltip")).toHaveText("Nothing to export");
  await exportButton(page).press("Enter");
  expect(calls).toHaveLength(0);
});

test("a failed export says why and Retry downloads, focus back on Export CSV", async ({ page }) => {
  await mockTestingApi(page);
  const calls = await mockExport(page, ["down", "file"], TESTS);
  await page.goto("/testing");
  await exportButton(page).click();
  const alert = page.getByRole("main").getByRole("alert");
  await expect(alert).toContainText("Couldn't export. The Pulso API didn't answer.");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Retry" }).press("Enter");
  expect((await download).suggestedFilename()).toBe(FILE);
  await expect(exportButton(page)).toBeFocused();
  await expect(alert).toHaveCount(0);
  expect(calls).toHaveLength(2);
});

test("375px: the count line and Export CSV fit with no horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockTestingApi(page);
  await page.goto("/testing");
  await expect(exportButton(page)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
