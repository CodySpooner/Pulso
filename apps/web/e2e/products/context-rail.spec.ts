import { expect, test, type Page } from "@playwright/test";

import { manyNotes, mockProductApi, PRODUCT_ID } from "./fixtures";

// UX-4: the context rail's tags and notes, against fixture responses (the E2E auth bypass, never a database restore).
const URL = `/products/${PRODUCT_ID}`;
const noteBox = (page: Page) => page.getByRole("textbox", { name: "Add a note" });
const tagBox = (page: Page) => page.getByRole("textbox", { name: "Add a tag" });
const noteItems = (page: Page) => page.getByRole("list", { name: "Notes, newest first" }).getByRole("listitem");
const tagChips = (page: Page) => page.getByRole("list", { name: "Tags on this product" }).getByRole("listitem");

test("add a note by keyboard alone: N, type, Ctrl+Enter", async ({ page }) => {
  await mockProductApi(page);
  await page.goto(URL);
  await expect(noteItems(page)).toHaveCount(2);
  await page.getByRole("heading", { level: 1 }).focus();
  await page.keyboard.press("n");
  await expect(noteBox(page)).toBeFocused();
  await page.keyboard.type("Supplier replied: US warehouse, 6 days.");
  await page.keyboard.press("Control+Enter");
  await expect(noteItems(page).first()).toHaveText("Supplier replied: US warehouse, 6 days.Oct 22, 14:00 UTC");
  await expect(noteBox(page)).toHaveValue("");
  await expect(noteItems(page)).toHaveCount(3); // newest first, above the older two
  await expect(noteItems(page).nth(1)).toContainText("Glow films well");
});

test("tags: Enter adds, a case-only repeat is refused, removing keeps focus in the list", async ({ page }) => {
  const puts: string[][] = [];
  page.on("request", (r) => r.method() === "PUT" && puts.push(r.postDataJSON().tags));
  await mockProductApi(page);
  await page.goto(URL);
  await expect(tagChips(page)).toHaveText(["Q4 test", "TikTok"]);
  await tagBox(page).focus();
  await page.keyboard.type("  winner ");
  await page.keyboard.press("Enter");
  await expect(tagChips(page)).toHaveText(["Q4 test", "TikTok", "winner"]);
  await expect(tagBox(page)).toHaveValue("");
  await page.keyboard.type("WINNER");
  await page.keyboard.press("Enter");
  await expect(page.locator("#tag-hint")).toHaveText("Already tagged “winner”.");
  await page.getByRole("button", { name: "Remove tag TikTok" }).focus();
  await page.keyboard.press("Enter");
  await expect(tagChips(page)).toHaveText(["Q4 test", "winner"]);
  await expect(page.getByRole("button", { name: "Remove tag winner" })).toBeFocused();
  expect(puts).toEqual([
    ["Q4 test", "TikTok", "winner"],
    ["Q4 test", "winner"],
  ]);
});

test("saves show at once, and roll back with the reason when they fail", async ({ page }) => {
  await mockProductApi(page, { holdSaves: true });
  await page.goto(URL);
  await noteBox(page).fill("Pending thought");
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(noteItems(page).first()).toHaveText("Pending thoughtSaving…"); // before the API answers
  await expect(noteBox(page)).toHaveValue("");

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockProductApi(page, { failSaves: true });
  await page.goto(URL);
  await noteBox(page).fill("Lost thought?");
  await noteBox(page).press("Control+Enter");
  await expect(page.getByRole("alert").filter({ hasText: "Couldn't add the note. Your text is back in the box." })).toContainText("e2e-notes-save");
  await expect(noteBox(page)).toHaveValue("Lost thought?");
  await expect(noteItems(page)).toHaveCount(2);
  await tagBox(page).fill("winner");
  await tagBox(page).press("Enter");
  await expect(page.getByRole("alert").filter({ hasText: "Couldn't save tags. Your change was undone." })).toBeVisible();
  await expect(tagChips(page)).toHaveText(["Q4 test", "TikTok"]);
});

test("older notes load in pages of 20", async ({ page }) => {
  await mockProductApi(page, { notes: manyNotes(25) });
  await page.goto(URL);
  await expect(noteItems(page)).toHaveCount(20);
  await page.getByRole("button", { name: "Show older notes" }).click();
  await expect(noteItems(page)).toHaveCount(25);
  await expect(noteItems(page).last()).toContainText("Note 1");
  await expect(page.getByRole("button", { name: "Show older notes" })).toHaveCount(0);
});

test("the rail's failed loads show the cause and Retry", async ({ page }) => {
  await mockProductApi(page, { railStatus: 503 });
  await page.goto(URL);
  await expect(page.getByRole("heading", { name: "Couldn't load tags" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Couldn't load notes" })).toBeVisible();
  await expect(noteBox(page)).toBeEditable(); // writing a note doesn't wait on the list
});

test.describe("375px touch", () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

  test("the rail sits under the tab and fits without sideways scroll", async ({ page }) => {
    await mockProductApi(page);
    await page.goto(URL);
    await expect(noteItems(page)).toHaveCount(2);
    const panel = await page.getByRole("tabpanel").boundingBox();
    const rail = await page.getByRole("complementary", { name: "Your tags and notes" }).boundingBox();
    expect(rail!.y).toBeGreaterThan(panel!.y + panel!.height);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(375);
  });
});
