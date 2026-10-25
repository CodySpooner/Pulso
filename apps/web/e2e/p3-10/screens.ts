import { expect, type Page } from "@playwright/test";

import { mockAmazonApi } from "../amazon/fixtures";
import type { Screen } from "../p2-39/screens";
import { found, LIVE, mockAliExpressApi } from "../products/aliexpress-fixtures";
import { mockProductAmazonApi, noImport } from "../products/amazon-fixtures";
import { mockProductApi, PRODUCT_ID } from "../products/fixtures";
import { STATES } from "./states";

// p3-10 (Phase 3 Q-2): every Phase 3 screen, loaded and in the Q-2 states (AliExpress pending approval, Amazon no
// import yet, the store views with no source), from fixtures only (the E2E auth bypass, never a database restore).
// phase-end.spec.ts runs on each the AGENTS.md §8 checks a browser can measure, with p2-39's probes.

const PRODUCT = `/products/${PRODUCT_ID}`;
const settled = (page: Page) => expect(page.locator(".bg-skeleton:visible")).toHaveCount(0);
const ranks = (page: Page) => page.getByRole("region", { name: "Amazon ranks" });
const aliexpressSection = (page: Page) => page.getByRole("region", { name: "AliExpress", exact: true });

export const SCREENS: Screen[] = [
  {
    name: "amazon-ranks",
    scope: "main",
    open: async (page) => {
      await mockAmazonApi(page);
      await page.goto("/amazon");
      await expect(page.getByRole("main").getByText(/^Amazon · manual import, as of Oct 21, 2026/)).toBeVisible();
      await settled(page);
    },
  },
  {
    name: "amazon-no-import",
    scope: "main",
    open: async (page) => {
      await mockAmazonApi(page, { empty: true });
      await page.goto("/amazon");
      await expect(page.getByRole("heading", { name: "No Amazon import yet" })).toBeVisible();
    },
  },
  {
    name: "product-trends-phase-3", // Search keywords (KW-1, KW-2) and Amazon ranks (AMZ-1c)
    scope: "main",
    open: async (page) => {
      await mockProductApi(page);
      await mockProductAmazonApi(page);
      await page.goto(`${PRODUCT}?tab=trends`);
      await expect(ranks(page).getByText("Amazon · manual import, as of Oct 21, 2026")).toBeVisible();
      await expect(page.getByRole("region", { name: "Search keywords" })).toBeVisible();
      await settled(page);
    },
  },
  {
    name: "trends-amazon-no-import",
    scope: "main",
    open: async (page) => {
      await mockProductApi(page);
      await mockProductAmazonApi(page, { body: noImport });
      await page.goto(`${PRODUCT}?tab=trends`);
      await expect(ranks(page).getByText("No Amazon import yet.")).toBeVisible();
      await settled(page);
    },
  },
  {
    name: "suppliers-aliexpress",
    scope: "main",
    open: async (page) => {
      await mockAliExpressApi(page, [found]);
      await page.goto(`${PRODUCT}?tab=suppliers`);
      await expect(page.getByLabel("AliExpress variants").filter({ visible: true }).getByText(LIVE).first()).toBeVisible(); // a table from 768 px, cards below
      await settled(page);
    },
  },
  {
    name: "suppliers-aliexpress-off",
    scope: "main",
    open: async (page) => {
      await mockAliExpressApi(page, [{ status: "disabled" }]);
      await page.goto(`${PRODUCT}?tab=suppliers`);
      await expect(aliexpressSection(page).getByRole("heading", { name: "AliExpress is off: needs the owner's app approval" })).toBeVisible();
      await settled(page);
    },
  },
  // p3-12 (Phase 3 end): the coming-soon page once CURRENT_PHASE is 4, for a Phase 4 page and a later one.
  ...([
    ["coming-soon-phase-4", "/screener", "Screener arrives in Phase 4"],
    ["coming-soon-later", "/ask", "Ask Pulso arrives in Phase 5"],
  ] as const).map(
    ([name, url, heading]): Screen => ({
      name,
      scope: "main",
      open: async (page) => {
        await page.goto(url);
        await expect(page.getByRole("heading", { name: heading })).toBeVisible();
      },
    }),
  ),
  // The store views Shopify being off keeps at 'no source yet' (DEC-261), the Sellers tab with CSV rows, and Data
  // Health's AliExpress (off, pending approval) and Amazon (no import yet) rows.
  ...STATES.map(
    (s): Screen => ({
      name: s.name,
      scope: "main",
      open: async (page) => {
        await s.setup(page);
        await page.goto(s.url);
        await s.ready(page);
      },
    }),
  ),
];
