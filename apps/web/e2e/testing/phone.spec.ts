import { expect, test, type Page } from "@playwright/test";

import { mockTestingApi } from "./fixtures";

// WF-8 (p4-38, DEC-363): the Testing Board on a phone, against fixture responses (the E2E auth bypass). One column at a
// time, picked with the Column control; a card moves by its "Move to…" menu, never a drag; the drawer is a full sheet.
const insets = { top: 47, bottom: 34 }; // iPhone 14 portrait, as e2e/palette-safe-area.spec.ts
const column = (page: Page, label: string) => page.getByRole("region", { name: new RegExp(`^${label}\\b`) });
const card = (page: Page, label: string, title: string) => column(page, label).getByRole("article", { name: title });
const pick = (page: Page, label: string) => page.getByRole("group", { name: "Column" }).getByRole("button", { name: new RegExp(`^${label}\\b`) });
const toast = (page: Page) => page.getByRole("status").filter({ hasText: /\S/ }).last();
const pageScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - innerWidth);

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

test("one column at a time: Testing first, the picker switches, a deep link opens its test's column", async ({ page }) => {
  await mockTestingApi(page);
  await page.goto("/testing");
  await expect(pick(page, "Testing")).toHaveAttribute("aria-pressed", "true");
  await expect(pick(page, "Testing")).toHaveAccessibleName("Testing, 4 tests");
  await expect(card(page, "Testing", "LED strip lights")).toBeVisible();
  await expect(column(page, "Idea")).toBeHidden();
  await pick(page, "Idea").tap();
  await expect(card(page, "Idea", "Sunset projection lamp")).toBeVisible();
  await expect(column(page, "Testing")).toBeHidden();
  expect(await pageScroll(page)).toBe(0);

  await page.goto("/testing?test=3"); // Mini waffle maker, a Winner
  await expect(page.getByRole("dialog", { name: "Mini waffle maker" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(pick(page, "Winner")).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#test-3")).toBeFocused(); // the card it closes back to is on screen
});

test("a card moves by touch, without a drag; the view follows it, and Undo brings both back", async ({ page }) => {
  const api = await mockTestingApi(page);
  await page.goto("/testing");
  await pick(page, "Idea").tap();
  await card(page, "Idea", "Sunset projection lamp").getByRole("button", { name: /^Move/ }).tap();
  await page.getByRole("menuitem", { name: "Researching" }).tap();
  await expect(pick(page, "Researching")).toHaveAttribute("aria-pressed", "true");
  await expect(card(page, "Researching", "Sunset projection lamp")).toBeVisible();
  await expect(page.locator("#test-7")).toBeFocused();
  await expect(pick(page, "Idea")).toHaveAccessibleName("Idea, 0 tests");
  await toast(page).getByRole("button", { name: "Undo" }).tap();
  await expect(card(page, "Idea", "Sunset projection lamp")).toBeVisible();
  await expect(pick(page, "Idea")).toHaveAttribute("aria-pressed", "true");

  // Killed asks why first; one tap on a reason moves it.
  await card(page, "Idea", "Sunset projection lamp").getByRole("button", { name: /^Move/ }).tap();
  await page.getByRole("menuitem", { name: "Killed…" }).tap();
  await page.getByRole("dialog", { name: "Why kill Sunset projection lamp?" }).getByRole("button", { name: "Margin too thin" }).tap();
  await expect(card(page, "Killed", "Sunset projection lamp")).toBeVisible();
  await expect(pick(page, "Killed")).toHaveAttribute("aria-pressed", "true");
  expect(api.patches).toEqual([{ stage: "researching" }, { stage: "idea" }, { stage: "killed", kill_reason: "margin_too_thin" }]);
});

test("by keyboard at phone width: the picker, then a card's Move to… menu", async ({ page }) => {
  const api = await mockTestingApi(page);
  await page.goto("/testing");
  await pick(page, "Researching").focus();
  await page.keyboard.press("Enter");
  await expect(pick(page, "Researching")).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Tab"); // past the rest of the picker to the column's first card
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await expect(page.locator("#test-6")).toBeFocused(); // Magnetic car phone mount
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menuitem", { name: "Idea" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: "Testing" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(pick(page, "Testing")).toHaveAttribute("aria-pressed", "true");
  await expect(card(page, "Testing", "Magnetic car phone mount")).toBeVisible();
  await expect(page.locator("#test-6")).toBeFocused();
  expect(api.patches).toEqual([{ stage: "testing" }]);
});

test("the drawer is a full-height sheet that clears the notch and the home indicator", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" }); // measure the settled sheet, not its slide-in
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setSafeAreaInsetsOverride", { insets });
  await mockTestingApi(page);
  await page.goto("/testing");
  await card(page, "Testing", "Posture corrector brace").getByRole("button", { name: "Posture corrector brace", exact: true }).tap();
  const drawer = page.getByRole("dialog", { name: "Posture corrector brace" });
  await expect(drawer).toBeVisible();
  const geometry = await drawer.evaluate((el) => {
    const box = el.getBoundingClientRect();
    const close = el.querySelector("button:has(.sr-only)")!.getBoundingClientRect();
    const style = getComputedStyle(el);
    return { box: [box.x, box.y, box.width, box.height], closeTop: close.top, padding: [style.paddingTop, style.paddingBottom] };
  });
  expect(geometry).toEqual({ box: [0, 0, 375, 812], closeTop: 12 + insets.top, padding: [`${insets.top}px`, `${insets.bottom}px`] });
  await expect(drawer.getByLabel("Ad spend")).toHaveAttribute("inputmode", "decimal"); // the numeric keypad
  await drawer.getByRole("button", { name: "Close test" }).tap();
  await expect(drawer).toBeHidden();
});

test("the picker sticks flush under the notched top bar", async ({ page }) => {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setSafeAreaInsetsOverride", { insets });
  await mockTestingApi(page);
  await page.goto("/testing");
  await expect(card(page, "Testing", "LED strip lights")).toBeVisible();
  await page.evaluate(() => scrollTo(0, 900));
  const [bar, picker] = await Promise.all([page.getByRole("banner").boundingBox(), page.getByRole("group", { name: "Column" }).boundingBox()]);
  expect(bar!.height).toBe(56 + insets.top); // the notch adds to the bar, as it does to the tab bar
  expect(picker!.y).toBe(bar!.height + 8); // its strip's 8 px of padding, then the control
});

test("every control on the board, in a card's menu and in the drawer owns a 44 px hit area", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" }); // measure the settled menu and sheet, not their open animation
  await mockTestingApi(page);
  await page.goto("/testing");
  await expect(card(page, "Testing", "LED strip lights")).toBeVisible();
  expect(await smallTargets(page, "main")).toEqual([]);
  await card(page, "Testing", "LED strip lights").getByRole("button", { name: /^Move/ }).tap();
  await expect(page.getByRole("menu")).toBeVisible();
  expect(await smallTargets(page, "[role=menu]")).toEqual([]);
  await page.keyboard.press("Escape");
  await page.goto("/testing?test=9");
  await expect(page.getByRole("list", { name: "Changed inputs" })).toBeVisible();
  expect(await smallTargets(page, "[role=dialog]")).toEqual([]);
  expect(await pageScroll(page)).toBe(0);
});
