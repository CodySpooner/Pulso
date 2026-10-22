import { clerk, setupClerkTestingToken } from "@clerk/testing/playwright";
import { expect, test } from "@playwright/test";

// WEB-2 / CI-4: with the real auth gate, a signed-out visit to an app route lands on /sign-in, remembers
// where it was going, and Clerk's sign-in form loads.
test("a signed-out visit redirects to sign-in", async ({ page }) => {
  await setupClerkTestingToken({ page });
  await page.goto("/discover");

  await expect(page).toHaveURL(/\/sign-in/);
  expect(new URL(page.url()).searchParams.get("redirect_url")).toMatch(/\/discover$/);
  await clerk.loaded({ page });
  await expect(page.getByRole("heading", { level: 1, name: "Sign in to Pulso" })).toBeVisible();
});
