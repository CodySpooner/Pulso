import { expect, test, type Locator, type Page } from "@playwright/test";

// F-02 (imp-033): CopyButton on the /admin/ui ErrorState specimen. A denied or missing clipboard says
// "Couldn’t copy" without an unhandled rejection, and the button stays usable to retry. imp-041: the failure
// also says what to do next, in a tooltip that opens by itself and in the live announcement.

const ERROR_ID = "2950841734"; // the specimen's digest, admin/ui/samples.tsx
const HINT = "Select the ID to copy it.";

async function openSpecimen(page: Page) {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("/admin/ui");
  // The button's name follows its label, so match every state.
  const button = page.getByRole("button", { name: /^(Copy error ID|Copied|Couldn’t copy)/ });
  await expect(button).toHaveText("Copy error ID");
  return { button, pageErrors };
}

async function expectFailed(page: Page, button: Locator) {
  await expect(button).toHaveText(`Couldn’t copy. ${HINT}`); // the sentence after the label is sr-only
  await expect(button).toHaveAccessibleDescription(HINT);
  await expect(page.getByRole("tooltip")).toHaveText(HINT);
}

test("copies the error ID and confirms", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const { button, pageErrors } = await openSpecimen(page);
  await button.click();
  await expect(button).toHaveText("Copied");
  await expect(page.getByRole("tooltip")).toHaveCount(0);
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(ERROR_ID);
  await expect(button).toHaveText("Copy error ID");
  expect(pageErrors).toEqual([]);
});

test("a denied write says so and what to do next, keeps focus and can be retried from the keyboard", async ({ page }) => {
  await page.addInitScript(() => {
    const w = window as unknown as { writes: number };
    w.writes = 0;
    navigator.clipboard.writeText = () => {
      w.writes++;
      return Promise.reject(new DOMException("Write permission denied.", "NotAllowedError"));
    };
  });
  const { button, pageErrors } = await openSpecimen(page);
  await button.focus();
  await page.keyboard.press("Enter");
  await expectFailed(page, button);
  await expect(button).toBeFocused();
  expect(await button.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");

  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => (window as unknown as { writes: number }).writes)).toBe(2);
  await expectFailed(page, button);
  await expect(button).toHaveText("Copy error ID", { timeout: 6_000 });
  await expect(page.getByRole("tooltip")).toHaveCount(0);

  // Esc dismisses the hint at once and leaves focus on the button.
  await page.keyboard.press("Enter");
  await expectFailed(page, button);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("tooltip")).toHaveCount(0);
  await expect(button).toHaveText("Copy error ID");
  await expect(button).toBeFocused();
  expect(pageErrors).toEqual([]);
});

test("a browser without the clipboard API says so and what to do next", async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(Navigator.prototype, "clipboard", { get: () => undefined }));
  const { button, pageErrors } = await openSpecimen(page);
  await button.click();
  await expectFailed(page, button);
  expect(pageErrors).toEqual([]);
});
