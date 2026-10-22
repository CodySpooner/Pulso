import { expect, test, type Page } from "@playwright/test";

// WEB-4: with prefers-reduced-motion emulated, no transform animation or transition runs (vault Design/
// Motion System, three layers). The same journey without the emulation must record motion, which proves
// the recorder would catch a regression.

declare global {
  interface Window {
    __transformMotion: string[];
  }
}

const TRANSFORM_PROPS = ["transform", "translate", "scale", "rotate"];

async function installRecorder(page: Page) {
  await page.addInitScript((props: string[]) => {
    window.__transformMotion = [];
    const isIdentity = (value: string) => {
      if (!value || value === "none") return true;
      try {
        return new DOMMatrix(value).isIdentity;
      } catch {
        return false;
      }
    };
    // CSS animations, CSS transitions and WAAPI animations (Motion's hardware-accelerated path).
    const poll = () => {
      for (const animation of document.getAnimations()) {
        const effect = animation.effect as KeyframeEffect | null;
        const duration = Number(effect?.getComputedTiming().duration ?? 0);
        const keys = (effect?.getKeyframes() ?? []).flatMap((frame) => Object.keys(frame));
        const transitionProperty = (animation as CSSTransition).transitionProperty;
        if (duration > 1 && (keys.some((k) => props.includes(k)) || props.includes(transitionProperty))) {
          window.__transformMotion.push(`${animation.constructor.name} ${transitionProperty ?? keys.join(",")} ${duration}ms`);
        }
      }
      requestAnimationFrame(poll);
    };
    requestAnimationFrame(poll);
    // Motion's JS-driven animations (springs, layout projection) write inline transforms frame by frame:
    // two or more distinct non-identity values on one element means it moved.
    const seen = new WeakMap<Element, Set<string>>();
    new MutationObserver((mutations) => {
      for (const { target } of mutations) {
        const value = (target as HTMLElement).style?.transform;
        if (!value || isIdentity(value)) continue;
        const values = seen.get(target as Element) ?? new Set<string>();
        values.add(value);
        seen.set(target as Element, values);
        if (values.size === 2) window.__transformMotion.push(`inline transform on <${(target as Element).tagName.toLowerCase()}>`);
      }
    }).observe(document, { attributes: true, attributeFilter: ["style"], subtree: true });
  }, TRANSFORM_PROPS);
}

/** Palette open → highlight move → close → three route changes (route enter, nav pill, card stagger) →
 *  the /admin/ui motion samples replayed and its range pill moved. */
async function journey(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Daily Pulse" })).toBeVisible();
  await page.waitForTimeout(500); // lazy Motion features load after first paint
  await page.keyboard.press("Control+K");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.waitForTimeout(400);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  const sidebar = page.getByRole("complementary");
  await sidebar.getByRole("link", { name: /^Discover/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Discover" })).toBeVisible();
  await page.waitForTimeout(400);
  await sidebar.getByRole("link", { name: /^Daily Pulse/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Daily Pulse" })).toBeVisible();
  await page.waitForTimeout(600);
  await sidebar.getByRole("link", { name: /^UI gallery/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: "UI gallery" })).toBeVisible();
  await page.getByRole("button", { name: "Replay motion" }).click();
  await page.getByRole("button", { name: "Month" }).click();
  await page.waitForTimeout(600);
  return page.evaluate(() => window.__transformMotion);
}

test("reduced motion: no transform animations or transitions run", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await installRecorder(page);
  expect(await journey(page)).toEqual([]);
});

test("control: the same journey animates transforms without reduced motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await installRecorder(page);
  const recorded = await journey(page);
  // Motion's WAAPI and JS paths (route enter, palette panel, shared pills), not just CSS keyframes.
  expect(recorded.some((entry) => entry.startsWith("Animation "))).toBe(true);
  expect(recorded.some((entry) => entry.startsWith("inline transform"))).toBe(true);
});
