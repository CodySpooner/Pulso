import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockAdminApi, offlineNetwork, type Call } from "./fixtures";

// imp-134 (aud-014 A14-03): offline, nothing is queued. One banner says so and how old the data is; Refresh, the
// switches, Run now and Import say why they're unavailable; a disable pressed then cancelled offline, and an
// import pressed offline, are never sent on reconnect.

const HINT = "You're offline. Reconnect to use this.";
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };
const patches = (calls: Call[]) => calls.filter((c) => c.method === "PATCH");
const commits = (calls: Call[]) => calls.filter((c) => c.method === "POST" && c.path.endsWith("/import"));
const runs = (calls: Call[]) => calls.filter((c) => c.method === "POST" && c.path.endsWith("/run"));
/** `control`'s tooltip is open with the offline reason: an open Radix tooltip describes its trigger. */
const saysWhy = async (control: Locator) => {
  await expect(control).toHaveAccessibleDescription(HINT);
  await expect(control.page().getByRole("tooltip", { name: HINT }).first()).toBeVisible();
};
/**
 * Presses an unavailable `control` and checks it says why. A tap shows the reason (imp-126); on a desktop, keyboard
 * focus shows it at once (a mouse sees it on hover), then a click does nothing. force: aria-disabled, so
 * Playwright would wait for it to enable.
 */
async function pressOffline(control: Locator, touch: boolean) {
  if (touch) {
    await control.tap({ force: true });
    await saysWhy(control);
    return;
  }
  // Not scrolled first: focusing an off-screen control scrolls main, and the reason stays open (imp-156).
  await control.blur(); // focus() on the focused element fires no focus event
  await control.focus();
  await saysWhy(control);
  await control.click({ force: true });
}
const noHScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

for (const [width, height] of [
  [1440, 900],
  [375, 812],
] as const) {
  test.describe(`${width}px`, () => {
    const touch = width < 768;
    test.use({ viewport: { width, height }, hasTouch: touch });

    test("offline: one banner, every write control says why, and nothing is sent on reconnect", async ({ page, context }) => {
      const calls = await mockAdminApi(page, { host: { live_runs_allowed: true } });
      const { offlineCalls, setOffline } = await offlineNetwork(page, context);
      await page.goto("/admin/data-health");
      const banner = page.getByRole("status").filter({ hasText: "You're offline." });
      const refresh = page.getByRole("button", { name: "Refresh" });
      const cj = page.getByRole("switch", { name: "CJ Dropshipping enabled" });
      const dialog = page.getByRole("dialog", { name: "Disable CJ Dropshipping?" });
      const panel = page.getByRole("region", { name: "CSV import" });
      const importButton = panel.getByRole("button", { name: "Import 3 rows" });

      // Online: a checked file, and the Disable dialog open, when the connection drops.
      await panel.locator('input[type="file"]').setInputFiles(file);
      await expect(importButton).toBeVisible();
      await cj.click();
      await expect(dialog).toBeVisible();
      await setOffline(true);

      // Disable fails at once instead of waiting for the connection, and Cancel then leaves nothing pending.
      await dialog.getByRole("button", { name: "Disable", exact: true }).click();
      await expect(dialog.getByRole("alert")).toHaveText("Couldn't disable CJ Dropshipping: you're offline. Try again once you reconnect.");
      expect(offlineCalls).toEqual(["PATCH /api/v1/admin/sources/cj"]); // the one press, failed at once
      await dialog.getByRole("button", { name: "Cancel" }).click();
      await expect(dialog).toBeHidden();
      await expect(cj).toBeFocused(); // after the exit animation, so it never lands on a later press

      await expect(banner).toHaveCount(1);
      await expect(banner).toHaveText("You're offline. Showing data as of Oct 22, 14:00 UTC. Refresh and actions are off until you reconnect.");
      await expect(banner).toBeInViewport();
      expect(await noHScroll(page)).toBe(true);

      // Each control says why, and a press does nothing else.
      await pressOffline(refresh, touch);
      await expect(refresh).toHaveAttribute("aria-disabled", "true");
      await expect(refresh).toHaveText("Refresh"); // no refetch started

      await pressOffline(cj, touch);
      await expect(dialog).toBeHidden();
      await expect(cj).toBeChecked();

      await pressOffline(page.getByRole("button", { name: "Run CJ Dropshipping now" }), touch);

      // Import keeps its existing reason line under the button, so a phone sees it without a tap.
      await expect(importButton).toHaveAttribute("aria-disabled", "true");
      await expect(importButton).toHaveAccessibleDescription(HINT);
      await expect(panel.getByText(HINT)).toBeVisible();
      await importButton.click({ force: true });
      await expect(importButton).toHaveText("Import 3 rows"); // not "Importing…"

      await pressOffline(panel.getByRole("button", { name: "Choose another…" }), touch);

      expect(offlineCalls).toHaveLength(1); // the controls sent nothing
      // Reconnect: the banner goes, the controls come back, and nothing pressed offline is sent.
      await setOffline(false);
      await expect(banner).toHaveCount(0);
      await expect(refresh).not.toHaveAttribute("aria-disabled", "true");
      await expect(importButton).not.toHaveAttribute("aria-disabled", "true");
      await page.waitForTimeout(1_500); // TanStack resumed paused mutations at once on reconnect (aud-014 R8)
      expect(patches(calls)).toHaveLength(0);
      expect(commits(calls)).toHaveLength(0);
      expect(runs(calls)).toHaveLength(0);

      // One press, online, works as before.
      await cj.click();
      await expect(dialog).toBeVisible();
    });
  });
}
