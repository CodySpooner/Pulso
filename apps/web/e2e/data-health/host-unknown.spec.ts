import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi, problem } from "./fixtures";

// imp-133 (aud-014 A14-02): Overdue comes from the host's gap summary. Fixtures: Shopify is blocked and Google
// Trends has an open gap that ended 2 h ago, so 2 sources need attention once the host loads. When only
// GET /host fails, no source may read Healthy, the gap check says why, and the counts read as floors.

const PAGE = "/admin/data-health";
const REASON = "Gap check didn't load";
const isHost = (url: URL) => url.pathname === "/api/v1/admin/host";

/** Sources answer 200, the host 503 (a later route wins over mockAdminApi's). */
async function hostDown(page: Page) {
  await mockAdminApi(page);
  await page.route(isHost, (route) => route.fulfill({ status: 503, json: problem(503, "req_host_503") }));
}

// The Unknown note is a link to the host card's Retry; the pill's hint stays plain text (imp-159).
const NOTE_LINK = "Gap check didn't load (retry on the Collector host card)";

const sourcesPanel = (page: Page) => page.getByRole("region", { name: "Sources", exact: true });
const hostRetry = (page: Page) => page.getByRole("region", { name: "Collector host" }).getByRole("button", { name: "Retry" });

test("1440: with the host 503, no source reads Healthy, Trends says why, the counts are floors; 1 Retry restores Overdue", async ({ page }) => {
  await hostDown(page);
  await page.goto(PAGE);
  await expect(hostRetry(page)).toBeVisible();

  const table = page.getByRole("region", { name: "Sources table" });
  const trends = table.getByRole("row", { name: /Google Trends/ });
  await expect(trends).toContainText(`Unknown${REASON}`);
  expect(await trends.getByText(REASON).evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true); // not cut by the ellipsis
  await expect(table.getByRole("row", { name: /CJ Dropshipping/ })).toContainText("Unknown");
  await expect(table.getByText("Healthy", { exact: true })).toHaveCount(0);
  await expect(table.getByRole("row", { name: /Shopify stores/ })).toContainText("Blocked"); // host-independent states stay

  const unknown = trends.getByRole("button", { name: "Unknown" });
  await unknown.focus();
  await expect(page.getByRole("tooltip")).toContainText("may be overdue. Retry on the Collector host card.");
  await page.keyboard.press("Tab"); // the hint never holds focus
  await expect(unknown).not.toBeFocused();
  await expect(page.getByRole("tooltip")).toHaveCount(0);

  await expect(sourcesPanel(page).getByText(/attention/)).toHaveText("· at least 1 needs attention");
  const link = page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: /Data Health/ });
  await expect(link).toHaveAccessibleName(/^Data Health\W+at least 1 source needs attention$/);
  await expect(link.getByTestId("data-health-badge")).toHaveText("1+");

  // Recovery: the host answers again. Trends' "Gap check didn't load" note links to the host card's Retry
  // (imp-159), and 1 Enter on it brings back the full picture.
  await page.unroute(isHost);
  await trends.getByRole("link", { name: NOTE_LINK }).click();
  await expect(hostRetry(page)).toBeFocused();
  await page.keyboard.press("Enter");
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

for (const width of [1440, 375]) {
  for (const how of ["pointer", "keyboard"] as const) {
    test(`${width}: Trends' Unknown note focuses the host card's Retry in one ${how === "pointer" ? "click" : "Enter"}`, async ({ page }) => {
      await hostDown(page);
      await page.setViewportSize({ width, height: width < 1024 ? 812 : 900 });
      await page.goto(PAGE);
      const trigger = page.getByRole("button", { name: "Google Trends: open runs" });
      const trends =
        width < 768 ? page.getByRole("listitem").filter({ has: trigger }) : page.getByRole("region", { name: "Sources table" }).getByRole("row").filter({ has: trigger });
      const link = trends.getByRole("link", { name: NOTE_LINK });
      await link.scrollIntoViewIfNeeded();
      if (width < 1024) await expect(hostRetry(page)).not.toBeInViewport(); // above the cards on a phone
      if (how === "pointer") await link.click();
      else {
        await link.focus();
        await page.keyboard.press("Enter");
      }
      await expect(hostRetry(page)).toBeFocused();
      await expect(hostRetry(page)).toBeInViewport({ ratio: 1 });
      if (width < 1024) {
        const bar = (await page.getByRole("banner").boundingBox())!;
        expect((await hostRetry(page).boundingBox())!.y).toBeGreaterThanOrEqual(bar.y + bar.height); // clear of the top bar
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });
  }
}

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
