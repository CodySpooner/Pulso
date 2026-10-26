import { expect, test } from "@playwright/test";

// Owner review screenshots of the Phase 0 shell (WEB-6) and the /admin/ui gallery (WEB-9): 1440px and
// 375px, dark and light. Run with `pnpm --filter web e2e:screenshots`; output goes to docs/screenshots/phase-0/.
const OUT = "../../docs/screenshots/phase-0";

const pages = [
  { name: "shell", path: "/", h1: "Daily Pulse", whole: false },
  { name: "admin-ui", path: "/admin/ui", h1: "UI gallery", whole: true },
];

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    for (const p of pages) {
      test(`${p.name} ${width}px ${theme}`, async ({ page }) => {
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
        await page.goto(p.path);
        await expect(page.getByRole("heading", { level: 1, name: p.h1 })).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(800); // logo draw (instant under reduced motion) and lazy Motion features
        if (p.whole) {
          // From 1024px the page scrolls inside <main>, so fullPage can't see it: grow the viewport instead.
          const contentHeight = await page.evaluate(() => document.getElementById("main")!.scrollHeight + 80);
          await page.setViewportSize({ width, height: Math.max(height, contentHeight) });
          await page.waitForTimeout(500); // let the taller layout paint before the capture
        }
        await page.screenshot({ path: `${OUT}/${p.name}-${width}-${theme}.png` });
      });
    }
  }
}

test("command palette 1440px dark", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(() => localStorage.setItem("theme", "dark"));
  await page.goto("/");
  await page.keyboard.press("Control+K");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("ArrowDown");
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/palette-1440-dark.png` });
});

test("coming-soon route 1440px dark", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(() => localStorage.setItem("theme", "dark"));
  await page.goto("/ask"); // Discover was built in UX-2 (p2-03), the Screener in WF-1b (p4-32)
  await expect(page.getByText("Ask Pulso arrives in Phase 5")).toBeVisible();
  await page.screenshot({ path: `${OUT}/coming-soon-1440-dark.png` });
});
