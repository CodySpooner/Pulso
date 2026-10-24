import { expect, test, type Locator, type Page } from "@playwright/test";

import { activity, mockAdminApi, problem, withActivity } from "./fixtures";

// imp-165: a closing dialog keeps what it showed open through its exit animation. Every animation frame from the
// close until the dialog is gone is sampled: each has the title as the dialog's accessible name (and an error the
// dialog showed), then focus is back on the control that opened it. Before, the body went with the close, so the
// exit faded an empty box and the name was gone for ~170 ms before focus returned (closing frames with it: 0).
const PAGE = "/admin/data-health";
const table = (page: Page) => page.getByRole("region", { name: "Sources table" });

/**
 * Records, every frame until no dialog is left, its state and accessible name (aria-labelledby) and its text. It
 * also records the moment the dialog reports closed (a MutationObserver), so a frame stall that outlasts the exit
 * can't leave the close unsampled (imp-183).
 */
async function sampleUntilGone(page: Page) {
  await page.evaluate(() => {
    const frames: { state: string | null; name: string; text: string }[] = [];
    Object.assign(window, { frames_: frames });
    const sample = () => {
      const dialog = document.querySelector('[role="dialog"]');
      if (!dialog) return false;
      const title = document.getElementById(dialog.getAttribute("aria-labelledby") ?? "");
      frames.push({ state: dialog.getAttribute("data-state"), name: title?.textContent ?? "", text: dialog.textContent ?? "" });
      return true;
    };
    new MutationObserver((_, observer) => {
      if (!document.querySelector('[role="dialog"][data-state="closed"]')) return;
      observer.disconnect();
      sample();
    }).observe(document.body, { subtree: true, attributeFilter: ["data-state"] });
    const tick = () => {
      if (sample()) requestAnimationFrame(tick);
    };
    tick();
  });
}

const closingFrames = (page: Page) =>
  page.evaluate(() => (window as unknown as { frames_: { state: string | null; name: string; text: string }[] }).frames_.filter((f) => f.state === "closed"));

const cases: { name: string; title: string; open: (page: Page) => Promise<Locator>; error?: string }[] = [
  { name: "Disable", title: "Disable CJ Dropshipping?", open: async (page) => table(page).getByRole("switch", { name: "CJ Dropshipping enabled" }) },
  {
    name: "Disable after a failed save",
    title: "Disable CJ Dropshipping?",
    error: "Couldn't disable CJ Dropshipping: The API is restarting. Try again.",
    open: async (page) => {
      await page.route("**/api/v1/admin/sources/cj", (route) => (route.request().method() === "PATCH" ? route.fulfill({ status: 503, json: problem(503, "req_exit") }) : route.fallback()));
      return table(page).getByRole("switch", { name: "CJ Dropshipping enabled" });
    },
  },
  { name: "Latest CJ order", title: "Latest CJ order", open: async (page) => table(page).getByRole("button", { name: "Update order for CJ activity" }) },
];

for (const motion of ["no-preference", "reduce"] as const) {
  test.describe(`${motion} motion`, () => {
    test.use({ reducedMotion: motion });

    for (const c of cases) {
      test(`${c.name}: Cancel keeps the title until the dialog is hidden, then focus is back on its opener`, async ({ page }) => {
        await mockAdminApi(page, { sources: withActivity(activity("ok", 22)) });
        const opener = await c.open(page);
        await page.goto(PAGE);
        await opener.click();
        const dialog = page.getByRole("dialog", { name: c.title });
        await expect(dialog).toBeVisible();
        if (c.error) {
          await dialog.getByRole("button", { name: "Disable", exact: true }).click();
          await expect(dialog.getByRole("alert")).toHaveText(c.error);
        }
        await page.waitForTimeout(300); // the enter animation has finished

        await sampleUntilGone(page);
        await dialog.getByRole("button", { name: "Cancel" }).click();
        await expect(dialog).toBeHidden();
        await expect(opener).toBeFocused();

        const frames = await closingFrames(page);
        // With motion the exit runs ~120 ms (imp-177), so frames are sampled; reduced motion may finish before the next frame.
        if (motion === "no-preference") expect(frames.length, "closing samples (a frame stall shortens the exit to fewer)").toBeGreaterThan(3);
        expect(frames.filter((f) => f.name !== c.title)).toEqual([]);
        if (c.error) expect(frames.filter((f) => !f.text.includes(c.error!))).toEqual([]);
      });
    }
  });
}
