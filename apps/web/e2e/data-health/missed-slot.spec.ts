import { expect, test, type Locator, type Page } from "@playwright/test";

import { host, mockAdminApi, type MockOptions } from "./fixtures";

// imp-124 + imp-125 (aud-010 A10-02, A10-04): an Overdue source names its latest missed slot in its row, phone
// card and run drawer, with a link that moves focus to the Open gaps table; and every row and card shows a
// visible way into the run drawer at rest, which opens by click and keyboard and gets focus back on close.

// The slot, then the reason as the Open gaps table words it, each on its own line.
const SLOT = "Missed Oct 22, 10:00–12:00 UTC";
const LINK = `${SLOT} Host offline (in Open gaps)`;
const NAMES = ["Shopify stores", "CJ Dropshipping", "Google Trends", "Frankfurter FX"];

async function load(page: Page, width: number, theme: "dark" | "light", options: MockOptions = {}) {
  await mockAdminApi(page, options);
  await page.setViewportSize({ width, height: width < 1024 ? 812 : 900 });
  await page.emulateMedia({ colorScheme: theme });
  await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
  await page.goto("/admin/data-health");
}

/** The source's table row from md up, its phone card below. */
function row(page: Page, width: number, name: string): Locator {
  const trigger = page.getByRole("button", { name: `${name}: open runs` });
  return width < 768 ? page.getByRole("listitem").filter({ has: trigger }) : page.getByRole("region", { name: "Sources table" }).getByRole("row").filter({ has: trigger });
}

const pageScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
/** From lg the shell scrolls inside `main`; the document scrolling too would shift the whole shell up. */
const shellShift = (page: Page) => page.evaluate(() => (innerWidth >= 1024 ? document.scrollingElement!.scrollTop : 0));

for (const theme of ["dark", "light"] as const) {
  for (const width of [1440, 375]) {
    test(`Overdue names its missed slot and links to Open gaps at ${width}px ${theme}`, async ({ page }) => {
      await load(page, width, theme);
      const link = row(page, width, "Google Trends").getByRole("link", { name: LINK });
      await expect(link).toBeVisible();
      await expect(link).toHaveAttribute("href", "#open-gaps");
      // Only the Overdue source carries one: CJ's gap ended 79 h ago, outside the 24 h window.
      await expect(page.getByRole("link", { name: /\(in Open gaps\)$/ }).locator("visible=true")).toHaveCount(1);
      // The slot reads on one line and the reason on the next, never cut, and the table still fits.
      await expect(link.locator("> span:not(.sr-only)")).toHaveText([SLOT, "Host offline"]);
      expect(await link.locator("> span:not(.sr-only)").first().evaluate((el) => el.getBoundingClientRect().height)).toBe(16);
      if (width >= 768) {
        const region = page.getByRole("region", { name: "Sources table" });
        expect(await region.evaluate((el) => el.scrollWidth - el.clientWidth)).toBe(0);
      }
      expect(await pageScroll(page)).toBe(0);

      await link.click();
      const gaps = page.locator("#open-gaps");
      await expect(gaps).toBeFocused();
      await expect(gaps).toHaveText(/^Open gaps/);
      await expect(gaps).toBeInViewport();
      expect(await shellShift(page)).toBe(0);
      await expect(page.getByRole("region", { name: "Open gaps" })).toContainText("Google Trends");
    });

    test(`the run drawer names the missed slot and its link lands on Open gaps at ${width}px ${theme}`, async ({ page }) => {
      await load(page, width, theme);
      await page.getByRole("button", { name: "Google Trends: open runs" }).locator("visible=true").click();
      const drawer = page.getByRole("dialog", { name: "Google Trends" });
      await expect(drawer).toContainText("Succeeded"); // the newest run, which alone would not say why
      await drawer.getByRole("link", { name: LINK }).click();
      await expect(drawer).toBeHidden();
      await expect(page.locator("#open-gaps")).toBeFocused();
      await expect(page.locator("#open-gaps")).toBeInViewport();
      expect(await shellShift(page)).toBe(0);
    });

    test(`every row and card shows its runs cue at rest at ${width}px ${theme}`, async ({ page }) => {
      await load(page, width, theme);
      for (const name of NAMES) {
        const triggers = row(page, width, name).getByRole("button", { name: /: open runs$/ });
        await expect(triggers).toHaveCount(1); // one drawer trigger per row, so no extra Tab stop
        await expect(triggers.locator("svg")).toBeVisible(); // the chevron
        await expect(triggers.getByText(name, { exact: true })).toHaveCSS("text-decoration-line", "underline"); // at rest, no hover
      }
    });
  }

  test(`the runs cue opens the drawer by click and keyboard and gets focus back at 375px and 1440px ${theme}`, async ({ page }) => {
    for (const width of [375, 1440]) {
      await load(page, width, theme);
      const trigger = page.getByRole("button", { name: "CJ Dropshipping: open runs" }).locator("visible=true");
      const drawer = page.getByRole("dialog", { name: "CJ Dropshipping" });
      await trigger.click();
      await expect(drawer).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(drawer).toBeHidden();
      await expect(trigger).toBeFocused();

      await page.keyboard.press("Enter");
      await expect(drawer).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(drawer).toBeHidden();
      await expect(trigger).toBeFocused();
    }
  });
}

