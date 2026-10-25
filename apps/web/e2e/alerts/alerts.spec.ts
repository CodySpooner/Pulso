import { expect, test, type Page } from "@playwright/test";

import { mockProductApi, PRODUCT_ID } from "../products/fixtures";
import { alerts, mockAlertsApi, older } from "./fixtures";

// WF-4b (p4-22): the bell, its popover and /alerts against fixture responses (the E2E auth bypass, never a database
// restore). The fixture holds six alerts: three unread today, three read earlier.
const bell = (page: Page) => page.getByTestId("alerts-bell");
const inbox = (page: Page) => page.getByRole("region", { name: "Alerts inbox" }).getByRole("rowheader");

test("the bell shows the unread count, and Mark all read takes it to 0", async ({ page }) => {
  const api = await mockAlertsApi(page);
  await page.goto("/");
  await expect(bell(page)).toHaveAccessibleName("Alerts, 3 unread");
  await expect(bell(page)).toHaveText("3");
  await bell(page).click();
  const menu = page.getByRole("menu", { name: "Alerts" });
  await expect(menu.getByRole("group")).toHaveText([/^Today.*Supplier price rose.*Freight fell.*Supplier ran out of stock/, /^Earlier.*Supplier back in stock/]);
  await expect(menu.getByRole("menuitem", { name: /Supplier price rose/ })).toContainText("$12.40 → $13.90");
  await menu.getByRole("menuitem", { name: "Mark all read" }).click();
  // The open menu is modal: Radix hides the page, bell included, from the accessibility tree until it closes.
  await expect(bell(page)).toHaveAttribute("aria-label", "Alerts, none unread");
  await expect(bell(page)).toHaveText("");
  await expect(menu).toBeVisible(); // it stays open; the dots fade in place
  await expect(menu.getByRole("menuitem", { name: "Mark all read" })).toBeDisabled();
  expect(api.writes).toEqual([{ path: "/v1/alerts/read", body: { all: true } }]);
  await page.keyboard.press("Escape");
  await expect(bell(page)).toHaveAccessibleName("Alerts, none unread");
});

test("two clicks read an alert and open its product's Suppliers tab", async ({ page }) => {
  await mockProductApi(page);
  const api = await mockAlertsApi(page);
  await page.goto("/");
  await bell(page).click(); // 1
  await page.getByRole("menuitem", { name: /^Unread: Supplier price rose/ }).click(); // 2
  await expect(page).toHaveURL(`/products/${PRODUCT_ID}?tab=suppliers`);
  await expect(bell(page)).toHaveAccessibleName("Alerts, 2 unread");
  expect(api.writes).toEqual([{ path: "/v1/alerts/read", body: { ids: [6], all: false } }]);
});

