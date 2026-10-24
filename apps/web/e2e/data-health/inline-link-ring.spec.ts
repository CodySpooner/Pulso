import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi, problem } from "./fixtures";

// imp-169: the global focus ring (2 px outline at 2 px offset) reaches 4 px past a control, more than the space
// beside an inline link, so the ring of "Collector host card" met "the" before it and "." after it. An inline link
// (`link-inline`) keeps a gap to the words either side; a Button and the other controls keep today's ring.

/** The host call answers 503, so the Open gaps line carries the "Collector host card" link (imp-159). */
async function load(page: Page, width: number) {
  await mockAdminApi(page);
  await page.route(
    (url) => url.pathname === "/api/v1/admin/host",
    (route) => route.fulfill({ status: 503, json: problem(503, "req_host_503") }),
  );
  await page.setViewportSize({ width, height: width < 1024 ? 812 : 900 });
  await page.goto("/admin/data-health");
}

for (const width of [1440, 375]) {
  test(`inline link at ${width}px: its focus ring keeps a gap to the words either side`, async ({ page }) => {
    await load(page, width);
    const link = page.getByRole("region", { name: "Coverage", exact: true }).getByRole("link", { name: "Collector host card" });
    await expect(link).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await link.focus();
    const measured = await link.evaluate((el) => {
      const box = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      const reach = parseFloat(style.outlineOffset) + parseFloat(style.outlineWidth);
      const ring = { left: box.left - reach, right: box.right + reach, top: box.top - reach, bottom: box.bottom + reach };
      const word = (node: Node, from: number, to: number) => {
        const range = document.createRange();
        range.setStart(node, from);
        range.setEnd(node, to);
        return { text: range.toString(), box: range.getBoundingClientRect() };
      };
      // How far apart the ring and a word's box are, on the axis that separates them; negative when they overlap.
      const gap = ({ box: w }: { box: DOMRect }) => Math.max(w.left - ring.right, ring.left - w.right, w.top - ring.bottom, ring.top - w.bottom);
      const before = el.previousSibling as Text;
      const end = before.data.trimEnd().length;
      const [the, period] = [word(before, end - 3, end), word(el.nextSibling!, 0, 1)];
      return { focusVisible: el.matches(":focus-visible"), words: [the.text, period.text], gaps: [gap(the), gap(period)] };
    });
    expect(measured.focusVisible).toBe(true);
    expect(measured.words).toEqual(["the", "."]);
    expect(measured.gaps[0], "ring to 'the'").toBeGreaterThanOrEqual(1);
    expect(measured.gaps[1], "ring to '.'").toBeGreaterThanOrEqual(1);
  });
}

test("a Button and the source picker keep today's ring", async ({ page }) => {
  await load(page, 1440);
  const controls = [
    page.getByRole("region", { name: "Collector host" }).getByRole("button", { name: "Retry" }),
    page.getByRole("region", { name: "CSV import" }).getByRole("combobox"),
  ];
  for (const control of controls) {
    await control.focus();
    const ring = await control.evaluate((el) => {
      const style = getComputedStyle(el);
      return { focusVisible: el.matches(":focus-visible"), style: style.outlineStyle, width: style.outlineWidth, offset: style.outlineOffset, margin: style.marginInline };
    });
    expect(ring).toEqual({ focusVisible: true, style: "solid", width: "2px", offset: "2px", margin: "0px" });
  }
});
