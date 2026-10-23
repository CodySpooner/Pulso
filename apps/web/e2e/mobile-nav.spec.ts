import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi } from "./data-health/fixtures";

// Review P0-08b #1: dismissing the navigation sheet returns focus to the button that opened it; following a
// link to another page focuses that page's h1 instead.
async function openSheet(page: Page, opener: string) {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-app-ready", "true");
  await expect(page.getByRole("heading", { level: 1, name: "Daily Pulse" })).toBeVisible();
  const button = page.getByRole("button", { name: opener, exact: true });
  await button.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  return button;
}

test.describe("phone", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("Esc closes the sheet and focus returns to More", async ({ page }) => {
    const more = await openSheet(page, "More");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(more).toBeFocused();
  });
});

test.describe("tablet", () => {
  test.use({ viewport: { width: 768, height: 1024 } });

  test("Close menu returns focus to the menu button", async ({ page }) => {
    const menu = await openSheet(page, "Open menu");
    await page.getByRole("button", { name: "Close menu" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(menu).toBeFocused();
  });

  test("a link to another page focuses its heading", async ({ page }) => {
    await openSheet(page, "Open menu");
    await page.getByRole("dialog").getByRole("link", { name: /^Discover/ }).click();
    await expect(page).toHaveURL(/\/discover$/);
    await expect(page.getByRole("heading", { level: 1, name: "Discover" })).toBeFocused();
  });
});

// imp-097 (vault Design/Accessibility, "Icon-only buttons: aria-label always, plus a tooltip"): at 768–1023px
// the top bar's two icon-only buttons name themselves on hover and keyboard focus. A tap never shows the tooltip,
// and focus handed back by a sheet or palette closed with a tap or click doesn't open it either.
const tabletIconButtons = [
  { name: "Open menu", tooltip: "Open menu", via: "Shift+Tab" },
  { name: "Open command palette", tooltip: "Open command palette Ctrl K", via: "Tab" },
];

async function gotoPulse(page: Page) {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-app-ready", "true");
  await expect(page.getByRole("heading", { level: 1, name: "Daily Pulse" })).toBeVisible();
}

/** No tooltip shows, checked after the 400ms open delay has passed. */
async function expectNoTooltip(page: Page) {
  await page.waitForTimeout(500);
  await expect(page.getByRole("tooltip")).toHaveCount(0);
}

for (const width of [768, 1023]) {
  test.describe(`tablet ${width}px tooltips`, () => {
    test.use({ viewport: { width, height: 1024 } });

    for (const { name, tooltip, via } of tabletIconButtons) {
      test(`hovering ${name} shows its tooltip below the bar`, async ({ page }) => {
        await gotoPulse(page);
        const button = page.getByRole("button", { name, exact: true });
        await button.hover();
        await expect(page.getByRole("tooltip")).toHaveText(tooltip);
        const box = (await button.boundingBox())!;
        const bubble = (await page.locator("[data-radix-popper-content-wrapper]").boundingBox())!;
        expect(bubble.y).toBeGreaterThanOrEqual(box.y + box.height + 4); // below the button, clear of its 4px focus ring
        expect(bubble.x).toBeGreaterThanOrEqual(8); // never flush with the screen edge
        expect(bubble.x + bubble.width).toBeLessThanOrEqual(width - 8);
        await page.mouse.move(width / 2, 600, { steps: 4 }); // Radix closes on the first move outside its grace area
        await expect(page.getByRole("tooltip")).toHaveCount(0);
      });

      test(`keyboard focus on ${name} shows its tooltip`, async ({ page }) => {
        await gotoPulse(page);
        // The logo link sits between the two buttons, so one key press lands on each with keyboard modality.
        await page.getByRole("link", { name: "Pulso, go to Daily Pulse" }).focus();
        await page.keyboard.press(via);
        await expect(page.getByRole("button", { name, exact: true })).toBeFocused();
        await expect(page.getByRole("tooltip")).toHaveText(tooltip);
        await page.keyboard.press("Escape");
        await expect(page.getByRole("tooltip")).toHaveCount(0);
      });
    }

    test("Esc closes the sheet, focus returns to Open menu and names it", async ({ page }) => {
      const menu = await openSheet(page, "Open menu");
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).toBeHidden();
      await expect(menu).toBeFocused();
      await expect(page.getByRole("tooltip")).toHaveText("Open menu");
    });

    // The tooltip follows :focus-visible, like the focus ring: after a key press Chromium shows both on returned focus.
    test("mouse clicks on Open menu and Close menu return focus with no ring and no tooltip", async ({ page }) => {
      await gotoPulse(page);
      const menu = page.getByRole("button", { name: "Open menu", exact: true });
      await menu.click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.getByRole("button", { name: "Close menu" }).click();
      await expect(page.getByRole("dialog")).toBeHidden();
      await expect(menu).toBeFocused();
      expect(await menu.evaluate((el) => el.matches(":focus-visible"))).toBe(false);
      await expectNoTooltip(page);
    });

    test("Ctrl+K still opens the palette and Esc returns focus to Open command palette", async ({ page }) => {
      await gotoPulse(page);
      const button = page.getByRole("button", { name: "Open command palette", exact: true });
      await button.focus();
      await page.keyboard.press("Control+k");
      await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).toBeHidden();
      await expect(button).toBeFocused();
    });
  });
}

