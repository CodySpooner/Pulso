import { expect, test, type Page } from "@playwright/test";

import { problem } from "../data-health/fixtures";
import { mockProductApi, PRODUCT_ID } from "../products/fixtures";
import { mockAlertsApi, ruleList } from "./fixtures";

// WF-4c (p4-27): the /alerts Rules tab and the rule builder against fixture responses (the E2E auth bypass, never a
// database restore). The clock is pinned at the fixtures' NOW, 2026-10-22 14:00 UTC.
const list = (page: Page) => page.getByRole("region", { name: "Alert rules" });
const row = (page: Page, name: string) => list(page).getByRole("row").filter({ has: page.getByRole("rowheader", { name: new RegExp(`^${name}`) }) });

test("the Rules tab lists each rule with its status line, and a Testing default offers no delete", async ({ page }) => {
  await mockAlertsApi(page, { rules: ruleList() });
  await page.goto("/alerts");
  await page.getByRole("link", { name: "Rules" }).click();
  await expect(page).toHaveURL(/\/alerts\?view=rules$/);
  await expect(page.getByRole("link", { name: "Rules" })).toHaveAttribute("aria-current", "page");
  await expect(list(page).getByRole("rowheader")).toHaveCount(5);
  await expect(row(page, "Testing: supplier stock-out")).toContainText("No source yet");
  await expect(row(page, "Testing: freight change")).toContainText("1 evaluation skipped: data gap Oct 19 → Oct 21");
  await expect(row(page, "Testing: supplier cost change")).toContainText("Evaluated 8h ago");
  const price = row(page, "Lamp: supplier price");
  await expect(price.getByRole("link", { name: "Sunset projection lamp" })).toHaveAttribute("href", `/products/${PRODUCT_ID}?tab=suppliers`);
  await expect(price).toContainText("offer 4806");
  await expect(price).toContainText("±8%");
  await expect(price).toContainText("Muted until Oct 23, 14:00 UTC");
  await expect(price).toContainText("2h ago");
  await expect(row(page, "Lamp: stock-out")).toContainText("Not evaluated yet");
  await expect(row(page, "Lamp: stock-out")).toContainText("never");
  await expect(page.getByRole("button", { name: "Delete: Lamp: stock-out" })).toBeVisible();
  for (const name of ["Testing: supplier cost change", "Testing: freight change", "Testing: supplier stock-out"]) {
    await expect(page.getByRole("button", { name: `Edit: ${name}` })).toBeVisible();
    await expect(page.getByRole("button", { name: `Delete: ${name}` })).toHaveCount(0);
  }
  await expect(page.getByRole("main")).toContainText("5 rules, newest first · as of Oct 22, 14:00 UTC");
});

test("two clicks make a supplier price rule from the Product Page, and it shows in the Rules tab", async ({ page }) => {
  await mockProductApi(page);
  const api = await mockAlertsApi(page);
  await page.goto(`/products/${PRODUCT_ID}`);
  await page.getByRole("button", { name: "Create alert" }).click(); // 1
  const dialog = page.getByRole("dialog", { name: /^New alert on Sunset projection lamp/ });
  await expect(dialog.getByRole("combobox", { name: "Watch" })).toHaveValue("product");
  await expect(dialog.getByRole("combobox", { name: "Event" })).toHaveValue("supplier_price_change");
  await expect(dialog.getByRole("textbox", { name: "Change, %" })).toHaveValue("5");
  await expect(dialog).toContainText("Discord · Phase 7");
  await dialog.getByRole("button", { name: "Create alert" }).click(); // 2
  await expect(dialog).toBeHidden();
  const name = "Sunset projection lamp with 16 colour modes and remote: supplier price ±5%";
  await expect(page.getByRole("status").filter({ hasText: `${name} is on.` })).toBeVisible();
  expect(api.ruleWrites).toEqual([
    { method: "POST", id: undefined, body: { name, type: "supplier_price_change", target_type: "product", target_id: PRODUCT_ID, params: { pct: 5 }, enabled: true } },
  ]);
  await page.getByRole("link", { name: "View rules" }).click();
  await expect(page).toHaveURL(/\/alerts\?view=rules$/);
  await expect(list(page).getByRole("rowheader").first()).toContainText(name);
});

