import { expect, test, type Page } from "@playwright/test";

import { activity, healthySources, mockAdminApi, sources } from "./fixtures";

// imp-166 (DEC-223): an expired CJ activity countdown on an enabled CJ needs attention, so the Sources panel's
// count and the DH-3 nav badge include it; warn is a heads-up on the row only. The counted row names its reason:
// the red "Expired · −3 days" line under the pill, never a Healthy pill alone.
const PAGE = "/admin/data-health";
const quiet = { open_gaps: [], latest_gap_ends: {} }; // no gaps, so only the sources decide the count
type Source = (typeof sources)[number];
const withCj = (list: Source[], over: Partial<Source>) => list.map((s) => (s.key === "cj" ? { ...s, ...over } : s));

const sourcesPanel = (page: Page) => page.getByRole("region", { name: "Sources", exact: true });
const navLink = (page: Page) => page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: /Data Health/ });
const cjRow = (page: Page) => page.getByRole("region", { name: "Sources table" }).getByRole("row", { name: /CJ Dropshipping/ });

for (const [name, list, host, count] of [
  ["expired, every other source healthy", withCj(healthySources, { activity: activity("expired", -3) }), quiet, 1],
  ["expired beside a blocked and an overdue source", withCj(sources, { activity: activity("expired", -3) }), {}, 3],
  ["warn", withCj(healthySources, { activity: activity("warn", 5) }), quiet, 0],
  ["expired on a CJ the owner disabled", withCj(healthySources, { activity: activity("expired", -3), enabled: false, status: "disabled" }), quiet, 0],
] as const) {
  test(`${name}: the panel and the badge count ${count}`, async ({ page }) => {
    await mockAdminApi(page, { sources: [...list], host });
    await page.goto(PAGE);
    await expect(page.getByText("Online · 4m ago").first()).toBeVisible(); // both calls have landed
    const note = sourcesPanel(page).getByText(/attention/);
    if (count === 0) {
      await expect(note).toHaveCount(0);
      await expect(navLink(page)).toHaveAccessibleName("Data Health");
      await expect(navLink(page).getByTestId("data-health-badge")).toHaveCount(0);
    } else {
      await expect(note).toHaveText(`· ${count} ${count === 1 ? "needs" : "need"} attention`);
      await expect(navLink(page)).toHaveAccessibleName(new RegExp(`^Data Health\\W+${count} ${count === 1 ? "source needs" : "sources need"} attention$`));
      await expect(navLink(page).getByTestId("data-health-badge")).toHaveText(String(count));
    }
    // The countdown is on the row whether or not it counts.
    await expect(cjRow(page).getByRole("button", { name: /Expired · −3 days|5 days left/ })).toBeVisible();
  });
}

test("the counted CJ row shows why beside its Healthy pill, in the table and on the phone card", async ({ page }) => {
  await mockAdminApi(page, { sources: withCj(healthySources, { activity: activity("expired", -3) }), host: quiet });
  await page.goto(PAGE);
  const row = cjRow(page);
  await expect(row).toContainText("Healthy");
  const why = row.getByRole("button", { name: "Expired · −3 days" });
  await expect(why).toBeVisible();
  await why.focus();
  await expect(page.getByRole("tooltip")).toContainText("the API is likely off");

  await page.setViewportSize({ width: 375, height: 812 });
  const card = page.getByRole("listitem").filter({ has: page.getByRole("button", { name: "CJ Dropshipping: open runs" }) });
  await expect(card.getByRole("button", { name: "Expired · −3 days" })).toBeVisible();
  const more = page.getByRole("navigation", { name: "Tab bar" }).getByRole("button", { name: /^More/ });
  await expect(more).toHaveAccessibleName(/^More\W+1 source needs attention$/);
  await expect(more.getByTestId("data-health-badge")).toHaveText("1");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});
