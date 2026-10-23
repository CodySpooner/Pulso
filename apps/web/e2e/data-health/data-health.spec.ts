import { expect, test, type Page } from "@playwright/test";

import { healthySources, host, mockAdminApi, operationId, sources } from "./fixtures";

// DH-2 / DH-3 (P1-12): the Data Health page and nav badge against fixture DH-1 responses (E2E auth bypass).

const PAGE = "/admin/data-health";

async function open(page: Page) {
  await page.goto(PAGE);
  await expect(page.getByRole("heading", { level: 1, name: "Data Health" })).toBeVisible();
}

test("renders every DH-1 field from fixtures", async ({ page }) => {
  await mockAdminApi(page);
  await open(page);
  await expect(page.getByText("As of Oct 22, 14:00 UTC")).toBeVisible();

  const hostCard = page.getByRole("region", { name: "Collector host" });
  await expect(hostCard).toContainText("pulso-pc");
  await expect(hostCard).toContainText("4m ago");
  await expect(hostCard).toContainText("Off here: live collectors run only on the collector host");
  await expect(hostCard).toContainText("3 missed slots · latest Google Trends");

  const backups = page.getByRole("region", { name: "Backups" });
  await expect(backups).toContainText("10h ago");
  await expect(backups).toContainText("1 of 14 failed");

  const table = page.getByRole("region", { name: "Sources table" });
  for (const [name, status] of [
    ["Shopify stores", "Blocked"],
    ["CJ Dropshipping", "Healthy"],
    ["Google Trends", "Overdue"],
    ["Frankfurter FX", "Disabled"],
  ]) {
    await expect(table.getByRole("row", { name: new RegExp(name) })).toContainText(status);
  }
  await expect(table).not.toContainText("Backups"); // the backup pseudo-source has its own card
  const cj = table.getByRole("row", { name: /CJ Dropshipping/ });
  await expect(cj).toContainText("1,240 / 36 / 112");
  await expect(cj).toContainText("as of 1h ago");
  await expect(table.getByRole("row", { name: /Shopify stores/ })).toContainText("5 consecutive 429 responses");
  await expect(table.getByRole("row", { name: /Shopify stores/ })).toContainText("429");
  await expect(table.getByRole("row", { name: /Frankfurter FX/ })).toContainText("Not collected yet"); // missing, never 0
  await expect(table.getByRole("row", { name: /AliExpress/ })).toContainText("No source yet · arrives in Phase 3");

  await expect(page.getByRole("img", { name: /^Shopify stores, last 90 days/ })).toBeVisible();
  await expect(page.getByRole("img", { name: /^Google Trends, last 90 days: .*missed \(gap\)/ })).toBeVisible();
  const gaps = page.getByRole("region", { name: "Open gaps" });
  await expect(gaps.getByRole("row", { name: /Google Trends/ })).toContainText("Host offline");
  await expect(gaps.getByRole("row", { name: /Google Trends/ })).toContainText("2");
  await expect(page.getByRole("heading", { name: "Import arrives with P1-11c" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Choose CSV…" })).toBeDisabled();

  // Run drawer: error text and raw-payload ids for the newest run, plus the source's remaining fields.
  await table.getByRole("button", { name: "Shopify stores: open runs" }).click();
  const drawer = page.getByRole("dialog", { name: "Shopify stores" });
  await expect(drawer).toContainText("429 Too Many Requests (retry-after 60)");
  await expect(drawer).toContainText("blocked_429");
  await expect(drawer).toContainText("#9001");
  await expect(drawer).toContainText("4 approved targets");
  await expect(drawer).toContainText("Retry not before");
  await expect(drawer.getByRole("button", { name: /#380/ })).toHaveAttribute("aria-expanded", "false");
});

test("toggle and Run now call patch_source and run_source", async ({ page }) => {
  const calls = await mockAdminApi(page, { host: { live_runs_allowed: true } });
  await open(page);
  const table = page.getByRole("region", { name: "Sources table" });
  const writes = () => calls.filter((c) => c.method !== "GET");

  // Disabling a source asks for an optional reason.
  await table.getByRole("switch", { name: "CJ Dropshipping enabled" }).click();
  await page.getByRole("dialog", { name: "Disable CJ Dropshipping?" }).getByRole("textbox").fill("seed review");
  await page.getByRole("button", { name: "Disable", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "CJ Dropshipping disabled." })).toBeVisible();

  // Re-enabling a blocked source needs a typed reason (§4.2): an empty reason can't be submitted.
  await table.getByRole("switch", { name: "Shopify stores enabled" }).click();
  const reenable = page.getByRole("dialog", { name: "Re-enable Shopify stores?" });
  await reenable.getByRole("button", { name: "Re-enable" }).click();
  await expect(reenable).toBeVisible();
  await reenable.getByRole("textbox").fill("retry-after passed");
  await reenable.getByRole("button", { name: "Re-enable" }).click();
  await expect(reenable).toBeHidden();

  await table.getByRole("button", { name: "Run CJ Dropshipping now" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Run #500 queued for CJ Dropshipping." })).toBeVisible();

  expect(writes()).toEqual([
    { method: "PATCH", path: "/v1/admin/sources/cj", body: { enabled: false, reason: "seed review" } },
    { method: "PATCH", path: "/v1/admin/sources/shopify_stores", body: { enabled: true, reason: "retry-after passed" } },
    { method: "POST", path: "/v1/admin/sources/cj/run", body: null },
  ]);
  expect(writes().map((c) => operationId(c.method, c.path))).toEqual(["patch_source", "patch_source", "run_source"]);
});

test("Run now is unavailable off the collector host and says why", async ({ page }) => {
  const calls = await mockAdminApi(page);
  await open(page);
  const run = page.getByRole("region", { name: "Sources table" }).getByRole("button", { name: "Run CJ Dropshipping now" });
  await expect(run).toHaveAttribute("aria-disabled", "true");
  await run.focus();
  await expect(page.getByRole("tooltip")).toContainText("Live collectors run only on the collector host.");
  await run.click({ force: true }); // aria-disabled: Playwright would wait for it to enable
  expect(calls.filter((c) => c.method === "POST")).toEqual([]);
});

test.describe("DH-3 nav badge", () => {
  test("counts blocked, failing and overdue sources", async ({ page }) => {
    await mockAdminApi(page);
    await page.goto("/");
    const link = page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: /Data Health/ });
    await expect(link).toHaveAccessibleName(/^Data Health\W+2 sources need attention$/);
    await expect(link.getByTestId("data-health-badge")).toHaveText("2");
  });

  test("clears when no source needs attention", async ({ page }) => {
    await mockAdminApi(page, { sources: healthySources, host: { open_gaps: [] } });
    await page.goto("/");
    const link = page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: /Data Health/ });
    await expect(page.getByText("Online · 4m ago").first()).toBeVisible(); // data has loaded
    await expect(link).toHaveAccessibleName("Data Health");
    await expect(link.getByTestId("data-health-badge")).toHaveCount(0);
  });
});

test.describe("states", () => {
  test("loading shows skeletons, then content", async ({ page }) => {
    await mockAdminApi(page, { delayMs: 1500 });
    await open(page);
    await expect(page.getByRole("region", { name: "Sources", exact: true }).locator('[aria-hidden="true"].bg-skeleton').first()).toBeVisible();
    await expect(page.getByRole("button", { name: "CJ Dropshipping: open runs" }).first()).toBeVisible({ timeout: 10_000 });
  });

  test("API down replaces the page with one error", async ({ page }) => {
    await mockAdminApi(page, { down: true });
    await open(page);
    await expect(page.getByRole("heading", { name: "Can't reach the API" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("When it runs on your PC, this also means the PC is off.")).toBeVisible();
  });

  test("no sources configured", async ({ page }) => {
    await mockAdminApi(page, { sources: [], coverage: [] });
    await open(page);
    await expect(page.getByRole("heading", { name: "No sources configured" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "No coverage yet" })).toBeVisible();
  });

  test("an offline host is flagged at the top", async ({ page }) => {
    await mockAdminApi(page, { host: { latest_heartbeat: { host: "pulso-pc", at: "2026-10-22T11:00:00Z" } } });
    await open(page);
    await expect(page.getByText("Collector host offline")).toBeVisible();
    await expect(page.getByRole("region", { name: "Collector host" })).toContainText("Offline");
  });
});

test("keyboard: open a source's runs and close them again", async ({ page }) => {
  await mockAdminApi(page);
  await open(page);
  const name = page.getByRole("region", { name: "Sources table" }).getByRole("button", { name: "CJ Dropshipping: open runs" });
  for (let i = 0; i < 40 && !(await name.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
  await expect(name).toBeFocused();
  expect(await name.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: "CJ Dropshipping" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(name).toBeFocused();
});

test.describe("phone width", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("cards replace the table with no horizontal page scroll", async ({ page }) => {
    await mockAdminApi(page);
    await open(page);
    await expect(page.getByRole("switch", { name: "CJ Dropshipping enabled" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Sources table" })).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  });
});

// Keeps the fixture honest: the overdue source comes from an open gap, not from a status field.
test("fixture sanity", () => {
  expect(sources.find((s) => s.key === "google_trends")?.status).toBe("active");
  expect(host.open_gaps.some((g) => g.source_key === "google_trends")).toBe(true);
});
