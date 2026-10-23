import { expect, test } from "@playwright/test";

test("the palette reaches the gallery after delayed hydration", async ({ page }) => {
  const scripts = Promise.withResolvers<void>();
  await page.route(/\/_next\/static\/.*\.js(?:\?|$)/, async (route) => {
    await scripts.promise;
    await route.continue();
  });
  try {
    await page.goto("/", { waitUntil: "commit" });
    await expect(page.getByRole("heading", { level: 1, name: "Daily Pulse" })).toBeVisible();
    // HTML alone is not readiness: no application JavaScript has been released yet.
    await expect(page.locator("html")).not.toHaveAttribute("data-app-ready", "true");
  } finally {
    scripts.resolve();
  }
  await expect(page.locator("html")).toHaveAttribute("data-app-ready", "true");
  await page.keyboard.press("Control+K");
  await expect(page.getByRole("combobox")).toBeFocused();
  await page.getByRole("combobox").fill("gallery");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: "UI gallery" })).toBeFocused();
});
