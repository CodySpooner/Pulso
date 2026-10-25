import { expect, test, type Page } from "@playwright/test";

import { NOW } from "../data-health/fixtures";
import { configured, firstRun, mockSettingsApi, refocus } from "./fixtures";

// UX-10 Settings against fixture responses (the E2E auth bypass, never a database restore).
const field = (page: Page, label: string) => page.getByRole("textbox", { name: label });
const alert = (page: Page) => page.getByRole("form", { name: "Workspace settings" }).getByRole("alert");
const save = (page: Page) => page.getByRole("button", { name: /^(Save changes|Saving…)$/ });
const reset = (page: Page) => page.getByRole("button", { name: "Reset" });
const status = (page: Page) => page.getByRole("status").filter({ hasText: /as of|Unsaved|Saving/ });
const saved = {
  payment_fee_bps: 290,
  payment_fee_fixed_minor: 30,
  shopify_fee_bps: 0,
  default_cpa_minor: 1500,
  target_margin_bps: 2000,
  duty_default_bps: 1500,
  returns_bps: 500,
  customs_fee_minor: 150,
};

test("loads the settings in percent and dollars, with the market locked", async ({ page }) => {
  await mockSettingsApi(page);
  await page.goto("/settings");
  await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
  await expect(page.getByRole("region").getByRole("heading", { level: 2 })).toHaveText(["Market", "Fees", "Target margin", "Duty default", "Returns %"]);
  await expect(field(page, "Processing rate")).toHaveValue("2.9");
  await expect(field(page, "Fixed fee per order")).toHaveValue("0.30");
  await expect(field(page, "Shopify transaction fee")).toHaveValue("0");
  await expect(field(page, "Ad cost per order (CPA)")).toHaveValue("15.00");
  await expect(field(page, "Target margin")).toHaveValue("20");
  await expect(field(page, "Default duty rate")).toHaveValue("15");
  await expect(field(page, "Import fee per order")).toHaveValue("1.50");
  await expect(field(page, "Refund rate")).toHaveValue("5");
  await expect(page.getByRole("radio", { name: "Set a rate" })).toBeChecked();
  // The market is read-only text, not a disabled input.
  const market = page.getByRole("region", { name: "Market" });
  await expect(market.getByRole("textbox")).toHaveCount(0);
  await expect(market).toContainText("United StatesUS, locked");
  await expect(market).toContainText("US dollarUSD, locked");
  // Clean: no assumptions to check, Save and Reset locked, and the data's as-of time.
  await expect(page.getByRole("region", { name: /assumptions? to check/ })).toHaveCount(0);
  await expect(save(page)).toHaveAttribute("aria-disabled", "true");
  await expect(reset(page)).toHaveAttribute("aria-disabled", "true");
  await expect(status(page)).toHaveText(`Your workspace's settings · as of Oct 22, 14:00 UTC`);
  // Numbers read right-aligned in tabular numerals.
  await expect(field(page, "Processing rate")).toHaveCSS("text-align", "right");
  await expect(field(page, "Processing rate")).toHaveCSS("font-variant-numeric", "tabular-nums");
});

test("editing a fee and saving takes two clicks and sends basis points and cents", async ({ page }) => {
  const { patches } = await mockSettingsApi(page);
  await page.goto("/settings");
  const rate = field(page, "Processing rate");
  await rate.click(); // click 1
  await rate.fill("3.4");
  await expect(status(page)).toHaveText("Unsaved changes");
  await expect(save(page)).toHaveAttribute("aria-disabled", "false");
  await save(page).click(); // click 2
  await expect(page.getByRole("status").filter({ hasText: "Saved." })).toHaveText("Saved. The next margin uses these · as of Oct 22, 14:00 UTC");
  expect(patches).toEqual([{ ...saved, payment_fee_bps: 340 }]);
  await expect(save(page)).toHaveAttribute("aria-disabled", "true");
  await expect(save(page)).toBeFocused(); // aria-disabled, so focus stays on the button that saved
  await expect(rate).toHaveValue("3.4");
});

test("Reset returns every field to the saved values", async ({ page }) => {
  const { patches } = await mockSettingsApi(page);
  await page.goto("/settings");
  await field(page, "Refund rate").fill("8");
  await field(page, "Fixed fee per order").fill("0.5");
  await reset(page).click();
  await expect(field(page, "Refund rate")).toHaveValue("5");
  await expect(field(page, "Fixed fee per order")).toHaveValue("0.30");
  await expect(save(page)).toHaveAttribute("aria-disabled", "true");
  expect(patches).toEqual([]);
  // "2.90" is the saved 2.9: not a change.
  await field(page, "Processing rate").fill("2.90");
  await expect(save(page)).toHaveAttribute("aria-disabled", "true");
});

