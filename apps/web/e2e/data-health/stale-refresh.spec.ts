import { expect, test, type Page, type Route } from "@playwright/test";

import { mockAdminApi, problem, sources } from "./fixtures";

// imp-132 (aud-014 A14-01): a refetch that fails while data is on screen keeps every panel's rows and cards, and
// one line says what failed, why, "Showing data as of <time>", Retry and Copy error ID: page level when both core
// calls fail, in the panel otherwise. The first-load API-down page is unchanged.

const PAGE = "/admin/data-health";
const ADMIN = "**/api/v1/admin/**";
const apiDown = (route: Route) => route.abort("connectionrefused");
const isCoverage = (url: URL) => url.pathname === "/api/v1/admin/coverage";
const coverage503 = (route: Route) => route.fulfill({ status: 503, json: problem(503, "req-cov-1") });

const sourceRows = (page: Page) =>
  page.getByRole("region", { name: "Sources", exact: true }).getByRole("button", { name: /: open runs$/ }).locator("visible=true");
const coverageRows = (page: Page) => page.getByRole("region", { name: "Coverage" }).getByRole("img", { name: /last 90 days/ });
const staleLines = (page: Page) => page.getByText("Showing data as of");
const noHScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function load(page: Page) {
  await mockAdminApi(page);
  await page.goto(PAGE);
  await expect(sourceRows(page)).toHaveCount(4, { timeout: 15_000 });
  await expect(coverageRows(page)).toHaveCount(4);
}

for (const [width, height] of [
  [1440, 900],
  [375, 812],
]) {
  test.describe(`${width}px`, () => {
    test.use({ viewport: { width, height } });

    test("a failed Refresh keeps every panel, and one page line says so until Retry", async ({ page }) => {
      await load(page);
      await page.route(ADMIN, apiDown); // newer routes win: the API stops while the page is open
      await page.getByRole("button", { name: "Refresh" }).click();

      const line = page.getByRole("group", { name: "Couldn't refresh Data Health" });
      await expect(line).toContainText("Showing data as of Oct 22, 14:00 UTC", { timeout: 15_000 });
      await expect(line).toContainText("The Pulso API didn't answer.");
      await expect(sourceRows(page)).toHaveCount(4);
      await expect(coverageRows(page)).toHaveCount(4);
      await expect(page.getByRole("region", { name: "Collector host" })).toContainText("pulso-pc");
      await expect(page.getByRole("region", { name: "Backups" })).toContainText("1 of 14 failed");
      await expect(staleLines(page)).toHaveCount(1); // one line for the page, none per panel
      await expect(page.getByRole("heading", { name: "Can't reach the API" })).toHaveCount(0);
      expect(await noHScroll(page)).toBe(true);

      await page.unroute(ADMIN, apiDown);
      await line.getByRole("button", { name: "Retry" }).click();
      await expect(staleLines(page)).toHaveCount(0);
      await expect(sourceRows(page)).toHaveCount(4);
      await expect(coverageRows(page)).toHaveCount(4);
    });

    test("one failed call keeps its panel's data and says so in that panel only", async ({ page }) => {
      await load(page);
      await page.route(isCoverage, coverage503);
      await page.getByRole("button", { name: "Refresh" }).click();

      const line = page.getByRole("region", { name: "Coverage" }).getByRole("group", { name: "Couldn't refresh coverage" });
      await expect(line).toContainText("The API is restarting. Try again.", { timeout: 15_000 });
      await expect(line).toContainText("Showing data as of Oct 22, 14:00 UTC");
      await expect(line.getByRole("textbox", { name: "Error ID" })).toHaveText("req-cov-1");
      await expect(line.getByRole("button", { name: "Copy error ID" })).toBeVisible();
      await expect(coverageRows(page)).toHaveCount(4);
      await expect(sourceRows(page)).toHaveCount(4);
      await expect(staleLines(page)).toHaveCount(1);
      expect(await noHScroll(page)).toBe(true);

      await page.unroute(isCoverage, coverage503);
      await line.getByRole("button", { name: "Retry" }).click();
      await expect(staleLines(page)).toHaveCount(0);
      await expect(coverageRows(page)).toHaveCount(4);
    });

    test("the first-load API-down page is unchanged", async ({ page }) => {
      await mockAdminApi(page, { down: true });
      await page.goto(PAGE);
      await expect(page.getByRole("heading", { level: 2, name: "Can't reach the API" })).toBeVisible({ timeout: 15_000 });
      await expect(page.getByRole("region", { name: "Sources", exact: true })).toHaveCount(0);
      await expect(staleLines(page)).toHaveCount(0);
    });
  });
}

test("a failed older-runs page keeps the runs already loaded in the drawer", async ({ page }) => {
  const cjRun = sources.find((s) => s.key === "cj")!.last_run!;
  const isCjRuns = (url: URL) => url.pathname === "/api/v1/admin/runs" && url.searchParams.get("source") === "cj";
  await mockAdminApi(page);
  await page.route(isCjRuns, (route) =>
    new URL(route.request().url()).searchParams.get("cursor")
      ? route.fulfill({ status: 503, json: problem(503, "req-runs-2") })
      : route.fulfill({ json: { items: [cjRun], next_cursor: String(cjRun.id) } }),
  );
  await page.goto(PAGE);
  await page.getByRole("button", { name: "CJ Dropshipping: open runs" }).locator("visible=true").click();
  const drawer = page.getByRole("dialog", { name: "CJ Dropshipping" });
  await expect(drawer.getByRole("list", { name: "CJ Dropshipping runs" }).getByRole("listitem")).toHaveCount(1);

  await drawer.getByRole("button", { name: "Load older runs" }).click();
  const line = drawer.getByRole("group", { name: "Couldn't load older runs" });
  await expect(line).toContainText("Showing data as of Oct 22, 14:00 UTC", { timeout: 15_000 });
  await expect(line.getByRole("textbox", { name: "Error ID" })).toHaveText("req-runs-2");
  await expect(drawer.getByRole("list", { name: "CJ Dropshipping runs" }).getByRole("listitem")).toHaveCount(1);
});
