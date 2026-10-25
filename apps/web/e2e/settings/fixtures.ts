import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { healthySources, mockAdminApi, problem } from "../data-health/fixtures";

// Fixture GET / PATCH /v1/settings responses for the Settings e2e tests and screenshots, never a database restore.

type S = components["schemas"];

/** A fresh workspace: the table defaults, every rate 0 and duty not set. */
export const firstRun: S["SettingsResponse"] = {
  workspace_id: "5d0e7a8c-1b2f-4c3d-9e8f-7a6b5c4d3e2f",
  default_country: "US",
  currency: "USD",
  payment_fee_bps: 0,
  payment_fee_fixed_minor: 0,
  shopify_fee_bps: 0,
  default_cpa_minor: 0,
  target_margin_bps: 0,
  duty_default_bps: null,
  returns_bps: 0,
  customs_fee_minor: 0,
};

/** The owner's numbers: 2.9% + $0.30 processing, $15 CPA, 20% target, 15% duty, 5% refunds, $1.50 import fee. */
export const configured: S["SettingsResponse"] = {
  ...firstRun,
  payment_fee_bps: 290,
  payment_fee_fixed_minor: 30,
  default_cpa_minor: 1500,
  target_margin_bps: 2000,
  duty_default_bps: 1500,
  returns_bps: 500,
  customs_fee_minor: 150,
};

export interface SettingsMock {
  settings?: S["SettingsResponse"];
  /** GET never answers: the loading skeleton stays. */
  hold?: boolean;
  /** GET answers with this problem status. */
  status?: number;
  /** PATCH answers 503. */
  failSaves?: boolean;
  /** PATCH answers this 422 problem's `errors`. */
  rejectSaves?: Record<string, unknown>[];
}

/** The shell's admin calls plus GET / PATCH /v1/settings, which keeps what a PATCH saves, like the API. Returns the
 *  PATCH bodies and a switch that makes later GETs fail (a refetch failing while the form shows saved data). */
export async function mockSettingsApi(page: Page, options: SettingsMock = {}) {
  const patches: Record<string, unknown>[] = [];
  let current = { ...(options.settings ?? configured) };
  let getStatus = options.status;
  await mockAdminApi(page, { sources: healthySources });
  await page.route("**/api/v1/settings", async (route) => {
    const request = route.request();
    const fail = (status: number, id: string, errors: Record<string, unknown>[] = []) =>
      route.fulfill({ status, contentType: "application/problem+json", json: { ...problem(status, id), errors } });
    if (request.method() === "PATCH") {
      const body = request.postDataJSON() as Record<string, unknown>;
      patches.push(body);
      if (options.failSaves) return fail(503, "e2e-settings-save");
      if (options.rejectSaves)
        return route.fulfill({
          status: 422,
          contentType: "application/problem+json",
          json: { ...problem(422, "e2e-settings-422"), title: "Unprocessable Content", code: "validation_error", detail: "Invalid request.", errors: options.rejectSaves },
        });
      current = { ...current, ...body };
      return route.fulfill({ json: current });
    }
    if (options.hold) return;
    if (getStatus) return fail(getStatus, `e2e-settings-${getStatus}`);
    return route.fulfill({ json: current });
  });
  return { patches, failGets: (status = 503) => (getStatus = status) };
}

/** Makes the page refetch its stale queries, as when the tab becomes visible again (react-query listens on window). */
export async function refocus(page: Page) {
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
}
