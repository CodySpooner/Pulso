import { expect, test, type Page } from "@playwright/test";

import { mockProductApi, PRODUCT_ID } from "./fixtures";
import { decided, empty, mockKeywordsApi, type KeywordsMock } from "./keywords-fixtures";

// p3-02 (KW-1) the Trends tab's search keywords against fixture responses (the E2E auth bypass, never a database
// restore). The keywords mock keeps what the page decides, as the API does.
const URL = `/products/${PRODUCT_ID}?tab=trends`;
const section = (page: Page) => page.getByRole("region", { name: "Search keywords" });
const chips = (page: Page) => section(page).getByRole("list", { name: "Confirmed keywords" }).getByRole("listitem");
const suggested = (page: Page) => section(page).getByRole("list", { name: "Suggested keywords" });
const field = (page: Page) => section(page).getByRole("textbox", { name: "Add a keyword" });

async function open(page: Page, options: KeywordsMock = {}, url = URL) {
  await mockProductApi(page);
  const posts = await mockKeywordsApi(page, options);
  await page.goto(url);
  return posts;
}

test("confirming a suggestion is one click: it becomes a chip, leaves the suggestions and stays after a reload", async ({ page }) => {
  const posts = await open(page, {}, `/products/${PRODUCT_ID}`);
  // From the product page: the Trends tab, then Confirm. Two clicks; one once the tab is open.
  await page.getByRole("tab", { name: "Trends" }).click();
  await expect(section(page).getByText("None yet. Confirm a suggestion below, or add your own.")).toBeVisible();
  await suggested(page).getByRole("button", { name: "Confirm sunset projection lamp" }).click();
  await expect(chips(page)).toHaveText(["sunset projection lamp"]);
  await expect(suggested(page).getByText("sunset projection lamp", { exact: true })).toHaveCount(0);
  expect(posts).toEqual([{ keyword: "sunset projection lamp", status: "confirmed" }]);
  // Focus stays in the list, on the row that moved up into its place.
  await expect(suggested(page).getByRole("button", { name: "Confirm lamp" })).toBeFocused();
  await page.reload();
  await expect(chips(page)).toHaveText(["sunset projection lamp"]);
});

test("reject, confirm instead, add by hand and remove round-trip, each decision kept", async ({ page }) => {
  const posts = await open(page);
  await suggested(page).getByRole("button", { name: "Reject usb" }).click();
  const rejected = section(page).getByText("Rejected (1)");
  await expect(rejected).toBeVisible();
  await rejected.click();
  await section(page).getByRole("button", { name: "Confirm usb instead" }).click();
  await expect(chips(page)).toHaveText(["usb"]);

  await field(page).fill("  Galaxy   Lamp ");
  await field(page).press("Enter");
  await expect(chips(page)).toHaveText(["usb", "Added by you: galaxy lamp"]); // typed in: no relevance, so last
  await expect(field(page)).toHaveValue("");
  for (const [typed, message] of [
    ["!!!", "A keyword needs at least one letter or digit."],
    ["GALAXY lamp", "“galaxy lamp” is already confirmed."],
  ]) {
    await field(page).fill(typed);
    await field(page).press("Enter");
    await expect(section(page).getByText(message)).toBeVisible();
  }

  await chips(page).getByRole("button", { name: "Reject galaxy lamp" }).click();
  await expect(chips(page)).toHaveText(["usb"]);
  await expect(chips(page).getByRole("button", { name: "Reject usb" })).toBeFocused(); // no chip after it: the one before
  await expect(section(page).getByText("Rejected (1)")).toBeVisible();
  expect(posts).toEqual([
    { keyword: "usb", status: "rejected" },
    { keyword: "usb", status: "confirmed" },
    { keyword: "  Galaxy   Lamp ", status: "confirmed" },
    { keyword: "galaxy lamp", status: "rejected" },
  ]);
});

test("keyboard alone: Enter confirms and focus walks down the suggestions", async ({ page }) => {
  const posts = await open(page);
  await suggested(page).getByRole("button", { name: "Confirm sunset projection lamp" }).focus();
  await page.keyboard.press("Enter");
  await expect(suggested(page).getByRole("button", { name: "Confirm lamp" })).toBeFocused();
  await page.keyboard.press("Tab"); // Reject lamp
  await page.keyboard.press("Enter");
  await expect(suggested(page).getByRole("button", { name: "Confirm sunset" })).toBeFocused();
  await expect(chips(page)).toHaveText(["sunset projection lamp"]);
  expect(posts.map((p) => `${p.status} ${p.keyword}`)).toEqual(["confirmed sunset projection lamp", "rejected lamp"]);
});

test("loading", async ({ page }) => {
  await open(page, { hold: true });
  await expect(section(page).getByLabel("Loading keywords")).toBeVisible();
});

test("error with Retry, before anything loaded", async ({ page }) => {
  await open(page, { status: 503 });
  await expect(section(page).getByRole("heading", { name: "Couldn't load keywords" })).toBeVisible();
  await expect(section(page).getByRole("button", { name: "Retry" })).toBeVisible();
});

test("titles with nothing to suggest; search interest has no source yet", async ({ page }) => {
  await open(page, { body: empty });
  await expect(section(page).getByText("No usable phrase in this product's titles yet.", { exact: false })).toBeVisible();
  await expect(section(page).getByText("Search interest per keyword · No source yet.")).toBeVisible();
});

test("a failed save is undone and says so", async ({ page }) => {
  await open(page, { body: decided, failSaves: true });
  await suggested(page).getByRole("button", { name: "Confirm lamp" }).click();
  await expect(section(page).getByRole("alert")).toContainText("Couldn't save the keyword. Your change was undone.");
  await expect(chips(page)).toHaveText(["sunset projection lamp", "Added by you: sunset lamp for bedroom"]);
  await expect(suggested(page).getByRole("button", { name: "Confirm lamp" })).toBeVisible();
});

test("two quick decisions: the second lands, and the first one's failure still says so", async ({ page }) => {
  await open(page, { body: decided, failKeywords: ["lamp"] });
  const lamp = suggested(page).getByRole("button", { name: "Confirm lamp" });
  const sunset = suggested(page).getByRole("button", { name: "Confirm sunset" });
  await expect(sunset).toBeVisible();
  // Both in one task, before a re-render, as a quick double tap can (imp-278).
  await page.evaluate((buttons) => { for (const b of buttons) (b as HTMLButtonElement).click(); }, [await lamp.elementHandle(), await sunset.elementHandle()]);
  await expect(section(page).getByRole("alert")).toContainText("Couldn't save the keyword. Your change was undone.");
  await expect(chips(page)).toHaveText(["sunset projection lamp", "sunset", "Added by you: sunset lamp for bedroom"]);
  await expect(lamp).toBeVisible();
});

test("a failed refresh keeps the list with a stale line and Retry", async ({ page }) => {
  await open(page, { body: decided, failSaves: true, refetchStatus: 503 });
  await suggested(page).getByRole("button", { name: "Confirm lamp" }).click(); // fails, so the list is refetched
  const stale = section(page).getByRole("group", { name: "Couldn't refresh keywords" });
  await expect(stale).toBeVisible();
  await expect(stale.getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(chips(page)).toHaveText(["sunset projection lamp", "Added by you: sunset lamp for bedroom"]);
});

test("375px: the keyword rows wrap with no horizontal page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await open(page, { body: decided });
  await expect(chips(page)).toHaveCount(2);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
