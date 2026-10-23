import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockAdminApi } from "./data-health/fixtures";

// F-02 (imp-033): CopyButton on the /admin/ui ErrorState specimen. A denied or missing clipboard says
// "Couldn’t copy" without an unhandled rejection, and the button stays usable to retry. imp-041: the failure
// also says what to do next, in a tooltip that opens by itself and in the live announcement. imp-044: it says
// why and stays 5 s; imp-043: that next step, selecting the ID, is one click; imp-062: or one focus from the
// keyboard, then Ctrl/⌘+C copies it without the clipboard API.

const ERROR_ID = "2950841734"; // the specimen's digest, admin/ui/samples.tsx
const HINT = "The clipboard isn’t available here.\nSelect the ID to copy it."; // a line each in the tooltip
const noClipboard = () => Object.defineProperty(Navigator.prototype, "clipboard", { get: () => undefined });
const denyWrites = () => {
  navigator.clipboard.writeText = () => Promise.reject(new DOMException("Write permission denied.", "NotAllowedError"));
};
const selection = (page: Page) => page.evaluate(() => getSelection()?.toString());

async function openSpecimen(page: Page) {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("/admin/ui");
  // The button's name follows its label, so match every state.
  const button = page.getByRole("button", { name: /^(Copy error ID|Copied|Couldn’t copy)/ });
  await expect(button).toHaveText("Copy error ID");
  return { button, pageErrors };
}

// From a failed Copy button: Shift+Tab past Retry to the ID, which keyboard focus selects whole with a visible
// ring; the browser's own copy then works although the clipboard API refused the write.
async function expectKeyboardCopy(page: Page, value: string) {
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Shift+Tab");
  const id = page.getByRole("textbox", { name: "Error ID" });
  await expect(id).toBeFocused();
  await expect(id).toHaveText(value);
  expect(await id.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
  expect(await selection(page)).toBe(value);
  await page.keyboard.press("ControlOrMeta+C");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(value);
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
  await expect(button).toHaveText("Copy error ID", { timeout: 7_000 });
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
  await page.addInitScript(noClipboard);
  const { button, pageErrors } = await openSpecimen(page);
  await button.click();
  await expectFailed(page, button);
  expect(pageErrors).toEqual([]);
});

test("the failure stays for its 5 s reading budget, then the label returns", async ({ page }) => {
  await page.clock.install();
  await page.addInitScript(noClipboard);
  const { button, pageErrors } = await openSpecimen(page);
  await page.clock.pauseAt(await page.evaluate(() => Date.now() + 1_000));
  await button.click();
  await expectFailed(page, button);
  await page.clock.runFor(4_999);
  await expectFailed(page, button);
  await page.clock.runFor(1);
  await expect(button).toHaveText("Copy error ID");
  await expect(page.getByRole("tooltip")).toHaveCount(0);
  expect(pageErrors).toEqual([]);
});

test("after a failed copy, one click selects the whole error ID", async ({ page }) => {
  await page.addInitScript(noClipboard);
  const { button, pageErrors } = await openSpecimen(page);
  await button.click();
  await expectFailed(page, button);
  await page.getByText(ERROR_ID, { exact: true }).click();
  expect(await selection(page)).toBe(ERROR_ID);
  expect(pageErrors).toEqual([]);
});

const requestId = "req-7f3a9c";

async function openCoverageError(page: Page) {
  await mockAdminApi(page);
  await page.route("**/api/v1/admin/coverage*", (route) =>
    route.fulfill({
      status: 503,
      json: { type: "about:blank", title: "Service Unavailable", status: 503, code: "unavailable", detail: "The API is restarting.", request_id: requestId, errors: [] },
    }),
  );
  await page.goto("/admin/data-health");
  await expect(page.getByRole("heading", { name: "Couldn't load coverage" })).toBeVisible({ timeout: 15_000 });
}

test("one click selects a Data Health panel's error ID", async ({ page }) => {
  await openCoverageError(page);
  await page.getByText(requestId, { exact: true }).click();
  expect(await selection(page)).toBe(requestId);
});

test("after a denied copy, the keyboard selects the error ID and Ctrl+C copies it", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.addInitScript(denyWrites);
  const { button, pageErrors } = await openSpecimen(page);
  await button.focus();
  await page.keyboard.press("Enter");
  await expectFailed(page, button);
  await expectKeyboardCopy(page, ERROR_ID);
  expect(pageErrors).toEqual([]);
});

test("the keyboard selects and copies a Data Health panel's error ID after a denied copy", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.addInitScript(denyWrites);
  await openCoverageError(page);
  const button = page.getByRole("button", { name: /^(Copy error ID|Copied|Couldn’t copy)/ });
  await button.focus();
  await page.keyboard.press("Enter");
  await expectFailed(page, button);
  await expectKeyboardCopy(page, requestId);
});
