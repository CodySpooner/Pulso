import type { Page } from "@playwright/test";

import { mockAlertsApi } from "../alerts/fixtures";
import { problem } from "../data-health/fixtures";
import { LATEST, pulse, type Pulse } from "./data";

export { LATEST, nothing, pulse, withStatus } from "./data";

const IMAGE = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="24" height="24" fill="#2a2f36"/><circle cx="12" cy="11" r="6" fill="#16c96f" opacity=".75"/><rect x="5" y="18" width="14" height="2" rx="1" fill="#878f9b"/></svg>`;

export interface PulseMock {
  /** The response for a day; `null` is a request without ?date=. Defaults to the fixture day (LATEST when absent). */
  day?: (date: string | null) => Pulse;
  /** GET /v1/pulse never answers: the skeletons stay. */
  hold?: boolean;
  /** GET /v1/pulse answers with this problem status; read per request, so a test can change it. */
  status?: number;
}

/** Answers /api/v1/pulse from the fixtures and records each request's date; the shell, the bell and /alerts run on the
 *  alerts fixtures (with Data Health's NOW pinned). Call before page.goto. */
export async function mockPulseApi(page: Page, options: PulseMock = {}) {
  const dates: (string | null)[] = [];
  await mockAlertsApi(page);
  await page.route("https://cdn.example.test/**", (route) => route.fulfill({ contentType: "image/svg+xml", body: IMAGE }));
  await page.route("**/api/v1/pulse**", (route) => {
    const date = new URL(route.request().url()).searchParams.get("date");
    dates.push(date);
    if (options.hold) return;
    if (options.status) return route.fulfill({ status: options.status, contentType: "application/problem+json", json: problem(options.status, "e2e-pulse") });
    return route.fulfill({ json: (options.day ?? ((d) => pulse(d ?? LATEST)))(date) });
  });
  return { dates };
}
