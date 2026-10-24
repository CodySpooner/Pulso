import { expect, test, type Page } from "@playwright/test";

import { activity, mockAdminApi, withActivity } from "./fixtures";

// imp-161 (DEC-216): the CJ row counts down CJ's 30-day inactivity rule (1600014) from the owner's latest order,
// in words with an icon, and a new order is two clicks away: Add order (or Update order), then Save order.
const cjRow = (page: Page) => page.getByRole("region", { name: "Sources table" }).getByRole("row", { name: /CJ Dropshipping/ });

for (const [state, days, text, asOf] of [
  ["ok", 22, "22 days left", "Last order Oct 14"],
  ["warn", 5, "5 days left", "Last order Sep 27"],
] as const) {
  test(`${state}: the CJ row shows the days left and the order's date, and explains itself on focus`, async ({ page }) => {
    await mockAdminApi(page, { sources: withActivity(activity(state, days)) });
    await page.goto("/admin/data-health");
    const row = cjRow(page);
    const status = row.getByRole("button", { name: text });
    await expect(status).toBeVisible();
    await expect(row.getByText(asOf)).toBeVisible();
    await expect(row.locator("time", { hasText: asOf.slice(11) })).toHaveAttribute("title", /^Latest CJ order .+ UTC, entered .+ · GET \/v1\/admin\/sources$/);
    await status.focus();
    await expect(page.getByRole("tooltip")).toContainText(state === "ok" ? "UTC days until" : "Place a CJ order before the 30 days run out");
    // Other sources have no activity line.
    await expect(page.getByRole("region", { name: "Sources table" }).getByText("Activity")).toHaveCount(1);
  });
}

test("round trip: no evidence yet, then Add order and Save order count down from the entered order", async ({ page }) => {
  const calls = await mockAdminApi(page, { sources: withActivity({ state: "unknown", days_remaining: null, as_of: null, observed_at: null }) });
  await page.goto("/admin/data-health");
  const row = cjRow(page);
  await expect(row.getByRole("button", { name: "No evidence yet" })).toBeVisible();
  await expect(row.locator('time[title^="Latest CJ order"]')).toHaveCount(0); // no order date, and never a number

  await row.getByRole("button", { name: "Add order for CJ activity" }).click(); // click 1
  const dialog = page.getByRole("dialog", { name: "Latest CJ order" });
  const at = dialog.getByLabel("Order date and time (UTC)");
  await expect(at).toBeFocused();
  await at.fill("2026-10-20T09:30");
  await dialog.getByLabel("Amount").fill("42.50");
  await expect(dialog.getByLabel("Currency")).toHaveValue("USD");
  await dialog.getByRole("button", { name: "Save order" }).click(); // click 2

  await expect(dialog).toBeHidden();
  expect(calls.filter((c) => c.method === "PUT")).toEqual([
    {
      method: "PUT",
      path: "/v1/admin/sources/cj/activity",
      body: { kind: "owner_entry", transaction_at: "2026-10-20T09:30:00.000Z", amount_minor: 4250, currency: "USD" },
    },
  ]);
  await expect(page.getByRole("status").filter({ hasText: "Order saved" })).toHaveText("Order saved. CJ Dropshipping activity: 28 days left.");
  await expect(row.getByRole("button", { name: "28 days left" })).toBeVisible();
  await expect(row.getByText("Last order Oct 20")).toBeVisible();
  await expect(row.getByRole("button", { name: "Update order for CJ activity" })).toBeFocused(); // focus returns to the row
});