test("keyboard only: the builder opens with Enter, shows the API's 422 by its field, and Escape returns focus", async ({ page }) => {
  await mockProductApi(page);
  const api = await mockAlertsApi(page);
  await page.goto(`/products/${PRODUCT_ID}`);
  const opener = page.getByRole("button", { name: "Create alert" });
  await opener.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("combobox", { name: "Watch" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("combobox", { name: "Event" })).toBeFocused();
  await page.keyboard.press("Tab");
  const pct = dialog.getByRole("textbox", { name: "Change, %" });
  await expect(pct).toBeFocused();
  await expect(page.locator(":focus-visible")).toHaveAccessibleName("Change, %"); // the ring shows
  await page.keyboard.press("Control+A");
  await page.keyboard.type("0");
  await page.keyboard.press("Enter");
  await expect(dialog.getByRole("alert")).toHaveText("Input should be greater than 0");
  await expect(pct).toHaveAttribute("aria-invalid", "true");
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();
  expect(api.ruleRows).toHaveLength(3); // nothing was made
});

test("enable, mute and unmute persist across a reload, and an edit saves the name and %", async ({ page }) => {
  const api = await mockAlertsApi(page, { rules: ruleList() });
  await page.goto("/alerts?view=rules");
  const notify = page.getByRole("switch", { name: "Notify: Lamp: stock-out" });
  await expect(notify).not.toBeChecked();
  await notify.click();
  await expect(notify).toBeChecked();
  await page.getByRole("button", { name: "Mute: Testing: freight change" }).click();
  await page.getByRole("menuitem", { name: "For 7 days" }).click();
  await expect(row(page, "Testing: freight change")).toContainText("Muted until Oct 29, 14:00 UTC");
  await page.getByRole("button", { name: "Mute: Lamp: supplier price" }).click();
  await page.getByRole("menuitem", { name: "Unmute", exact: true }).click();
  await expect(row(page, "Lamp: supplier price")).not.toContainText("Muted");
  await page.reload();
  await expect(page.getByRole("switch", { name: "Notify: Lamp: stock-out" })).toBeChecked();
  await expect(row(page, "Testing: freight change")).toContainText("Muted until Oct 29, 14:00 UTC");
  await expect(row(page, "Lamp: supplier price")).toContainText("On");

  const edit = page.getByRole("button", { name: "Edit: Testing: supplier cost change" });
  await edit.click();
  const dialog = page.getByRole("dialog", { name: "Edit alert rule" });
  await expect(dialog).toContainText("Products in Testing · every open test");
  await expect(dialog).toContainText("changes price by");
  await dialog.getByRole("textbox", { name: "Change, %" }).fill("7");
  await dialog.getByRole("textbox", { name: "Name" }).fill("Testing: cost ±7%");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
  await expect(edit).toBeHidden(); // renamed
  await expect(row(page, "Testing: cost ±7%")).toContainText("±7%");
  const id = (n: number) => `0a1e0000-0000-4000-8000-00000000000${n}`;
  expect(api.ruleWrites).toEqual([
    { method: "PATCH", id: id(4), body: { enabled: true } },
    { method: "PATCH", id: id(2), body: { muted_until: "2026-10-29T14:00:00.000Z" } },
    { method: "PATCH", id: id(5), body: { muted_until: null } },
    { method: "PATCH", id: id(1), body: { name: "Testing: cost ±7%", params: { pct: 7 } } },
  ]);
});

test("a refused toggle rolls back and says why; delete asks first and removes the rule", async ({ page }) => {
  const api = await mockAlertsApi(page, { rules: ruleList() });
  await page.route("**/api/v1/alert-rules/**", (route) =>
    route.request().method() === "PATCH" ? route.fulfill({ status: 503, contentType: "application/problem+json", json: problem(503, "e2e-rule-patch") }) : route.fallback(),
  );
  await page.goto("/alerts?view=rules");
  const notify = page.getByRole("switch", { name: "Notify: Testing: supplier cost change" });
  await notify.click();
  await expect(page.getByRole("alert").filter({ hasText: "Couldn’t update" })).toContainText("Couldn’t update the rule, so it’s back as it was. The API is restarting.");
  await expect(notify).toBeChecked();

  await page.getByRole("button", { name: "Delete: Lamp: stock-out" }).click();
  const dialog = page.getByRole("dialog", { name: "Delete Lamp: stock-out?" });
  await expect(dialog).toContainText("The alerts it already fired stay in your inbox.");
  await dialog.getByRole("button", { name: "Delete rule" }).click();
  await expect(dialog).toBeHidden();
  await expect(list(page).getByRole("rowheader")).toHaveCount(4);
  expect(api.ruleWrites.filter((w) => w.method === "DELETE")).toEqual([{ method: "DELETE", id: "0a1e0000-0000-4000-8000-000000000004", body: null }]);
});

test("states: no rules, and an error with Retry", async ({ page }) => {
  await mockAlertsApi(page, { rules: [] });
  await page.goto("/alerts?view=rules");
  await expect(page.getByRole("heading", { name: "No rules yet" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Find a product in Discover" })).toHaveAttribute("href", "/discover");

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockAlertsApi(page, { rulesStatus: 503 });
  await page.goto("/alerts?view=rules");
  await expect(page.getByRole("heading", { name: "Couldn’t load your rules" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});
