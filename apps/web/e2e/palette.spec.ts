import { expect, test } from "@playwright/test";

// WEB-5: Ctrl+K opens the palette, arrows + Enter navigate, Esc closes and focus returns.
test.describe("command palette", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("data-app-ready", "true");
    await expect(page.getByRole("heading", { level: 1, name: "Daily Pulse" })).toBeVisible();
  });

  test("Ctrl+K opens it and Esc closes it, returning focus to the trigger", async ({ page }) => {
    const trigger = page.getByRole("button", { name: /search or run a command/i });
    await trigger.focus();
    await page.keyboard.press("Control+K");

    const dialog = page.getByRole("dialog", { name: "Command palette" });
    await expect(dialog).toBeVisible();
    await expect(page.getByRole("combobox")).toBeFocused();

    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("Esc clears the query first, then closes", async ({ page }) => {
    await page.keyboard.press("Control+K");
    const input = page.getByRole("combobox");
    await input.fill("screen");
    await page.keyboard.press("Escape");
    await expect(input).toHaveValue("");
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
  });

  test("arrow keys and Enter navigate to a route and focus its heading", async ({ page }) => {
    await page.keyboard.press("Control+K");
    const options = page.getByRole("option");
    // The disabled search row is skipped, so the first selection is Daily Pulse.
    await expect(options.filter({ hasText: "Daily Pulse" })).toHaveAttribute("aria-selected", "true");

    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowDown");
    await expect(options.filter({ hasText: "Discover" })).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("ArrowUp");
    await expect(options.filter({ hasText: "Alerts" })).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");

    await expect(page).toHaveURL(/\/discover$/);
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(page.getByRole("heading", { level: 1, name: "Discover" })).toBeFocused();
    await expect(page.getByText("Products across your sources.")).toBeVisible(); // built in UX-2 (p2-03)
  });

  test("typing filters the commands", async ({ page }) => {
    await page.keyboard.press("Control+K");
    await page.getByRole("combobox").fill("data health");
    await expect(page.getByRole("option", { name: /Data Health/ })).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/admin\/data-health$/);
  });
});

// A11Y-01 (imp-025): the focused palette input shows the token focus ring (2px solid --ring, globals.css),
// and the ring sits inside the dialog, so overflow-hidden can't clip it. imp-040: the ring lines up with the
// row highlight (same height, gutters and radius; the highlight fills its row) and encloses the search icon.
const ringCases = [
  ...(["dark", "light"] as const).flatMap((theme) => [1440, 375].map((width) => ({ theme, width, forced: false, touch: false }))),
  { theme: "dark" as const, width: 1440, forced: true, touch: false }, // forced colors repaint the ring in a system colour
  { theme: "dark" as const, width: 375, forced: false, touch: true }, // touch rows and input are 44px (imp-026)
];
for (const { theme, width, forced, touch } of ringCases) {
  test.describe(() => {
    test.use({ hasTouch: touch });
    test(`the focused palette input shows the focus ring: ${theme} ${width}px${forced ? " forced colors" : ""}${touch ? " touch" : ""}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce", forcedColors: forced ? "active" : "none" });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/");
      await expect(page.locator("html")).toHaveAttribute("data-app-ready", "true");
      await expect(page.getByRole("heading", { level: 1, name: "Daily Pulse" })).toBeVisible();
      await page.keyboard.press("Control+K");
      const input = page.getByRole("combobox");
      await expect(input).toBeFocused();

      const ring = () =>
        input.evaluate((el, forced) => {
          const probe = document.body.appendChild(document.createElement("i"));
          probe.style.color = "var(--ring)";
          const token = getComputedStyle(probe).color;
          probe.remove();
          const s = getComputedStyle(el);
          const reach = parseFloat(s.outlineOffset) + parseFloat(s.outlineWidth);
          const r = el.getBoundingClientRect();
          const outer = { top: r.top - reach, bottom: r.bottom + reach, left: r.left - reach, right: r.right + reach };
          const dialog = el.closest('[role="dialog"]')!;
          const box = dialog.getBoundingClientRect();
          const row = dialog.querySelector('[role="option"][aria-selected="true"]')!;
          const highlight = row.getBoundingClientRect();
          const icon = el.parentElement!.querySelector("svg")!.getBoundingClientRect();
          const same = (a: number, b: number) => Math.abs(a - b) < 0.5;
          return {
            style: s.outlineStyle,
            thick: parseFloat(s.outlineWidth) >= 2,
            token: forced || s.outlineColor === token,
            inside: outer.top >= box.top && outer.bottom <= box.bottom && outer.left >= box.left && outer.right <= box.right,
            rowHeight: same(outer.bottom - outer.top, highlight.height),
            rowInset: same(outer.left, highlight.left) && same(outer.right, highlight.right),
            rowRadius: s.borderRadius === getComputedStyle(row).borderRadius,
            iconInside: icon.left >= outer.left + 2 && icon.right <= outer.right - 2 && icon.top >= outer.top + 2 && icon.bottom <= outer.bottom - 2,
          };
        }, forced);
      await expect.poll(ring).toEqual({ style: "solid", thick: true, token: true, inside: true, rowHeight: true, rowInset: true, rowRadius: true, iconInside: true });
    });
  });
}

test("the whole shell is reachable by keyboard: skip link first", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-app-ready", "true");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
});