test("the form refuses a future time and a zero amount before sending; Escape sends nothing", async ({ page }) => {
  const calls = await mockAdminApi(page, { sources: withActivity(activity("ok", 22)) });
  await page.goto("/admin/data-health");
  await cjRow(page).getByRole("button", { name: "Update order for CJ activity" }).click();
  const dialog = page.getByRole("dialog", { name: "Latest CJ order" });
  const at = dialog.getByLabel("Order date and time (UTC)");
  await at.fill("2026-10-22T15:00"); // an hour after the pinned clock
  await dialog.getByLabel("Amount").fill("0");
  await dialog.getByRole("button", { name: "Save order" }).click();
  expect(await at.evaluate((el: HTMLInputElement) => el.validity.rangeOverflow)).toBe(true);
  await at.fill("2026-10-22T13:00");
  await dialog.getByRole("button", { name: "Save order" }).click();
  expect(await dialog.getByLabel("Amount").evaluate((el: HTMLInputElement) => el.validity.valid)).toBe(false);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(cjRow(page).getByRole("button", { name: "Update order for CJ activity" })).toBeFocused();
  expect(calls.filter((c) => c.method === "PUT")).toEqual([]);
});

// imp-151 (XR-8): the field's native step and min assumed 2 decimals, so the browser blocked 1.255 KWD and offered
// to round it. toMinor alone now judges the amount, by the currency's ISO decimals.
test("a three-decimal KWD amount saves exactly: 1.255 KWD is 1255 minor units", async ({ page }) => {
  const calls = await mockAdminApi(page, { sources: withActivity(activity("ok", 22)) });
  await page.goto("/admin/data-health");
  await cjRow(page).getByRole("button", { name: "Update order for CJ activity" }).click(); // click 1
  const dialog = page.getByRole("dialog", { name: "Latest CJ order" });
  await dialog.getByLabel("Order date and time (UTC)").fill("2026-10-20T09:30");
  await dialog.getByLabel("Amount").fill("1.255");
  await dialog.getByLabel("Currency").fill("KWD");
  await dialog.getByRole("button", { name: "Save order" }).click(); // click 2
  await expect(dialog).toBeHidden();
  expect(calls.filter((c) => c.method === "PUT").map((c) => c.body)).toEqual([
    { kind: "owner_entry", transaction_at: "2026-10-20T09:30:00.000Z", amount_minor: 1255, currency: "KWD" },
  ]);
});

// imp-151 (XR-7): a currency the API can't read is refused on its own field before anything is sent.
test("a currency outside the API's list is refused on the Currency field; fixing it sends one PUT", async ({ page }) => {
  const calls = await mockAdminApi(page, { sources: withActivity(activity("ok", 22)) });
  await page.goto("/admin/data-health");
  await cjRow(page).getByRole("button", { name: "Update order for CJ activity" }).click();
  const dialog = page.getByRole("dialog", { name: "Latest CJ order" });
  await dialog.getByLabel("Order date and time (UTC)").fill("2026-10-20T09:30");
  await dialog.getByLabel("Amount").fill("150000");
  const currency = dialog.getByLabel("Currency");
  await currency.fill("idr");
  await dialog.getByRole("button", { name: "Save order" }).click();
  expect(await currency.evaluate((el: HTMLInputElement) => el.validationMessage)).toBe(
    "Use a currency Pulso supports: USD, EUR, GBP, CAD, AUD, CNY, JPY, or KWD.",
  );
  expect(await dialog.getByLabel("Amount").evaluate((el: HTMLInputElement) => el.validity.valid)).toBe(true);
  expect(calls.filter((c) => c.method === "PUT")).toEqual([]);
  await currency.fill("JPY"); // a changed field clears the message, so the next Save checks again
  await dialog.getByRole("button", { name: "Save order" }).click();
  await expect(dialog).toBeHidden();
  expect(calls.filter((c) => c.method === "PUT").map((c) => c.body)).toEqual([
    { kind: "owner_entry", transaction_at: "2026-10-20T09:30:00.000Z", amount_minor: 150000, currency: "JPY" },
  ]);
});

test("phone: the CJ card lists its activity without page overflow", async ({ page }) => {
  await mockAdminApi(page, { sources: withActivity(activity("warn", 5)) });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/admin/data-health");
  const card = page.getByRole("listitem").filter({ has: page.getByRole("button", { name: "CJ Dropshipping: open runs" }) });
  await expect(card.getByRole("button", { name: "5 days left" })).toBeVisible();
  await expect(card.getByRole("button", { name: "Update order for CJ activity" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});
