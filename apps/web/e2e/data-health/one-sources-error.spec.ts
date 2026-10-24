import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi, problem } from "./fixtures";

// imp-139 (aud-014 A14-08): one failed GET /sources is one error on the page, not three. The Sources panel keeps
// its error, Retry and Copy error ID. Coverage keeps the rows its own call loaded, by source key, with one line
// saying what they lack; CSV import shows one line. Neither has a Retry or error ID of its own, and the Sources
// Retry brings all three back (DEC-227).

const ID = "req_sources_503";
const COVERAGE_LINE = "Names wait for the source list above. Rows show source keys, and sources with no runs yet aren't listed.";
const IMPORT_LINE = "Waits for the source list above. Retry there to choose a source and import.";

/** Every admin call answers from the fixtures except GET /sources, which answers 503 while `sources.down` holds. */
async function load(page: Page, width: number, theme: "dark" | "light") {
  await mockAdminApi(page);
  const sources = { down: true };
  await page.route(
    (url) => url.pathname === "/api/v1/admin/sources",
    (route) => (sources.down ? route.fulfill({ status: 503, json: problem(503, ID) }) : route.fallback()),
  );
  await page.setViewportSize({ width, height: width < 1024 ? 812 : 900 });
  await page.emulateMedia({ colorScheme: theme });
  await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
  await page.goto("/admin/data-health");
  await expect(panel(page, "Sources").getByRole("heading", { level: 3, name: "Couldn't load sources" })).toBeVisible({ timeout: 15_000 });
  return sources;
}

function panel(page: Page, name: string) {
  return page.getByRole("region", { name, exact: true });
}
const pageScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

/** Tab presses from load until focus leaves the document, and how many of those stops sit in the page's <main>. */
async function tabStops(page: Page): Promise<{ page: number; main: number }> {
  const stops = { page: 0, main: 0 };
  for (let i = 0; i < 300; i++) {
    await page.keyboard.press("Tab");
    const at = await page.evaluate(() => {
      let el = document.activeElement;
      while (el?.shadowRoot?.activeElement) el = el.shadowRoot.activeElement; // the dev overlay's own controls
      if (!el || el === document.body || el.hasAttribute("data-tab-seen")) return null;
      el.setAttribute("data-tab-seen", "");
      return el.closest("main") ? "main" : "page";
    });
    if (!at) break;
    stops.page++;
    if (at === "main") stops.main++;
  }
  return stops;
}

for (const theme of ["dark", "light"] as const) {
  for (const width of [1440, 375]) {
    test(`sources 503 at ${width}px ${theme}: one error, two waiting lines, and one Retry restores all three`, async ({ page }) => {
      const sources = await load(page, width, theme);

      // One error: its title, Retry, Copy error ID and the ID itself, once each, all in the Sources panel.
      await expect(page.getByRole("heading", { name: /^Couldn't load/ })).toHaveCount(1);
      await expect(page.getByRole("button", { name: "Retry" })).toHaveCount(1);
      await expect(page.getByRole("button", { name: "Copy error ID" })).toHaveCount(1);
      await expect(page.getByText(ID)).toHaveCount(1);
      await expect(panel(page, "Sources").getByRole("button", { name: "Retry" })).toBeVisible();

      // Coverage keeps the rows its own call loaded, by key, under one line that names what they lack.
      const coverage = panel(page, "Coverage");
      await expect(coverage.getByRole("img", { name: /^google_trends, last 90 days: / })).toBeVisible();
      await expect(coverage.getByRole("img", { name: /, last 90 days: / })).toHaveCount(3); // Frankfurter FX has no runs
      await expect(coverage.getByText(COVERAGE_LINE)).toBeVisible();
      // CSV import: one line and nothing to press.
      const csv = panel(page, "CSV import");
      await expect(csv.getByText(IMPORT_LINE)).toBeVisible();
      await expect(csv.locator("a[href], button, select, input, [tabindex='0']")).toHaveCount(0);
      for (const [dependent, line] of [[coverage, COVERAGE_LINE], [csv, IMPORT_LINE]] as const) {
        await expect(dependent.getByRole("button", { name: /^(Retry|Copy error ID)$/ })).toHaveCount(0);
        await expect(dependent.getByText(ID)).toHaveCount(0);
        // Not a live region: a background refetch that fails again says nothing.
        await expect(dependent.getByText(line).locator("xpath=ancestor-or-self::*[@aria-live or @role='alert' or @role='status']")).toHaveCount(0);
      }
      expect(await pageScroll(page)).toBe(0);

      // Recovery: 1 click on the Sources Retry brings back Sources, Coverage's names and the import panel.
      sources.down = false;
      await panel(page, "Sources").getByRole("button", { name: "Retry" }).click();
      await expect(panel(page, "Sources").getByRole("button", { name: "CJ Dropshipping: open runs" })).toBeVisible();
      await expect(panel(page, "Sources").getByRole("heading", { level: 2, name: "Sources" })).toBeFocused(); // imp-135
      await expect(coverage.getByRole("img", { name: /^Google Trends, last 90 days: / })).toBeVisible();
      await expect(coverage.getByRole("img", { name: /, last 90 days: / })).toHaveCount(4); // Frankfurter FX's row is back
      await expect(coverage.getByText(COVERAGE_LINE)).toHaveCount(0);
      await expect(csv.getByRole("combobox", { name: "Source" })).toBeVisible();
      await expect(csv.getByText(IMPORT_LINE)).toHaveCount(0);
      await expect(page.getByRole("heading", { name: /^Couldn't load/ })).toHaveCount(0);
    });
  }
}

for (const width of [1440, 375]) {
  test(`sources 503 at ${width}px: Tab stops on the page`, async ({ page }) => {
    await load(page, width, "dark");
    const stops = await tabStops(page);
    test.info().annotations.push({ type: "tab-stops", description: `${width}px: ${stops.page} on the page, ${stops.main} in main` });
    console.log(`imp-139 tab stops ${width}px: page ${stops.page}, main ${stops.main}`);
    expect(stops.main).toBeGreaterThan(0);
  });
}
