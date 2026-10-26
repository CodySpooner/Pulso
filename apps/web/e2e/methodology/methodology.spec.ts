import { expect, test } from "@playwright/test";

import { contrastMisses } from "../p2-39/screens";
import { openPalette } from "../search/fixtures";

// p4-06 (MT-1, DEC-313): /methodology renders the committed export of the scoring code; no API, so no mocks.
test("the sidebar reaches Methodology in one click, with Lifecycle Stage and its version", async ({ page }) => {
  await page.goto("/");
  await page.locator("html[data-app-ready=true]").waitFor();
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Methodology" }).click();
  await expect(page).toHaveURL(/\/methodology$/);
  const lifecycle = page.locator("section#lifecycle-stage");
  await expect(lifecycle.getByRole("heading", { name: "Lifecycle Stage" })).toBeVisible();
  await expect(lifecycle.getByRole("textbox", { name: "Lifecycle Stage model_version" })).toHaveText(/^\d{3}-[0-9a-f]{12}$/);
  await expect(lifecycle.getByRole("table", { name: "Lifecycle Stage config" }).getByRole("row", { name: /^up/ })).toContainText("0.1823");
});

test("the palette opens Methodology", async ({ page }) => {
  const input = await openPalette(page);
  await input.fill("methodology");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/methodology$/);
  await expect(page.getByRole("heading", { level: 1, name: "Methodology" })).toBeVisible();
});

test("a contents link jumps to its section by keyboard, and every section has its anchor", async ({ page }) => {
  await page.goto("/methodology");
  const contents = page.getByRole("navigation", { name: "On this page" });
  const links = contents.getByRole("link");
  for (const href of await links.evaluateAll((as) => as.map((a) => a.getAttribute("href")!)))
    await expect(page.locator(href)).toHaveCount(1);
  const link = contents.getByRole("link", { name: "Explanation contract" });
  await link.focus();
  await expect(link).toBeFocused();
  expect(await link.evaluate((el) => getComputedStyle(el).outlineStyle)).toBe("solid");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#explanation$/);
  await expect(page.locator("section#explanation")).toBeInViewport();
});

for (const theme of ["dark", "light"] as const)
  test(`AA contrast in the ${theme} theme`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
    await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
    await page.goto("/methodology");
    await expect(page.locator("section#lifecycle-stage")).toBeVisible();
    expect(await page.evaluate(contrastMisses, "main")).toEqual([]);
  });

test("no horizontal page scroll at 375px", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/methodology");
  await expect(page.locator("section#lifecycle-stage")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

// fix-ci-2b87388: the page check above passed locally with the Saturation inputs table 1px from the edge and failed on
// CI's fonts, so every table and code path is measured against its own box: none spills out or is cut off.
test("at 375px every table and code path wraps inside its card", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/methodology");
  await expect(page.locator("section#saturation")).toBeVisible();
  const spills = await page
    .locator("main table, main h3 + code")
    .evaluateAll((els) =>
      els.filter((el) => el.getBoundingClientRect().width > el.parentElement!.clientWidth + 0.5 || el.scrollWidth > el.clientWidth).map((el) => el.getAttribute("aria-label") ?? el.textContent),
    );
  expect(spills).toEqual([]);
  await expect(page.locator("section#saturation h3 + code", { hasText: "pulso_ml.scores.saturation.saturation_scores" })).toBeVisible();
});

// p4-35 (MT-1 part 2, DEC-354): #confidence states the formula, the freshness rule and each source's cadence.
test("Confidence states the formula and each source's cadence, one click from the contents", async ({ page }) => {
  await page.goto("/methodology");
  await page.getByRole("navigation", { name: "On this page" }).getByRole("link", { name: "Confidence" }).click();
  await expect(page).toHaveURL(/#confidence$/);
  const section = page.locator("section#confidence");
  await expect(section).toBeInViewport();
  await expect(section).toContainText("confidence = Σ weight × freshness over the present inputs");
  await expect(section).toContainText("stale: older, so it is missing");
  const trends = section.getByRole("table", { name: "Source cadences" }).getByRole("row", { name: /google_trends/ });
  await expect(trends).toContainText("weekly");
  await expect(trends.getByRole("cell")).toHaveText(["10.5 d", "21 d"]);
});
