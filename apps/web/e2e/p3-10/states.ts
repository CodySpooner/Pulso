import { expect, type Page } from "@playwright/test";

import { aliexpress, mockAdminApi, sources } from "../data-health/fixtures";
import { product, PRODUCT_ID, unmatched } from "../products/fixtures";
import { empty, mockSellersApi, sellers } from "../products/sellers-fixtures";
import type { components } from "../../src/lib/api/schema";

// p3-10 (Phase 3 Q-2): the Phase 3 view × state cells this task fixes (DEC-302), driven through the existing fixtures
// (the E2E auth bypass, never a database restore) and asserted by role and text. states.spec.ts runs them on chromium
// at 1440 and 375; states-screenshots.spec.ts captures them. docs/reports/p3-10.md maps every other cell to its proof.

export interface State {
  name: string;
  url: string;
  setup: (page: Page) => Promise<unknown>;
  ready: (page: Page) => Promise<void>;
  /** What the screenshot centres on, when it isn't the top of the page. */
  focus?: (page: Page) => ReturnType<Page["locator"]>;
}

const SELLERS = `/products/${PRODUCT_ID}?tab=sellers`;
const IMPORT = "/admin/data-health#import";
const off = { status: "disabled" as const, since: null, reason: null }; // DEC-261: the store crawler never runs
/** The header agrees with the tab: no store has been seen, so stores and retail price have no source either. */
const noStores = { ...product, store_count: unmatched.store_count, price_min_minor: unmatched.price_min_minor, price_max_minor: unmatched.price_max_minor };
/** Source 8 as migration 0012 seeds it: CSV only, its row the flag and off (DEC-279), no file imported yet. */
export const amazon: components["schemas"]["SourceHealth"] = {
  ...aliexpress,
  key: "amazon",
  name: "Amazon",
  type: "csv",
  csv_import: "ready",
};
// The table holds the sources from 768px, cards below it.
const sourceRow = (page: Page, name: string, type: string) =>
  page.viewportSize()!.width < 768
    ? page.getByRole("listitem").filter({ hasText: `${name}${type}` })
    : page.getByRole("region", { name: "Sources table" }).getByRole("row", { name: new RegExp(`^${name}`) });

async function noSourcePage(page: Page, title: string) {
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 2, name: title })).toBeVisible();
  await expect(main).toContainText("The Shopify store crawler stays off");
  await expect(main).not.toContainText("arrives in Phase");
  await expect(main).not.toContainText("builds this page");
  await expect(main.getByRole("list", { name: "Build phases" })).toHaveCount(0);
  await expect(main.getByRole("link", { name: "Import a CSV in Data Health" })).toHaveAttribute("href", IMPORT);
}

export const STATES: State[] = [
  {
    name: "stores-no-source",
    url: "/stores",
    setup: async () => {},
    ready: (page) => noSourcePage(page, "Store Spy: no source yet"),
  },
  {
    name: "store-no-source",
    url: "/stores/northwind-home",
    setup: async () => {},
    ready: (page) => noSourcePage(page, "Store: no source yet"),
  },
  {
    name: "sellers-no-source",
    url: SELLERS,
    setup: async (page) => {
      await mockSellersApi(page, { body: { ...empty, crawler: off } });
      await page.route((url) => url.pathname === `/api/v1/products/${PRODUCT_ID}`, (route) => route.fulfill({ json: noStores }));
    },
    ready: async (page) => {
      const tab = page.getByRole("tabpanel");
      await expect(tab.getByRole("heading", { name: "Sellers: no source yet" })).toBeVisible();
      await expect(tab).toContainText("The Shopify store crawler stays off");
      await expect(tab.getByRole("link", { name: "Import a CSV in Data Health" })).toHaveAttribute("href", IMPORT);
      // Never an error and never 0: no paused warning, no summary strip of zeros, no tracked-store promise.
      await expect(tab).not.toContainText("paused");
      await expect(tab.getByRole("heading", { name: "Sellers", exact: true, level: 3 })).toHaveCount(0);
      await expect(tab).not.toContainText("No stores seen selling this yet");
    },
  },
  {
    name: "sellers-off-imported",
    url: SELLERS,
    setup: (page) => mockSellersApi(page, { body: { ...sellers, crawler: off } }),
    ready: async (page) => {
      const tab = page.getByRole("tabpanel");
      await expect(tab.getByRole("status").filter({ hasText: "Store crawler off" })).toContainText("sellers come only from your CSV imports");
      await expect(tab).not.toContainText("paused");
      await expect(tab).toContainText("nightsky-decor.com");
    },
  },
  {
    name: "data-health-amazon",
    url: "/admin/data-health",
    setup: (page) => mockAdminApi(page, { sources: [...sources, aliexpress, amazon] }),
    ready: async (page) => {
      const row = sourceRow(page, "Amazon", "CSV only");
      await expect(row.getByText("No import yet", { exact: true })).toBeVisible();
      // The phone card's switch label still says Disabled: the row is the source's flag (DEC-279), not its state.
      if (page.viewportSize()!.width >= 768) await expect(row).not.toContainText("Disabled");
      await expect(sourceRow(page, "AliExpress", "Official API")).toContainText("Disabled"); // pending the owner's app approval
    },
    focus: (page) => sourceRow(page, "Amazon", "CSV only"),
  },
];
