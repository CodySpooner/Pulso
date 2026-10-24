import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi, sources } from "./fixtures";

// imp-172 (DEC-228): a never-run source's drawer names the CSV import panel as a link-styled button. One press closes
// the drawer and opens the panel on that source, through the Sources row's own path (open(key)), so focus lands on
// Choose CSV…. Before, it took a close, a scroll and a click. Every closing frame still shows the drawer's title.
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };

async function openFx(page: Page) {
  await page.goto("/admin/data-health");
  const panel = page.getByRole("region", { name: "CSV import" });
  await panel.getByLabel("Source").selectOption("cj"); // FX is the panel's default: start elsewhere
  await page.getByRole("button", { name: "Frankfurter FX: open runs" }).first().click();
  const drawer = page.getByRole("dialog", { name: "Frankfurter FX" });
  await expect(drawer.getByRole("heading", { name: "No runs yet" })).toBeVisible();
  return { panel, drawer, link: drawer.getByRole("button", { name: "CSV import panel" }) };
}

/** Records the drawer title's text on every closing frame until the dialog is gone. */
async function sampleClosing(page: Page) {
  await page.evaluate(() => {
    const frames: string[] = [];
    Object.assign(window, { closing_: frames });
    const tick = () => {
      const dialog = document.querySelector('[role="dialog"]');
      if (!dialog) return;
      if (dialog.getAttribute("data-state") === "closed") frames.push(document.getElementById(dialog.getAttribute("aria-labelledby") ?? "")?.textContent ?? "");
      requestAnimationFrame(tick);
    };
    tick();
  });
}

for (const theme of ["dark", "light"] as const) {
  for (const width of [1440, 375]) {
    for (const input of ["mouse", "Enter"] as const) {
      test(`${input} on the drawer's CSV import panel opens the panel on FX at ${width}px ${theme}`, async ({ page }) => {
        await mockAdminApi(page); // Frankfurter FX: never run, CSV import ready
        await page.setViewportSize({ width, height: width < 1024 ? 812 : 900 });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
        const { panel, drawer, link } = await openFx(page);
        await expect(drawer).toContainText("Import a CSV from the CSV import panel to add its first run.");

        if (input === "Enter") {
          // Tab from the drawer itself (where it puts focus on open) to the button, then one Enter.
          let tabs = 0;
          while (!(await link.evaluate((el) => el === document.activeElement)) && tabs < 20) {
            await page.keyboard.press("Tab");
            tabs++;
          }
          expect(tabs).toBe(2); // the drawer, its status pill, then the button
          await sampleClosing(page);
          await page.keyboard.press("Enter");
        } else {
          await sampleClosing(page);
          await link.click();
        }

        await expect(page.getByRole("dialog")).toBeHidden();
        const choose = panel.getByRole("button", { name: "Choose CSV…" });
        await expect(choose).toBeFocused();
        await expect(choose).toBeInViewport();
        await expect(panel.getByLabel("Source")).toHaveValue("fx_frankfurter");
        const closing = await page.evaluate(() => (window as unknown as { closing_: string[] }).closing_);
        expect(closing.length).toBeGreaterThan(0);
        expect(closing.filter((t) => t !== "Frankfurter FX")).toEqual([]); // never an empty sheet
        expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
      });
    }
  }
}

test("with a file open for another source, the panel asks before switching (DEC-175)", async ({ page }) => {
  await mockAdminApi(page);
  await page.goto("/admin/data-health");
  const panel = page.getByRole("region", { name: "CSV import" });
  await panel.getByLabel("Source").selectOption("cj");
  await panel.locator('input[type="file"]').setInputFiles(file);
  await expect(panel.getByRole("status")).toContainText("3 valid rows");
  await page.getByRole("button", { name: "Frankfurter FX: open runs" }).first().click();
  await page.getByRole("dialog", { name: "Frankfurter FX" }).getByRole("button", { name: "CSV import panel" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(panel.getByLabel("Source")).toHaveValue("cj");
  await expect(panel.getByRole("button", { name: "Switch to Frankfurter FX" })).toBeFocused();
});

for (const csv_import of [null, "preview_only"] as const) {
  test(`a never-run source with csv_import ${csv_import} keeps today's text and no button`, async ({ page }) => {
    await mockAdminApi(page, { sources: sources.map((s) => (s.key === "fx_frankfurter" ? { ...s, csv_import } : s)) });
    await page.goto("/admin/data-health");
    await page.getByRole("button", { name: "Frankfurter FX: open runs" }).first().click();
    const drawer = page.getByRole("dialog", { name: "Frankfurter FX" });
    await expect(drawer).toContainText("This source is disabled, so the collector host won't run it until it's enabled.");
    await expect(drawer).not.toContainText("CSV import");
    await expect(drawer.getByRole("button", { name: "CSV import panel" })).toHaveCount(0);
  });
}

test("a never-run source that can run names both, and its button still opens the panel", async ({ page }) => {
  await mockAdminApi(page, {
    host: { live_runs_allowed: true },
    sources: sources.map((s) => (s.key === "fx_frankfurter" ? { ...s, enabled: true, status: "active" } : s)),
  });
  const { panel, drawer, link } = await openFx(page);
  await expect(drawer).toContainText("Press Run now in the Sources panel, or import a CSV from the CSV import panel, to add its first run.");
  await link.click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(panel.getByLabel("Source")).toHaveValue("fx_frankfurter");
  await expect(panel.getByRole("button", { name: "Choose CSV…" })).toBeFocused();
});
