import { expect, test, type Page } from "@playwright/test";

// imp-047: below 768px the palette is a full-screen sheet, so its input bar must clear the notch and its list
// the home indicator; the centred desktop dialog ignores the insets. Chromium emulates a notched phone over CDP.
const insets = { top: 47, bottom: 34 }; // iPhone 14 portrait

async function openPalette(page: Page, width: number) {
  await page.setViewportSize({ width, height: 812 });
  await page.emulateMedia({ reducedMotion: "reduce" }); // measure the settled sheet, not its open animation
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setSafeAreaInsetsOverride", { insets });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Daily Pulse" })).toBeVisible();
  await page.keyboard.press("Control+K");
  await expect(page.getByRole("combobox")).toBeFocused();
}

const geometry = (page: Page) => () =>
  page.getByRole("dialog", { name: "Command palette" }).evaluate((dialog) => {
    const box = dialog.getBoundingClientRect();
    const bar = dialog.querySelector('[role="combobox"]')!.parentElement!.getBoundingClientRect();
    const list = dialog.querySelector('[role="listbox"]')!.getBoundingClientRect();
    return {
      top: box.top,
      barTop: bar.top - box.top,
      listGap: box.bottom - list.bottom,
      pageScroll: document.documentElement.scrollWidth - innerWidth,
    };
  });

test("the phone palette clears the notch and the home indicator, with no sideways scroll", async ({ page }) => {
  await openPalette(page, 375);
  // 1px border plus the inset at both ends; the phone sheet has no footer, so the list is its last child.
  await expect.poll(geometry(page)).toEqual({ top: 0, barTop: 1 + insets.top, listGap: 1 + insets.bottom, pageScroll: 0 });
});

test("the desktop palette ignores the safe-area insets", async ({ page }) => {
  await openPalette(page, 1440);
  await expect.poll(async () => (await geometry(page)()).barTop).toBe(1);
});
