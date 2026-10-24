import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockAdminApi } from "./data-health/fixtures";

// imp-177 + imp-141 (DEC-229) and imp-182 (DEC-233), vault Design/Motion System: a dialog enters at `base` with
// `ease.out` from scale 0.97 and exits at `fast` with `ease.in` to 0.98 (row 9), and a locked Button never depresses
// under a pointer press while an enabled one still does, at `fast` (Micro-interactions).
const PAGE = "/admin/data-health";
test.use({ reducedMotion: "no-preference" }); // the durations and the press scale are what this measures

/** The dialog's held animation: its name and timing, and the transform its enter starts from or its exit ends at. */
const heldAnimation = (dialog: Locator) =>
  dialog.evaluate((el) => {
    const { animationName, animationDuration, animationTimingFunction } = getComputedStyle(el);
    const [from, to] = (el.getAnimations()[0].effect as KeyframeEffect).getKeyframes();
    return { animationName, animationDuration, animationTimingFunction, transform: (animationName === "exit" ? to : from).transform };
  });

test("a dialog enters at base with ease-out from 0.97 and exits at fast with ease-in to 0.98", async ({ page }) => {
  await mockAdminApi(page);
  await page.goto(PAGE);
  // The dialog's animations are held at their first frame while they are read. Polling frames for the closed state
  // raced the unmount: a frame stall past the 120 ms exit left nothing to find, and it hung (imp-183).
  const hold = await page.addStyleTag({ content: "[role=dialog] { animation-play-state: paused !important; }" });
  await page.getByRole("region", { name: "Sources table" }).getByRole("switch", { name: "CJ Dropshipping enabled" }).click();
  const dialog = page.getByRole("dialog", { name: "Disable CJ Dropshipping?" });
  await expect(dialog).toBeVisible();
  expect(await heldAnimation(dialog)).toEqual({
    animationName: "enter",
    animationDuration: "0.2s",
    animationTimingFunction: "cubic-bezier(0.16, 1, 0.3, 1)",
    transform: "translate3d(0px, 0px, 0px) scale3d(0.97, 0.97, 0.97) rotate(0deg)",
  });

  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog, "the dialog reports closed after Cancel").toHaveAttribute("data-state", "closed", { timeout: 2_000 });
  expect(await heldAnimation(dialog)).toEqual({
    animationName: "exit",
    animationDuration: "0.12s",
    animationTimingFunction: "cubic-bezier(0.7, 0, 0.84, 0)",
    transform: "translate3d(0px, 0px, 0px) scale3d(0.98, 0.98, 0.98) rotate(0deg)",
  });
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
  await expect(refresh).toHaveCSS("transition-duration", "0.12s"); // the press runs at `fast` (DEC-233)
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
