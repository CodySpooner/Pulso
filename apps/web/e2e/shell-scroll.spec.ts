import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi } from "./data-health/fixtures";

// imp-147: at lg the shell is one viewport tall and only <main> scrolls. Absolutely positioned boxes with no
// positioned ancestor (the import panel's sr-only live regions) used to escape main's overflow and make the
// document 1,309 px tall at 1440×900, so a fragment jump near the page end scrolled the document too and pushed
// the whole shell up. The document must stay one viewport tall, and a jump must scroll main only.

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

for (const [width, height] of [
  [1440, 900],
  [375, 812],
] as const) {
  test(`a fragment jump to Open gaps scrolls main, not the shell, at ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await openDataHealth(page);
    const topbar = page.getByRole("banner");
    const before = (await topbar.boundingBox())!.y;
    const heading = page.getByRole("heading", { name: /^Open gaps/ });
    // What a native #fragment jump does: scroll every scrollable ancestor, the document included, to the target.
    await heading.evaluate((el) => el.scrollIntoView({ block: "start" }));

    await expect(heading).toBeInViewport();
    expect((await topbar.boundingBox())!.y).toBe(before);
    const size = await docSize(page);
    expect(size.scrollWidth).toBe(width);
    if (width === 1440) {
      expect(size).toMatchObject({ scrollHeight: height, scrollY: 0 });
      expect(await page.locator("main").evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
    }
  });
}
