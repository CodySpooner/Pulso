import { expect, test, type Page } from "@playwright/test";

import { mockProductApi, PRODUCT_ID } from "../products/fixtures";
import { lists, mockAlertsApi, PET_LIST, scoreRules } from "./fixtures";

// p4-34 (WF-4d, DEC-353): the builder's velocity spike and Saturation cross verbs, and their rules in the list, against
// fixture responses (the E2E auth bypass, never a database restore). The clock is pinned at 2026-10-22 14:00 UTC.
const LAMP = "Sunset projection lamp with 16 colour modes and remote";
const list = (page: Page) => page.getByRole("region", { name: "Alert rules" });
const row = (page: Page, name: string) => list(page).getByRole("row").filter({ has: page.getByRole("rowheader", { name: new RegExp(`^${name}`) }) });

async function openBuilder(page: Page) {
  await mockProductApi(page);
  const api = await mockAlertsApi(page, { lists: lists() });
  await page.goto(`/products/${PRODUCT_ID}`);
  await page.getByRole("button", { name: "Create alert" }).focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("combobox", { name: "Watch" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("combobox", { name: "Event" })).toBeFocused();
  return { api, dialog };
}

test("keyboard only: a velocity spike rule on the product takes Enter, one letter and Enter", async ({ page }) => {
  const { api, dialog } = await openBuilder(page);
  await page.keyboard.press("v"); // the verb's first letter picks it
  await expect(dialog.getByRole("combobox", { name: "Event" })).toHaveValue("velocity_spike");
  await expect(dialog.getByRole("combobox", { name: "Watch" })).toHaveValue("product");
  await expect(dialog.getByRole("combobox", { name: "Watch" }).getByRole("option")).toHaveText(["this product", "any product on Pet"]);
  await expect(dialog).toContainText("A night with a data gap in either week is skipped");
  await page.keyboard.press("Tab");
  const rise = dialog.getByRole("textbox", { name: "Rise, %" });
  await expect(rise).toBeFocused();
  await expect(rise).toHaveValue("50");
  await expect(page.locator(":focus-visible")).toHaveAccessibleName("Rise, %"); // the ring shows
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("textbox", { name: "Units in 7 days, at least" })).toHaveValue("10");
  await page.keyboard.press("Enter");
  await expect(dialog).toBeHidden();
  const name = `${LAMP}: velocity +50%`;
  await expect(page.getByRole("status").filter({ hasText: `${name} is on.` })).toBeVisible();
  expect(api.ruleWrites).toEqual([
    { method: "POST", id: undefined, body: { name, type: "velocity_spike", target_type: "product", target_id: PRODUCT_ID, params: { pct: 50, min_volume: 10 }, enabled: true } },
  ]);
});

test("keyboard only: a Saturation cross on a watchlist, with the API's 422 beside the line", async ({ page }) => {
  const { api, dialog } = await openBuilder(page);
  await page.keyboard.press("s");
  await expect(dialog.getByRole("combobox", { name: "Event" })).toHaveValue("saturation_cross");
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("a"); // "any product on Pet"
  await expect(dialog.getByRole("combobox", { name: "Watch" })).toHaveValue(`watchlist:${PET_LIST}`);
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("combobox", { name: "Direction" })).toBeFocused();
  await page.keyboard.press("b");
  await page.keyboard.press("Tab");
  const line = dialog.getByRole("textbox", { name: "Saturation, 0–100" });
  await expect(line).toHaveValue("65");
  await expect(page.locator(":focus-visible")).toHaveAccessibleName("Saturation, 0–100");
  await page.keyboard.press("Control+A");
  await page.keyboard.type("130");
  await page.keyboard.press("Enter");
  await expect(dialog.getByRole("alert")).toHaveText("Saturation runs from 0 to 100."); // imp-585: never Pydantic's text
  await expect(line).toHaveAttribute("aria-invalid", "true");
  await page.keyboard.press("Control+A");
  await page.keyboard.type("35");
  await page.keyboard.press("Enter");
  await expect(dialog).toBeHidden();
  expect(api.ruleWrites.at(-1)).toEqual({
    method: "POST",
    id: undefined,
    body: { name: `${LAMP}: saturation below 35`, type: "saturation_cross", target_type: "watchlist", target_id: PET_LIST, params: { threshold: 35, direction: "below" }, enabled: true },
  });
  await page.getByRole("link", { name: "View rules" }).click();
  const made = row(page, `${LAMP}: saturation below 35`);
  await expect(made.getByRole("link", { name: "Pet" })).toHaveAttribute("href", `/watchlists?list=${PET_LIST}`);
  await expect(made).toContainText("every product on it");
  await expect(made).toContainText("below 35");
});

test("the list shows a velocity spike's gap skip and score thresholds, and an edit saves its params", async ({ page }) => {
  const api = await mockAlertsApi(page, { rules: scoreRules() });
  await page.goto("/alerts?view=rules");
  const spike = row(page, "Lamp: velocity");
  await expect(spike).toContainText("1 evaluation skipped: data gap Oct 8 → Oct 22");
  await expect(spike).toContainText("Velocity+50% · ≥10 /7d");
  await expect(spike.getByRole("link", { name: "Sunset projection lamp" })).toHaveAttribute("href", `/products/${PRODUCT_ID}?tab=trends`);
  await expect(spike).toContainText("this product");
  const crowded = row(page, "Pet: saturation");
  await expect(crowded).toContainText("No source yet");
  await expect(crowded).toContainText("Saturationabove 65");
  await page.getByRole("button", { name: "Edit: Lamp: velocity +50%" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit alert rule" });
  await expect(dialog).toContainText("velocity rises by");
  await dialog.getByRole("textbox", { name: "Rise, %" }).fill("80");
  await dialog.getByRole("button", { name: "Save rule" }).click();
  await expect(dialog).toBeHidden();
  await expect(spike).toContainText("+80% · ≥10 /7d");
  expect(api.ruleWrites).toEqual([{ method: "PATCH", id: "0a1e0000-0000-4000-8000-000000000007", body: { name: "Lamp: velocity +50%", params: { pct: 80, min_volume: 10 } } }]);
});