test("keyboard: Enter on the row's missed-slot link and on the drawer's moves focus to Open gaps", async ({ page }) => {
  await load(page, 1440, "dark");
  const table = page.getByRole("region", { name: "Sources table" });
  await table.getByRole("link", { name: LINK }).focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#open-gaps")).toBeFocused();

  await table.getByRole("button", { name: "Google Trends: open runs" }).focus();
  await page.keyboard.press("Enter");
  const drawer = page.getByRole("dialog", { name: "Google Trends" });
  await drawer.getByRole("link", { name: LINK }).focus();
  await page.keyboard.press("Enter");
  await expect(drawer).toBeHidden();
  await expect(page.locator("#open-gaps")).toBeFocused();
  // Escape-closing still returns focus to the opener.
  await table.getByRole("button", { name: "Google Trends: open runs" }).focus();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Escape");
  await expect(table.getByRole("button", { name: "Google Trends: open runs" })).toBeFocused();
});

test("a missed slot off the loaded gap page reads its end from the gap summary", async ({ page }) => {
  await load(page, 1440, "dark", { host: { open_gaps: host.open_gaps.filter((g) => g.source_key !== "google_trends") } });
  const link = row(page, 1440, "Google Trends").getByRole("link", { name: "Missed a slot ending Oct 22, 12:00 UTC (in Open gaps)" });
  await expect(link).toBeVisible();
  await page.getByRole("button", { name: "Google Trends: open runs" }).locator("visible=true").click();
  await expect(page.getByRole("dialog", { name: "Google Trends" })).toContainText("Missed a slot ending Oct 22, 12:00 UTC");
});

test("a cross-midnight slot keeps each phrase whole and the table still fits at 1440px", async ({ page }) => {
  // p1-53: Google Trends' gaps 11 h earlier, so the slot runs Oct 21, 23:00 – Oct 22, 01:00.
  const earlier = (iso: string) => new Date(Date.parse(iso) - 11 * 3_600_000).toISOString();
  const open_gaps = host.open_gaps.map((g) => (g.source_key === "google_trends" ? { ...g, slot_start: earlier(g.slot_start), slot_end: earlier(g.slot_end) } : g));
  await load(page, 1440, "dark", { host: { open_gaps, latest_gap_ends: { ...host.latest_gap_ends, google_trends: earlier(host.latest_gap_ends.google_trends!) } } });
  const link = row(page, 1440, "Google Trends").getByRole("link", { name: "Missed Oct 21, 23:00 – Oct 22, 01:00 UTC Host offline (in Open gaps)" });
  await expect(link).toBeVisible();
  // A line may break between the phrases, never inside one, whatever the font's widths.
  const phrases = link.locator(".whitespace-nowrap");
  await expect(phrases).toHaveText(["Missed Oct 21, 23:00 –", "Oct 22, 01:00 UTC"]);
  for (const phrase of await phrases.all()) expect(await phrase.evaluate((el) => el.getClientRects().length)).toBe(1);
  const region = page.getByRole("region", { name: "Sources table" });
  expect(await region.evaluate((el) => el.scrollWidth - el.clientWidth)).toBe(0);
});

/** Whether the element owns the 44×44 px square around its centre, as e2e/touch-targets.spec.ts probes it (A11Y-02). */
const ownsSquare = (el: Locator) =>
  el.evaluate((node) => {
    const r = node.getBoundingClientRect();
    const [cx, cy] = [r.left + r.width / 2, r.top + r.height / 2];
    return [-21, 0, 21].every((dx) => [-21, 0, 21].every((dy) => node.contains(document.elementFromPoint(cx + dx, cy + dy))));
  });

test.describe("touch", () => {
  test.use({ hasTouch: true });

  test("the Overdue pill, its note link and its neighbours keep their 44 px hit squares", async ({ page }) => {
    for (const width of [1024, 375]) {
      await load(page, width, "dark");
      const name = page.getByRole("button", { name: "Google Trends: open runs" }).locator("visible=true");
      const scope = row(page, width, "Google Trends");
      const pills = page.getByRole("button", { name: /^(Healthy|Overdue)$/ }).locator("visible=true");
      for (const el of [scope.getByRole("link", { name: LINK }), name, pills.first(), pills.last()]) {
        await el.scrollIntoViewIfNeeded();
        expect(await ownsSquare(el)).toBe(true);
      }
      await name.click();
      const drawer = page.getByRole("dialog", { name: "Google Trends" });
      // Polled: the drawer's enter animation moves both until it settles.
      for (const el of [drawer.getByRole("link", { name: LINK }), drawer.getByRole("button", { name: "Overdue" })]) await expect.poll(() => ownsSquare(el)).toBe(true);
    }
  });
});
