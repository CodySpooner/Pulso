import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi, problem } from "./fixtures";

// imp-133 (aud-014 A14-02): Overdue comes from the host's gap summary. Fixtures: Shopify is blocked and Google
// Trends has an open gap that ended 2 h ago, so 2 sources need attention once the host loads. When only
// GET /host fails, no source may read Healthy, the gap check says why, and the counts read as floors.

const PAGE = "/admin/data-health";
const REASON = "Gap check unavailable: the collector host didn't load";
const isHost = (url: URL) => url.pathname === "/api/v1/admin/host";

/** Sources answer 200, the host 503 (a later route wins over mockAdminApi's). */
async function hostDown(page: Page) {
  await mockAdminApi(page);
  await page.route(isHost, (route) => route.fulfill({ status: 503, json: problem(503, "req_host_503") }));
}

const sourcesPanel = (page: Page) => page.getByRole("region", { name: "Sources", exact: true });
const hostRetry = (page: Page) => page.getByRole("region", { name: "Collector host" }).getByRole("button", { name: "Retry" });

test("1440: with the host 503, no source reads Healthy, Trends says why, the counts are floors; 1 Retry restores Overdue", async ({ page }) => {
  await hostDown(page);
  await page.goto(PAGE);
  await expect(hostRetry(page)).toBeVisible();

  const table = page.getByRole("region", { name: "Sources table" });
  const trends = table.getByRole("row", { name: /Google Trends/ });
  await expect(trends).toContainText(`Unknown${REASON}`);
  await expect(table.getByRole("row", { name: /CJ Dropshipping/ })).toContainText("Unknown");
  await expect(table.getByText("Healthy", { exact: true })).toHaveCount(0);
  await expect(table.getByRole("row", { name: /Shopify stores/ })).toContainText("Blocked"); // host-independent states stay

  await trends.getByRole("button", { name: "Unknown" }).focus();
  await expect(page.getByRole("tooltip")).toContainText("may be overdue. Retry on the Collector host card.");

  await expect(sourcesPanel(page).getByText(/attention/)).toHaveText("· at least 1 needs attention");
  const link = page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: /Data Health/ });
  await expect(link).toHaveAccessibleName(/^Data Health\W+at least 1 source needs attention$/);
  await expect(link.getByTestId("data-health-badge")).toHaveText("1+");

  // Recovery: the host answers again and 1 click on the host card's Retry brings back the full picture.
  await page.unroute(isHost);
  await hostRetry(page).click();
  await expect(trends).toContainText("Overdue");
  await expect(table.getByText("Unknown", { exact: true })).toHaveCount(0);
  await expect(table.getByText("Healthy", { exact: true })).toHaveCount(1); // CJ: its gap ended 79 h ago
  await expect(sourcesPanel(page).getByText(/attention/)).toHaveText("· 2 need attention");
  await expect(link).toHaveAccessibleName(/^Data Health\W+2 sources need attention$/);
  await expect(link.getByTestId("data-health-badge")).toHaveText("2");
});

test.describe("phone width", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("375: with the host 503, the Trends card reads Unknown with its reason and More's count is a floor", async ({ page }) => {
    await hostDown(page);
    await page.goto(PAGE);
    await expect(hostRetry(page)).toBeVisible();

    const card = (name: string) => page.getByRole("listitem").filter({ has: page.getByRole("button", { name: `${name}: open runs` }) });
    await expect(card("Google Trends")).toContainText("Unknown");
    await expect(card("Google Trends").getByText(REASON)).toBeVisible();
    await expect(card("CJ Dropshipping")).toContainText("Unknown");
    await expect(sourcesPanel(page).getByText("Healthy", { exact: true })).toHaveCount(0);

    await expect(sourcesPanel(page).getByText(/attention/)).toHaveText("· at least 1 needs attention");
    const more = page.getByRole("navigation", { name: "Tab bar" }).getByRole("button", { name: /^More/ });
    await expect(more).toHaveAccessibleName(/^More\W+at least 1 source needs attention$/);
    await expect(more.getByTestId("data-health-badge")).toHaveText("1+");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  });
});

test("while the host call loads, no source reads Healthy or Unknown and nothing is counted; then Overdue lands", async ({ page }) => {
  await mockAdminApi(page);
  let release!: () => void;
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route(isHost, async (route) => {
    await held;
    await route.fallback();
  });
  await page.goto(PAGE);

  const table = page.getByRole("region", { name: "Sources table" });
  await expect(table.getByRole("row", { name: /Shopify stores/ })).toContainText("Blocked"); // sources have loaded
  await expect(table.getByText(/^(Healthy|Unknown|Partial)$/)).toHaveCount(0);
  await expect(table).not.toContainText(REASON);
  await expect(sourcesPanel(page)).not.toContainText("attention");
  const link = page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: /Data Health/ });
  await expect(link).toHaveAccessibleName("Data Health");

  release();
  await expect(table.getByRole("row", { name: /Google Trends/ })).toContainText("Overdue");
  await expect(link).toHaveAccessibleName(/^Data Health\W+2 sources need attention$/);
});
