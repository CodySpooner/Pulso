import { expect, test } from "@playwright/test";

// WEB-5: Ctrl+K opens the palette, arrows + Enter navigate, Esc closes and focus returns.
test.describe("command palette", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
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
    await expect(page.getByText("Discover arrives in Phase 2")).toBeVisible();
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
// and the ring sits inside the dialog, so overflow-hidden can't clip it.
const ringCases = [
  ...(["dark", "light"] as const).flatMap((theme) => [1440, 375].map((width) => ({ theme, width, forced: false }))),
  { theme: "dark" as const, width: 1440, forced: true }, // forced colors repaint the ring in a system colour
];
for (const { theme, width, forced } of ringCases) {
  test(`the focused palette input shows the focus ring: ${theme} ${width}px${forced ? " forced colors" : ""}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce", forcedColors: forced ? "active" : "none" });
    await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
    await page.goto("/");
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
        const box = el.closest('[role="dialog"]')!.getBoundingClientRect();
        return {
          style: s.outlineStyle,
          thick: parseFloat(s.outlineWidth) >= 2,
          token: forced || s.outlineColor === token,
          inside: r.top - reach >= box.top && r.bottom + reach <= box.bottom && r.left - reach >= box.left && r.right + reach <= box.right,
        };
      }, forced);
    await expect.poll(ring).toEqual({ style: "solid", thick: true, token: true, inside: true });
  });
}

test("the whole shell is reachable by keyboard: skip link first", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
});
