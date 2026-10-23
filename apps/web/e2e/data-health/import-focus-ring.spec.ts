import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-095: a locked Import button ("Importing…", or blocked by the source) stays focusable, so its focus
// ring must keep >= 3:1 on the card in both themes. The Button's aria-disabled opacity-50 faded it to 1.93:1.
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };
const COMMIT = /\/api\/v1\/admin\/sources\/[^/]+\/import$/;

async function openPanel(page: Page, theme: "dark" | "light", width: number) {
  await page.setViewportSize({ width, height: width < 768 ? 812 : 900 });
  await page.emulateMedia({ colorScheme: theme });
  await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
  await page.goto("/admin/data-health");
  const panel = page.getByRole("region", { name: "CSV import" });
  const choose = panel.getByRole("button", { name: "Choose CSV…" });
  await choose.focus();
  const chooser = page.waitForEvent("filechooser");
  await page.keyboard.press("Enter");
  await (await chooser).setFiles(file);
  await expect(panel.getByRole("status")).toHaveText("3 valid rows · 1 invalid row");
  return panel;
}

/**
 * The focused control's ring, measured from screenshot pixels: on each side, the strongest pixel between the
 * control and 8px out against the card. `full` is the ring token itself on the card, i.e. an unfaded ring.
 */
async function ringContrast(page: Page, control: Locator) {
  await control.evaluate((el) => el.scrollIntoView({ block: "center" })); // clear of the phone's bottom nav
  const box = (await control.boundingBox())!;
  const pad = 8;
  const x = Math.floor(box.x) - pad;
  const y = Math.floor(box.y) - pad;
  const clip = { x, y, width: Math.ceil(box.x + box.width) + pad - x, height: Math.ceil(box.y + box.height) + pad - y };
  const png = (await page.screenshot({ clip, animations: "disabled" })).toString("base64");
  const inner = { left: box.x - x, top: box.y - y, right: box.x + box.width - x, bottom: box.y + box.height - y };
  return control.evaluate(
    async (el, { png, inner }) => {
      const rgb = (css: string) => css.match(/\d+(\.\d+)?/g)!.slice(0, 3).map(Number);
      const lum = (c: number[]) => {
        const [r, g, b] = c.map((v) => (v / 255 <= 0.04045 ? v / 255 / 12.92 : ((v / 255 + 0.055) / 1.055) ** 2.4));
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
      };
      const ratio = (a: number[], b: number[]) => {
        const [hi, lo] = [lum(a), lum(b)].sort((p, q) => q - p);
        return (hi + 0.05) / (lo + 0.05);
      };
      const card = rgb(getComputedStyle(el.closest("section")!).backgroundColor);
      const bytes = Uint8Array.from(atob(png), (c) => c.charCodeAt(0));
      const bitmap = await createImageBitmap(new Blob([bytes], { type: "image/png" }));
      const ctx = new OffscreenCanvas(bitmap.width, bitmap.height).getContext("2d")!;
      ctx.drawImage(bitmap, 0, 0);
      const best = (points: [number, number][]) =>
        Math.max(...points.map(([px, py]) => ratio([...ctx.getImageData(px, py, 1, 1).data.slice(0, 3)], card)));
      const midX = Math.round((inner.left + inner.right) / 2);
      const midY = Math.round((inner.top + inner.bottom) / 2);
      const span = (from: number, to: number) => Array.from({ length: Math.max(0, to - from) }, (_, i) => from + i);
      return {
        left: best(span(0, Math.floor(inner.left)).map((px) => [px, midY])),
        right: best(span(Math.ceil(inner.right), bitmap.width).map((px) => [px, midY])),
        top: best(span(0, Math.floor(inner.top)).map((py) => [midX, py])),
        bottom: best(span(Math.ceil(inner.bottom), bitmap.height).map((py) => [midX, py])),
        full: ratio(rgb(getComputedStyle(el).outlineColor), card),
      };
    },
    { png, inner },
  );
}

async function expectFullRing(page: Page, control: Locator) {
  await expect(control).toBeFocused();
  const { full, ...sides } = await ringContrast(page, control);
  for (const [side, contrast] of Object.entries(sides)) {
    expect(contrast, `${side} side of the ring`).toBeGreaterThanOrEqual(3);
    expect(contrast, `${side} side at the ring token's full ${full.toFixed(2)}:1`).toBeGreaterThanOrEqual(full - 0.05);
  }
}

for (const theme of ["dark", "light"] as const) {
  for (const width of [1440, 375]) {
    test(`Importing… keeps a full focus ring and one commit (${width}px ${theme})`, async ({ page }) => {
      await mockAdminApi(page);
      let commits = 0;
      let release!: () => void;
      const held = new Promise<void>((resolve) => (release = resolve));
      await page.route(COMMIT, async (route) => {
        commits += 1;
        await held;
        await route.fallback();
      });
      const panel = await openPanel(page, theme, width);

      await page.keyboard.press("Tab");
      await expect(panel.getByRole("button", { name: "Import 3 rows" })).toBeFocused();
      await page.keyboard.press("Enter");
      const importing = panel.getByRole("button", { name: "Importing…" });
      await expect(importing).toHaveAttribute("aria-disabled", "true");
      await expect(panel.getByRole("status")).toHaveText("Importing rates.csv…");
      await expectFullRing(page, importing);

      // A pointer click, Space and Enter start nothing; the keyboard goes last, so focus stays visible.
      await importing.click({ force: true });
      await page.keyboard.press("Space");
      await page.keyboard.press("Enter");
      await expect(importing).toBeFocused();

      release();
      await expect(panel.getByRole("status")).toHaveText(/^Imported into Frankfurter FX as run #501/);
      await expect(panel.getByRole("alert")).toHaveText("");
      const openRuns = panel.getByRole("button", { name: "Open runs" }); // completion focus, as before (imp-056)
      await expect(openRuns).toBeFocused();
      expect(await openRuns.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
      expect(commits).toBe(1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });
  }
}

test("a blocked Import button keeps a full focus ring too (light)", async ({ page }) => {
  await mockAdminApi(page);
  const panel = await openPanel(page, "light", 1440);
  await panel.getByLabel("Source").selectOption("shopify_stores"); // preview only: no import adapter yet
  const blocked = panel.getByRole("button", { name: "Import 3 rows" });
  await expect(blocked).toHaveAttribute("aria-disabled", "true");
  await blocked.focus();
  await expectFullRing(page, blocked);
});
