import { defineConfig, devices } from "@playwright/test";

const PORT = 3199;

// Smoke tests drive `next dev` with the E2E auth bypass (src/lib/auth.ts): Clerk keys don't exist yet, and
// a production build ignores the bypass. e2e/clerk runs against real Clerk: playwright.clerk.config.ts (CI-4).
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: { baseURL: `http://localhost:${PORT}`, trace: "retain-on-failure" },
  projects: [
    { name: "chromium", testIgnore: /screenshots|clerk/, use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    // `pnpm --filter web e2e:screenshots` writes docs/screenshots/phase-0/*.png for owner review.
    { name: "screenshots", testMatch: /screenshots/, use: { ...devices["Desktop Chrome"], reducedMotion: "reduce" } },
  ],
  webServer: {
    command: "node scripts/dev.mjs",
    url: `http://localhost:${PORT}`,
    timeout: 180_000,
    reuseExistingServer: !process.env.CI,
    env: { WEB_PORT: String(PORT), NEXT_PUBLIC_PULSO_E2E_AUTH_BYPASS: "1", NEXT_PUBLIC_CLERK_KEYLESS_DISABLED: "1" },
  },
});