test.describe("tablet touch tooltips", () => {
  test.use({ viewport: { width: 768, height: 1024 }, hasTouch: true });

  test("tapping Open menu opens the sheet with no tooltip, and Close menu hands focus back without one", async ({ page }) => {
    await gotoPulse(page);
    const menu = page.getByRole("button", { name: "Open menu", exact: true });
    await menu.tap();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByRole("tooltip")).toHaveCount(0);
    await page.getByRole("button", { name: "Close menu" }).tap();
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(menu).toBeFocused();
    await expectNoTooltip(page);
  });

  test("tapping Open command palette opens it with no tooltip, and a tap outside hands focus back without one", async ({ page }) => {
    await gotoPulse(page);
    const button = page.getByRole("button", { name: "Open command palette", exact: true });
    await button.tap();
    await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
    await expect(page.getByRole("tooltip")).toHaveCount(0);
    await page.touchscreen.tap(384, 1000); // the overlay below the palette
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(button).toBeFocused();
    await expectNoTooltip(page);
  });
});

// imp-099: imp-093's DH-3 count and imp-097's tooltip share the tablet Open menu (fixture DH-1: 2 sources need
// attention). The count stays in the accessible name, the tooltip still reads "Open menu" below the badge, and focus
// handed back after a click or tap still opens no tooltip.
const menuWithCount = /^Open menu\W+2 sources need attention$/;

async function gotoPulseWithCount(page: Page) {
  await mockAdminApi(page);
  await gotoPulse(page);
  const menu = page.getByRole("banner").getByRole("button", { name: /^Open menu/ });
  await expect(menu).toHaveAccessibleName(menuWithCount);
  await expect(menu.getByTestId("data-health-badge")).toHaveText("2");
  return menu;
}

for (const width of [768, 1023]) {
  test.describe(`tablet ${width}px Open menu with the DH-3 count`, () => {
    test.use({ viewport: { width, height: 1024 } });

    test("hover and Esc-returned focus show the tooltip, a click-close shows none, and the count stays named", async ({ page }) => {
      const menu = await gotoPulseWithCount(page);
      await menu.hover();
      await expect(page.getByRole("tooltip")).toHaveText("Open menu");
      const badge = (await menu.getByTestId("data-health-badge").boundingBox())!;
      const bubble = (await page.locator("[data-radix-popper-content-wrapper]").boundingBox())!;
      expect(bubble.y).toBeGreaterThanOrEqual(badge.y + badge.height); // the bubble never covers the count
      await expect(menu).toHaveAccessibleName(menuWithCount);
      await expect(page.getByText(/need attention/).filter({ visible: true })).toHaveCount(1); // the count is announced once
      await page.mouse.move(width / 2, 600, { steps: 4 });
      await expect(page.getByRole("tooltip")).toHaveCount(0);

      await menu.click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.getByRole("button", { name: "Close menu" }).click();
      await expect(page.getByRole("dialog")).toBeHidden();
      await expect(menu).toBeFocused();
      await expectNoTooltip(page);

      await page.keyboard.press("Enter");
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(menu).toBeFocused();
      await expect(page.getByRole("tooltip")).toHaveText("Open menu");
      await expect(menu).toHaveAccessibleName(menuWithCount);
    });
  });
}

test.describe("tablet touch Open menu with the DH-3 count", () => {
  test.use({ viewport: { width: 768, height: 1024 }, hasTouch: true });

  test("tap open and tap Close menu leave no tooltip and keep the count", async ({ page }) => {
    const menu = await gotoPulseWithCount(page);
    await menu.tap();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByRole("tooltip")).toHaveCount(0);
    await page.getByRole("button", { name: "Close menu" }).tap();
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(menu).toBeFocused();
    await expectNoTooltip(page);
    await expect(menu).toHaveAccessibleName(menuWithCount);
    await expect(menu.getByTestId("data-health-badge")).toBeVisible();
  });
});