test("invalid input shows on blur, blocks Save and focuses the field", async ({ page }) => {
  const { patches } = await mockSettingsApi(page);
  await page.goto("/settings");
  const refunds = field(page, "Refund rate");
  await refunds.fill("101");
  await expect(refunds).not.toHaveAttribute("aria-invalid"); // not while typing
  await refunds.blur();
  await expect(refunds).toHaveAttribute("aria-invalid", "true");
  await expect(refunds).toHaveAccessibleDescription("Enter 100% or less.");
  await field(page, "Fixed fee per order").fill("0.305");
  await field(page, "Target margin").focus();
  await save(page).click();
  await expect(alert(page)).toHaveText("Fix 2 fields to save: Fixed fee per order, Refund rate.");
  await expect(field(page, "Fixed fee per order")).toBeFocused();
  await expect(field(page, "Fixed fee per order")).toHaveAccessibleDescription("Use whole cents: at most 2 decimals.");
  expect(patches).toEqual([]);
  await field(page, "Fixed fee per order").fill("0.35");
  await refunds.fill("10");
  await expect(alert(page)).toHaveCount(0);
  await save(page).click();
  await expect.poll(() => patches).toEqual([{ ...saved, payment_fee_fixed_minor: 35, returns_bps: 1000 }]);
});

test("a failed save keeps the input and says why, with the error ID", async ({ page }) => {
  const { patches } = await mockSettingsApi(page, { failSaves: true });
  await page.goto("/settings");
  await field(page, "Processing rate").fill("3.1");
  await field(page, "Refund rate").fill("7.25");
  await save(page).click();
  await expect(alert(page)).toContainText("Couldn't save. Your changes are still here. The API is restarting. Try again.");
  await expect(alert(page)).toContainText("Error ID e2e-settings-save");
  await expect(alert(page).getByRole("button", { name: "Copy error ID" })).toBeVisible();
  await expect(field(page, "Processing rate")).toHaveValue("3.1");
  await expect(field(page, "Refund rate")).toHaveValue("7.25");
  await expect(save(page)).toHaveAttribute("aria-disabled", "false"); // still dirty: try again
  expect(patches).toHaveLength(1);
});

test("an API 422 lands on the field it names", async ({ page }) => {
  await mockSettingsApi(page, {
    rejectSaves: [{ loc: ["body", "returns_bps"], msg: "Input should be less than or equal to 10000", type: "less_than_equal" }],
  });
  await page.goto("/settings");
  await field(page, "Refund rate").fill("9");
  await save(page).click();
  await expect(field(page, "Refund rate")).toHaveAccessibleDescription("Input should be less than or equal to 10000");
  await expect(field(page, "Refund rate")).toHaveValue("9");
  await field(page, "Refund rate").fill("8");
  await expect(field(page, "Refund rate")).toHaveAccessibleDescription("Share of revenue refunded.");
});

test("duty: not set is its own state, and 0% is a rate", async ({ page }) => {
  const { patches } = await mockSettingsApi(page, { settings: firstRun });
  await page.goto("/settings");
  const checks = page.getByRole("region", { name: "2 assumptions to check" });
  await expect(checks).toContainText("Duty isn't set, so landed margins stay incomplete.");
  await expect(checks).toContainText("Payment processing is 0%, so margins count no processor fee.");
  await expect(page.getByRole("radio", { name: "Not set" })).toBeChecked();
  await expect(page.getByRole("region", { name: "Duty default" })).toContainText(
    "Duty not set. Landed margins that need it stay incomplete and read “duty not set” until you set a rate, or the supplier's quote is DDP (duties paid).",
  );
  await expect(field(page, "Default duty rate")).toHaveCount(0);

  // One click from the banner opens an empty rate box, never a pre-filled 0.
  await checks.getByRole("button", { name: "Set duty" }).click();
  await expect(field(page, "Default duty rate")).toBeFocused();
  await expect(field(page, "Default duty rate")).toHaveValue("");
  await save(page).click();
  await expect(alert(page)).toHaveText("Fix 1 field to save: Default duty rate.");
  await expect(field(page, "Default duty rate")).toHaveAccessibleDescription("Enter a duty rate. 0% is a valid rate.");

  await field(page, "Default duty rate").fill("0");
  await save(page).click();
  await expect.poll(() => patches.at(-1)?.duty_default_bps).toBe(0);
  await expect(page.getByRole("region", { name: "1 assumption to check" })).not.toContainText("Duty");
  await expect(field(page, "Default duty rate")).toHaveValue("0");

  await page.locator("label").filter({ hasText: /^Not set$/ }).click(); // the segment, as a pointer user presses it
  await expect(page.getByRole("radio", { name: "Not set" })).toBeChecked();
  await save(page).click();
  await expect.poll(() => patches.length).toBe(2);
  expect(patches[1].duty_default_bps).toBeNull();
  await expect(page.getByRole("region", { name: "2 assumptions to check" })).toBeVisible();
});

