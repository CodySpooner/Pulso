import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi } from "./data-health/fixtures";

// imp-147: at lg the shell is one viewport tall and only <main> scrolls. Absolutely positioned boxes with no
// positioned ancestor (the CSV panel's sr-only live regions) used to escape main's overflow and make the document
// 1,319 px tall at 1440×900, so a fragment jump to #open-gaps scrolled the document too and pushed the whole shell
// up 419 px. The document must stay one viewport tall, and a jump must scroll main only.

const docSize = (page: Page) =>
  page.evaluate(() => ({ scrollHeight: document.documentElement.scrollHeight, scrollWidth: document.documentElement.scrollWidth, scrollY }));

async function openDataHealth(page: Page) {
  await mockAdminApi(page);
  await page.goto("/admin/data-health");
  // The live regions sit at the end of the page, after every panel has loaded.
  await expect(page.getByRole("heading", { name: /^Open gaps/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "CSV import" })).toBeVisible();
}

for (const path of ["/admin/data-health", "/"]) {
  test(`the document is one viewport tall at 1440 on ${path}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    if (path === "/") await page.goto(path);
    else await openDataHealth(page);
    expect(await docSize(page)).toMatchObject({ scrollHeight: 900, scrollWidth: 1440 });
  });
}

const jumps: [string, (page: Page) => Promise<unknown>][] = [
  ["a native #open-gaps fragment jump", (page) => page.evaluate(() => (location.hash = "open-gaps"))],
  ["the Overdue note's Open gaps link", (page) => page.getByRole("link", { name: /\(in Open gaps\)$/ }).locator("visible=true").click()],
];

for (const [width, height] of [
  [1440, 900],
  [375, 812],
] as const) {
  for (const [name, jump] of jumps) {
    test(`${name} scrolls main, not the shell, at ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await openDataHealth(page);
      const topbar = page.getByRole("banner");
      const before = (await topbar.boundingBox())!.y;
      await jump(page);

      await expect(page.locator("#open-gaps")).toBeInViewport();
      expect((await topbar.boundingBox())!.y).toBe(before);
      const size = await docSize(page);
      expect(size.scrollWidth).toBe(width);
      if (width === 1440) {
        expect(size).toMatchObject({ scrollHeight: height, scrollY: 0 });
        expect(await page.locator("main").evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
      }
    });
  }
}
