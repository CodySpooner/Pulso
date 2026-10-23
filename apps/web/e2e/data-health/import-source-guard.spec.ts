import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-089: while an import runs, the panel's Source select can't switch away from it. Switching used to reset
// the running commit, so its outcome and Open runs were lost; the file was re-checked against another template.
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };
const COMMIT = /\/api\/v1\/admin\/sources\/[^/]+\/import$/;

test("a running import keeps its source against keyboard and pointer, then the select works again", async ({ page }) => {
  const calls = await mockAdminApi(page);
  let release!: () => void;
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route(COMMIT, async (route) => {
    await held;
    await route.fallback();
  });
  await page.goto("/admin/data-health");
  const panel = page.getByRole("region", { name: "CSV import" });
  const select = panel.getByLabel("Source");
  await expect(select).toHaveValue("fx_frankfurter");
  await panel.locator('input[type="file"]').setInputFiles(file);
  await panel.getByRole("button", { name: "Import 3 rows" }).click();
  await expect(panel.getByRole("status")).toHaveText("Importing rates.csv…");

  // Keyboard: the select stays focusable, but arrows don't change it.
  await select.focus();
  await page.keyboard.press("ArrowUp");
  // Pointer, or assistive tech setting the value: the change event that a pick sends still keeps the running source.
  await select.evaluate((el: HTMLSelectElement) => {
    el.value = "cj";
    el.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await expect(select).toHaveValue("fx_frankfurter");
  await expect(panel.getByRole("status")).toHaveText("Importing rates.csv…");
  expect(calls.filter((c) => c.path.endsWith("/import/preview"))).toHaveLength(1); // never re-checked against another template
  await expect(select).toHaveAttribute("aria-disabled", "true"); // says it is unavailable, and a click can't open it
  expect(await select.evaluate((el) => getComputedStyle(el).pointerEvents)).toBe("none");

  // The original import finishes, and its outcome and Open runs belong to Frankfurter FX.
  release();
  await expect(panel.getByRole("status")).toHaveText(/^Imported into Frankfurter FX as run #501: 3 new/);
  await expect(select).toBeFocused(); // focus stays where the user left it
  await panel.getByRole("button", { name: "Open runs" }).click();
  await expect(page.getByRole("dialog", { name: "Frankfurter FX" })).toBeVisible();
  await page.keyboard.press("Escape");

  // Done: switching works as before.
  await expect(select).not.toHaveAttribute("aria-disabled", "true");
  await select.selectOption("cj");
  await expect(select).toHaveValue("cj");
  await expect(panel).toContainText("No import adapter yet");
});
