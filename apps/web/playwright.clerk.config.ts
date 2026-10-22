import { defineConfig, devices } from "@playwright/test";

import { smokePort } from "./e2e/smoke-port";

const PORT = smokePort(200);

// CI-4: `pnpm --filter web e2e:clerk` drives `next dev` with the real Clerk dev instance (no E2E bypass) and
// Clerk testing tokens. It needs CLERK_SECRET_KEY and NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY, from the environment
// or apps/web/.env.local. A separate run from `pnpm e2e`: Next allows one `next dev` per app directory.
export default defineConfig({
  testDir: "e2e/clerk",
  globalSetup: "./e2e/clerk/global-setup.ts",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: { ...devices["Desktop Chrome"], baseURL: `http://localhost:${PORT}`, trace: "retain-on-failure" },
  webServer: {
    command: "node scripts/dev.mjs",
    url: `http://localhost:${PORT}/sign-in`,
    timeout: 180_000,
    reuseExistingServer: false, // see playwright.config.ts
    env: { WEB_PORT: String(PORT), NEXT_PUBLIC_CLERK_SIGN_IN_URL: "/sign-in", NEXT_PUBLIC_CLERK_KEYLESS_DISABLED: "1" },
  },
});
