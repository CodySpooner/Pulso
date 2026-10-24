import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockAdminApi } from "./data-health/fixtures";

// imp-177 + imp-141 (DEC-229), vault Design/Motion System: a dialog enters at `base` and exits at `fast` with
// `ease.in` (row 9), and a locked Button never depresses under a pointer press while an enabled one still does.
const PAGE = "/admin/data-health";
test.use({ reducedMotion: "no-preference" }); // the durations and the press scale are what this measures

test("a dialog enters at base and exits at fast with ease-in", async ({ page }) => {
  await mockAdminApi(page);
  await page.goto(PAGE);
  await page.getByRole("region", { name: "Sources table" }).getByRole("switch", { name: "CJ Dropshipping enabled" }).click();
  const dialog = page.getByRole("dialog", { name: "Disable CJ Dropshipping?" });
  await expect(dialog).toHaveCSS("animation-duration", "0.2s");
  await expect(dialog).toHaveCSS("animation-timing-function", "ease");

  // The closing content's exit animation timing, read with the exit held at its first frame. Polling frames for the
  // closed state raced the unmount: a frame stall past the 120 ms exit left nothing to find, and it hung (imp-183).
  const hold = await page.addStyleTag({ content: "[data-state=closed] { animation-play-state: paused !important; }" });
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog, "the dialog reports closed after Cancel").toHaveAttribute("data-state", "closed", { timeout: 2_000 });
  const exit = await dialog.evaluate((el) => {
    const { animationName, animationDuration, animationTimingFunction } = getComputedStyle(el);
    return { animationName, animationDuration, animationTimingFunction };
  });
  expect(exit).toEqual({ animationName: "exit", animationDuration: "0.12s", animationTimingFunction: "cubic-bezier(0.7, 0, 0.84, 0)" });
  await hold.evaluate((style) => (style as Element).remove());
  await expect(dialog).toBeHidden();
});

/** The button's width while a pointer holds it down, as a share of its width at rest. */
async function pressScale(page: Page, button: Locator) {
  const rest = (await button.boundingBox())!;
  await page.mouse.move(rest.x + rest.width / 2, rest.y + rest.height / 2);
  await page.mouse.down();
  await page.waitForTimeout(200); // the 120 ms press transition has finished
  const pressed = await button.evaluate((el) => el.getBoundingClientRect().width);
  await page.mouse.move(0, 0); // release off the button, so the press never clicks
  await page.mouse.up();
  await page.waitForTimeout(200); // and has settled back
  return pressed / rest.width;
}

test("a locked Button keeps scale 1 under a pointer press; an enabled one still depresses", async ({ page }) => {
  await mockAdminApi(page); // off the collector host, so Run now is locked
  await page.goto(PAGE);
  const refresh = page.getByRole("button", { name: "Refresh", exact: true });
  const run = page.getByRole("region", { name: "Sources table" }).getByRole("button", { name: "Run CJ Dropshipping now" });
  await expect(refresh).toHaveAttribute("aria-disabled", "false");
  await expect(run).toHaveAttribute("aria-disabled", "true");
  await expect(run).toHaveCSS("pointer-events", "auto"); // a press reaches it, so its reason shows

  expect(await pressScale(page, refresh)).toBeCloseTo(0.98, 3);
  expect(await pressScale(page, run)).toBe(1);

  // Icon sizes press to 0.94. No icon Button is locked in the app yet, so lock the theme toggle as callers do.
  const toggle = page.getByRole("button", { name: "Toggle theme" });
  expect(await pressScale(page, toggle)).toBeCloseTo(0.94, 3);
  await toggle.evaluate((el) => {
    el.setAttribute("aria-disabled", "true");
    el.style.pointerEvents = "auto";
  });
  expect(await pressScale(page, toggle)).toBe(1);
});
