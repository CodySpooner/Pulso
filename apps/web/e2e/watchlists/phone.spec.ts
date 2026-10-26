import { expect, test, type Page } from "@playwright/test";

import { CATALOG, MAIN, mockWatchlistsApi, PET } from "./fixtures";

// WF-8 (p4-38, DEC-363): /watchlists on a phone, against fixture responses (the E2E auth bypass). The list switcher,
// the cards, a row's menu and the undo toast, by touch.
const insets = { top: 47, bottom: 34 }; // iPhone 14 portrait, as e2e/palette-safe-area.spec.ts
const cardOf = (page: Page, title: string) => page.getByRole("list", { name: "Main products" }).getByRole("article").filter({ hasText: title });
const toast = (page: Page) => page.getByRole("status").filter({ hasText: /\S/ }).last();

/** Controls under `root` that don't own the 44×44 px square around their centre, as e2e/touch-targets.spec.ts probes it. */
const smallTargets = (page: Page, root: string) =>
  page.locator(root).evaluate((scope) =>
    [...scope.querySelectorAll<HTMLElement>("a[href], button, input, select, textarea, [role=menuitem]")]
      .filter((el) => !el.matches(":disabled") && el.checkVisibility({ visibilityProperty: true, opacityProperty: true }))
      .flatMap((el) => {
        el.scrollIntoView({ block: "center" });
        const r = el.getBoundingClientRect();
        const [cx, cy] = [r.left + r.width / 2, r.top + r.height / 2];
        const owned = [-21, 0, 21].every((dx) => [-21, 0, 21].every((dy) => el.contains(document.elementFromPoint(cx + dx, cy + dy))));
        return owned ? [] : [`${el.getAttribute("aria-label") || el.textContent?.trim().slice(0, 40)} (${Math.round(r.width)}×${Math.round(r.height)})`];
      }),
  );

test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

test("every control on the page, in a row's menu and in the undo toast owns a 44 px hit area, with no sideways scroll", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" }); // measure the settled menu, not its open animation
  await mockWatchlistsApi(page);
  await page.goto("/watchlists");
  await expect(cardOf(page, CATALOG[0].title)).toBeVisible();
  expect(await smallTargets(page, "main")).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBe(0);

  await page.getByRole("button", { name: `Actions for ${CATALOG[0].title}` }).tap();
  await expect(page.getByRole("menu")).toBeVisible();
  expect(await smallTargets(page, "[role=menu]")).toEqual([]);
  await page.getByRole("menuitem", { name: "Remove" }).tap();
  await expect(toast(page).getByRole("button", { name: "Undo" })).toBeVisible();
  expect(await smallTargets(page, "[role=status]:has(button)")).toEqual([]);
});

test("a row's Move to lists the other lists inline and on screen; one tap moves the product", async ({ page }) => {
  const { writes } = await mockWatchlistsApi(page);
  await page.goto("/watchlists");
  await page.getByRole("button", { name: `Actions for ${CATALOG[0].title}` }).tap();
  const menu = page.getByRole("menu");
  await expect(menu.getByRole("group", { name: "Move to" }).getByRole("menuitem")).toHaveText(["Pet niche", "Q4 gifts"]);
  const box = (await menu.boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(375);
  await menu.getByRole("menuitem", { name: "Pet niche" }).tap();
  await expect(toast(page)).toHaveText("Moved to Pet niche.");
  await expect(cardOf(page, CATALOG[0].title)).toHaveCount(0);
  expect(writes.at(-1)).toEqual({ method: "POST", path: `/api/v1/watchlists/${MAIN}/items/move`, body: { product_ids: [CATALOG[0].id], to: PET } });
});

test("the undo toast clears the tab bar and the home indicator; Undo brings the product back", async ({ page }) => {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setSafeAreaInsetsOverride", { insets });
  await mockWatchlistsApi(page);
  await page.goto("/watchlists");
  await page.getByRole("button", { name: `Actions for ${CATALOG[0].title}` }).tap();
  await page.getByRole("menuitem", { name: "Remove" }).tap();
  await expect(cardOf(page, CATALOG[0].title)).toHaveCount(0);
  const note = toast(page);
  await expect(note).toContainText(`Removed ${CATALOG[0].title} from Main.`);
  const [bar, card] = await Promise.all([page.getByRole("navigation", { name: "Tab bar" }).boundingBox(), note.locator("div").first().boundingBox()]);
  expect(bar!.height).toBe(56 + insets.bottom);
  expect(card!.y + card!.height).toBeLessThanOrEqual(bar!.y - 8); // above the tab bar, never under it
  await note.getByRole("button", { name: "Undo" }).tap();
  await expect(cardOf(page, CATALOG[0].title)).toBeVisible();
});