test("keyboard: every field is reachable with a visible ring, and Ctrl+S saves only when dirty", async ({ page }) => {
  const { patches } = await mockSettingsApi(page);
  await page.goto("/settings");
  await expect(page.locator("html")).toHaveAttribute("data-app-ready", "true");
  await field(page, "Processing rate").focus();
  const order = ["Fixed fee per order", "Shopify transaction fee", "Ad cost per order (CPA)", "Target margin"];
  for (const label of order) {
    await page.keyboard.press("Tab");
    await expect(field(page, label)).toBeFocused();
    // The ring is drawn on the field's box, around the unit.
    await expect(field(page, label).locator("..")).toHaveCSS("outline-style", "solid");
  }
  await page.keyboard.press("Tab");
  await expect(page.getByRole("radio", { name: "Set a rate" })).toBeFocused();
  await expect(page.locator("label", { has: page.getByRole("radio", { name: "Set a rate" }) })).toHaveCSS("outline-style", "solid");
  await page.keyboard.press("Tab");
  await expect(field(page, "Default duty rate")).toBeFocused();

  await page.keyboard.press("Control+s"); // clean: nothing to save, and no browser dialog
  await page.keyboard.press("End"); // Tab selected the value
  await page.keyboard.type("2");
  await expect(field(page, "Default duty rate")).toHaveValue("152");
  await page.keyboard.press("Control+s");
  await expect.poll(() => patches).toEqual([{ ...saved, duty_default_bps: 15_200 }]);
  await expect(field(page, "Default duty rate")).toBeFocused();
});

test("loading shows the form skeleton; a failed load says why with Retry", async ({ page }) => {
  await mockSettingsApi(page, { hold: true });
  await page.goto("/settings");
  await expect(page.locator(".bg-skeleton").first()).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "Loading your settings…" })).toBeAttached();

  const other = await page.context().newPage();
  await mockSettingsApi(other, { status: 503 });
  await other.goto("/settings");
  await expect(other.getByRole("heading", { level: 2, name: "Couldn't load your settings" })).toBeVisible();
  await expect(other.getByText("Error ID e2e-settings-503")).toBeVisible();
  await expect(other.getByRole("button", { name: "Retry" })).toBeVisible();
});

test("a failed refresh keeps the form and the owner's edit, marked stale", async ({ page }) => {
  const api = await mockSettingsApi(page);
  await page.goto("/settings");
  await field(page, "Refund rate").fill("6");
  api.failGets();
  await page.clock.setFixedTime(new Date(NOW.getTime() + 6 * 60_000)); // past the 5-minute stale time
  await refocus(page);
  const stale = page.getByRole("group", { name: "Couldn't refresh your settings" });
  await expect(stale).toContainText("Showing data as of Oct 22, 14:00 UTC");
  await expect(field(page, "Refund rate")).toHaveValue("6");
});

test("375px: no sideways scroll, and the save bar sits above the tab bar", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockSettingsApi(page, { settings: firstRun });
  await page.goto("/settings");
  await expect(field(page, "Processing rate")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
  const bar = await save(page).boundingBox();
  const tabs = await page.getByRole("navigation", { name: "Tab bar" }).boundingBox();
  expect(bar && tabs && bar.y + bar.height <= tabs.y).toBe(true);
  await field(page, "Refund rate").fill("5");
  await expect(save(page)).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
});

test("the shell links to Settings", async ({ page }) => {
  await mockSettingsApi(page, { settings: configured });
  await page.goto("/");
  await page.getByRole("link", { name: "Settings" }).first().click();
  await expect(page).toHaveURL("/settings");
  await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
});
