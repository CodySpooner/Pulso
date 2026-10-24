import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockAdminApi, problem } from "./fixtures";

// imp-145 + imp-146: Open gaps come from GET /host alone. With the coverage call failed they still render, so the
// Overdue links (imp-124) land on their heading; with the host call failed one line says the gap check didn't
// load and names the next step (DEC-196), never an empty list or "no gaps".

const LINK = "Missed Oct 22, 10:00–12:00 UTC Host offline (in Open gaps)";
const UNAVAILABLE = "Gap check didn't load, so open gaps can't be listed. Retry on the Collector host card.";

/** Every admin call answers from the fixtures except `failing`, which answers 503. */
async function load(page: Page, width: number, failing: "host" | "coverage") {
  await mockAdminApi(page);
  await page.route(
    (url) => url.pathname === `/api/v1/admin/${failing}`,
    (route) => route.fulfill({ status: 503, json: problem(503, `req_${failing}_503`) }),
  );
  await page.setViewportSize({ width, height: width < 1024 ? 812 : 900 });
  await page.goto("/admin/data-health");
}

const coverage = (page: Page) => page.getByRole("region", { name: "Coverage", exact: true });
const pageScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

/** The source's table row from md up, its phone card below. */
function row(page: Page, width: number, name: string): Locator {
  const trigger = page.getByRole("button", { name: `${name}: open runs` });
  return width < 768 ? page.getByRole("listitem").filter({ has: trigger }) : page.getByRole("region", { name: "Sources table" }).getByRole("row").filter({ has: trigger });
}

for (const width of [1440, 375]) {
  test(`host 503 at ${width}px: one line says the gap check didn't load, and no list`, async ({ page }) => {
    await load(page, width, "host");
    const panel = coverage(page);
    await expect(panel.getByRole("img", { name: /^Google Trends, last 90 days/ })).toBeVisible(); // coverage loaded
    const line = panel.locator("p", { hasText: "Gap check didn't load" });
    await expect(line).toHaveCount(1);
    await expect(line).toHaveText(UNAVAILABLE);
    await expect(line).toBeVisible();
    await expect(panel.getByRole("region", { name: "Open gaps" })).toHaveCount(0);
    await expect(page.locator("#open-gaps")).toHaveCount(0);
    await expect(panel).not.toContainText("No open gaps");
    expect(await pageScroll(page)).toBe(0);
  });

  test(`coverage 503 at ${width}px: Open gaps stay, and the row and drawer links land on their heading`, async ({ page }) => {
    await load(page, width, "coverage");
    const panel = coverage(page);
    await expect(panel.getByRole("heading", { name: "Couldn't load coverage" })).toBeVisible();
    await expect(panel.getByRole("region", { name: "Open gaps" })).toContainText("Google Trends");
    const heading = page.locator("#open-gaps");

    await row(page, width, "Google Trends").getByRole("link", { name: LINK }).click();
    await expect(heading).toBeFocused();
    await expect(heading).toBeInViewport();

    await page.getByRole("button", { name: "Google Trends: open runs" }).locator("visible=true").click();
    const drawer = page.getByRole("dialog", { name: "Google Trends" });
    await drawer.getByRole("link", { name: LINK }).click();
    await expect(drawer).toBeHidden();
    await expect(heading).toBeFocused(); // not the opener
    await expect(heading).toBeInViewport();
    expect(await pageScroll(page)).toBe(0);
  });
}
