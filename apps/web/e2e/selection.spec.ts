import { expect, test } from "@playwright/test";

// imp-063: selected text uses the --selection / --selection-foreground token pair in both themes, whatever
// the text's own colour (src/styles/contrast.test.ts checks the pair against AA).
for (const theme of ["dark", "light"] as const) {
  test(`::selection resolves to the selection tokens (${theme})`, async ({ page }) => {
    await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
    await page.goto("/admin/ui");
    await expect(page.locator("html")).toHaveClass(new RegExp(`\\b${theme}\\b`));
    const caption = page.getByText("Captions and hints"); // subtle text: the worst case before imp-063
    await caption.selectText();

    const { selected, tokens } = await caption.evaluate((el) => {
      const probe = document.createElement("span");
      probe.style.color = "var(--selection-foreground)";
      probe.style.backgroundColor = "var(--selection)";
      el.append(probe);
      const t = getComputedStyle(probe);
      const s = getComputedStyle(el, "::selection");
      const result = { selected: [s.color, s.backgroundColor], tokens: [t.color, t.backgroundColor] };
      probe.remove();
      return result;
    });
    expect(selected).toEqual(tokens);
    expect(tokens[0]).not.toBe(await caption.evaluate((el) => getComputedStyle(el).color)); // overrides the text colour
  });
}
