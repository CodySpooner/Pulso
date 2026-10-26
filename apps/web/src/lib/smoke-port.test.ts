import { afterEach, describe, expect, test, vi } from "vitest";

import { smokePort } from "../../e2e/smoke-port";

// The repo-root .env.local, faked: no env file is written (imp-599).
const envFile = vi.hoisted(() => ({ text: undefined as string | undefined }));
vi.mock("node:fs", () => ({
  existsSync: (file: string) => file.endsWith(".env.local") && envFile.text !== undefined,
  readFileSync: () => envFile.text,
}));

afterEach(() => {
  vi.unstubAllEnvs();
  envFile.text = undefined;
});

describe("smokePort", () => {
  test("a WEB_PORT env var wins over the repo-root .env.local", () => {
    vi.stubEnv("WEB_PORT", "3389");
    envFile.text = "WEB_PORT=3005\n";
    expect(smokePort(100)).toBe(3489);
  });

  test("the .env.local WEB_PORT wins over the default", () => {
    vi.stubEnv("WEB_PORT", undefined);
    envFile.text = "API_PORT=8005\nWEB_PORT=3005\n";
    expect(smokePort(100)).toBe(3105);
    expect(smokePort(200)).toBe(3205);
  });

  test("with neither, the base is 3000 (the main checkout and CI)", () => {
    vi.stubEnv("WEB_PORT", undefined);
    expect(smokePort(100)).toBe(3100);
    envFile.text = "API_PORT=8005\n";
    expect(smokePort(100)).toBe(3100);
  });

  test("a test worker evaluating the config again gets the same port, never offset twice", () => {
    // Workers fork with the runner's env, not the webServer env that sets WEB_PORT to the final port, so they
    // see the same WEB_PORT the runner did, as long as smokePort leaves process.env alone.
    vi.stubEnv("WEB_PORT", "3389");
    const runner = smokePort(100);
    expect(process.env.WEB_PORT).toBe("3389");
    expect(smokePort(100)).toBe(runner);
    expect(runner).toBe(3489);
  });
});