test("keyboard only: Tab to the bell, Enter opens, arrows move, Escape closes and returns focus", async ({ page }) => {
  await mockAlertsApi(page);
  await page.goto("/");
  await expect(page.locator("html[data-app-ready]")).toBeAttached();
  await expect(bell(page)).toHaveAccessibleName("Alerts, 3 unread");
  for (let i = 0; i < 40 && !(await bell(page).evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
  await expect(bell(page)).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menuitem", { name: "Mark all read" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: /Supplier price rose/ })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: /Freight fell/ })).toBeFocused();
  await page.keyboard.press("End");
  await expect(page.getByRole("menuitem", { name: "View all alerts" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toBeHidden();
  await expect(bell(page)).toBeFocused();
});

test("/alerts filters by type and read state through the URL", async ({ page }) => {
  await mockAlertsApi(page);
  await page.goto("/alerts");
  await expect(inbox(page)).toHaveCount(6);
  await page.getByRole("combobox", { name: "Type" }).selectOption("freight_change");
  await expect(page).toHaveURL(/\/alerts\?type=freight_change$/);
  await expect(inbox(page)).toHaveText([/Freight fell/, /Freight rose/]);
  await page.getByRole("combobox", { name: "Read state" }).selectOption("true");
  await expect(inbox(page)).toHaveText([/Unread: Freight fell/]);
  await page.reload(); // the URL keeps both
  await expect(page.getByRole("combobox", { name: "Type" })).toHaveValue("freight_change");
  await expect(page.getByRole("combobox", { name: "Read state" })).toHaveValue("true");
  await expect(inbox(page)).toHaveText([/Freight fell/]);
  await page.getByRole("combobox", { name: "Type" }).selectOption("back_in_stock");
  await expect(page.getByRole("heading", { name: "No alert matches these filters" })).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page).toHaveURL(/\/alerts$/);
  await expect(inbox(page)).toHaveCount(6);
});

test("archive moves a row to Archived, unarchive brings it back, and bulk Mark read sends the selection", async ({ page }) => {
  const api = await mockAlertsApi(page);
  await page.goto("/alerts");
  await page.getByRole("button", { name: /^Archive: Supplier ran out of stock/ }).click();
  await expect(inbox(page)).toHaveCount(5);
  await page.getByRole("link", { name: "Archived" }).click();
  await expect(page).toHaveURL(/\/alerts\?view=archived$/);
  await expect(page.getByRole("region", { name: "Archived alerts" }).getByRole("rowheader")).toHaveText([/Supplier ran out of stock/]);
  await page.getByRole("button", { name: /^Unarchive: Supplier ran out of stock/ }).click();
  await expect(page.getByRole("heading", { name: "Nothing archived" })).toBeVisible();
  await page.getByRole("link", { name: /^Inbox/ }).click();
  await expect(inbox(page)).toHaveCount(6);

  await page.getByRole("checkbox", { name: /^Select Supplier price rose/ }).check();
  await page.getByRole("checkbox", { name: /^Select Freight fell/ }).check();
  await expect(page.getByText("2 selected")).toBeVisible();
  await page.getByRole("button", { name: "Mark read", exact: true }).click();
  await expect(page.getByText("2 selected")).toBeHidden();
  await expect(bell(page)).toHaveAccessibleName("Alerts, 1 unread");
  expect(api.writes).toEqual([
    { path: "/v1/alerts/archive", body: { ids: [4] } },
    { path: "/v1/alerts/unarchive", body: { ids: [4] } },
    { path: "/v1/alerts/read", body: { ids: [6, 5], all: false } },
  ]);
});

test("Load more pages through the keyset, 50 at a time", async ({ page }) => {
  const api = await mockAlertsApi(page, { items: [...alerts(), ...older(50)] });
  await page.goto("/alerts");
  await expect(inbox(page)).toHaveCount(50);
  await page.getByRole("button", { name: "Load more" }).click();
  await expect(inbox(page)).toHaveCount(56);
  await expect(page.getByText("56 alerts, newest first")).toBeVisible();
  await expect(page.getByRole("button", { name: "Load more" })).toBeHidden();
  expect(api.writes).toEqual([]);
});

test("states: rule status lines, empty, error with Retry", async ({ page }) => {
  await mockAlertsApi(page, { items: [] });
  await page.goto("/alerts");
  await expect(page.getByRole("heading", { name: "No alerts yet" })).toBeVisible();
  await expect(page.getByRole("main")).toContainText("3 rules are on, 1 with no source yet. Last evaluation 8h ago.");
  await expect(page.getByRole("main")).toContainText("Testing: freight change: 1 evaluation skipped: data gap Oct 19 → Oct 21.");
  await bell(page).click();
  await expect(page.getByRole("menu")).toContainText("No alerts yet");
  await page.keyboard.press("Escape");

  await page.unrouteAll({ behavior: "ignoreErrors" });
  const api = await mockAlertsApi(page, { status: 503 });
  await page.goto("/alerts");
  await expect(page.getByRole("heading", { name: "Couldn’t load alerts" })).toBeVisible();
  expect(api.writes).toEqual([]);
});
