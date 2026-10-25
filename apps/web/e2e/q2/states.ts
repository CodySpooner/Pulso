import { expect, type Page } from "@playwright/test";

import { mockFeedApi, mockProductApi, PRODUCT_ID } from "../products/fixtures";
import { mockProfitApi } from "../products/profit-fixtures";
import { mockSellersApi } from "../products/sellers-fixtures";

// p2-30 (Q-2): the Phase 2 view × state cells no earlier spec proved, driven through the existing fixtures (the E2E
// auth bypass, never a database restore) and asserted by role and text. states.spec.ts runs them on chromium at 1440
// and 375; states-screenshots.spec.ts captures them. docs/reports/p2-30.md maps every cell to the test that proves it.

export interface State {
  name: string;
  url: string;
  setup: (page: Page) => Promise<unknown>;
  ready: (page: Page) => Promise<void>;
  /** An earlier task's screenshot of this state; the change here is screen-reader only, so it isn't captured again. */
  seenIn?: string;
}

const PRODUCT = `/products/${PRODUCT_ID}`;
const STALE_SINCE = "2026-10-19T12:00:00Z"; // the fixtures' stale Shopify capture, 74h before NOW
const staleShopify = [{ source: "shopify_stores", source_name: "Shopify stores", state: "stale" as const, since: STALE_SINCE }];
const loading = (page: Page, text: string) => expect(page.getByRole("status").filter({ hasText: text })).toBeAttached();
const view = (page: Page, name: "Grid" | "Table") => expect(page.getByRole("button", { name, exact: true })).toHaveAttribute("aria-pressed", "true");
const feedRow = (page: Page, title: string) => page.getByRole("region", { name: "Products" }).getByRole("row").filter({ hasText: title });
const staleBanner = (page: Page) => expect(page.getByRole("main")).toContainText("Shopify stores stale, last captured Oct 19, 12:00 UTC");
// The table holds the sellers from 768px, cards below it.
const sellerRow = (page: Page, domain: string) =>
  (page.viewportSize()!.width < 768 ? page.getByRole("list", { name: "Sellers" }).getByRole("listitem") : page.getByRole("region", { name: "Sellers" }).getByRole("row")).filter({
    hasText: domain,
  });

export const STATES: State[] = [
  {
    name: "discover-table-loading",
    url: "/discover?view=table",
    setup: (page) => mockFeedApi(page, { hold: true }),
    ready: async (page) => {
      await view(page, "Table");
      await loading(page, "Loading products…");
      await expect(page.locator(".bg-skeleton:visible").first()).toBeVisible();
    },
  },
  {
    name: "discover-table-empty",
    url: "/discover?view=table",
    setup: (page) => mockFeedApi(page, { items: [] }),
    ready: async (page) => {
      await view(page, "Table");
      await expect(page.getByRole("heading", { name: "No products collected yet" })).toBeVisible();
      await expect(page.getByRole("main").getByRole("link", { name: "Open Data Health" })).toHaveAttribute("href", "/admin/data-health");
    },
  },
  {
    name: "discover-table-error",
    url: "/discover?view=table",
    setup: (page) => mockFeedApi(page, { status: 503 }),
    ready: async (page) => {
      await view(page, "Table");
      await expect(page.getByRole("heading", { name: "Couldn't load products" })).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText("e2e-feed-503").first()).toBeVisible();
      await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
    },
  },
  {
    name: "discover-table-stale",
    url: "/discover?view=table",
    setup: (page) => mockFeedApi(page, { degraded: staleShopify }),
    ready: async (page) => {
      await staleBanner(page);
      await expect(page.getByText(/^20 products · as of Oct 22, 08:00 UTC$/)).toBeVisible();
      await expect(feedRow(page, "Facial ice roller")).toContainText("3d ago· stale");
      await expect(feedRow(page, "Facial ice roller").locator("time[title]").last()).toHaveAttribute("title", "Oldest data on this product: Oct 19, 12:00 UTC");
    },
  },
  {
    name: "discover-table-no-source",
    url: "/discover?view=table",
    setup: (page) => mockFeedApi(page),
    ready: async (page) => {
      const noStores = feedRow(page, "Mini waffle maker");
      await expect(noStores.getByRole("button", { name: "Retail price: No source yet" })).toHaveText("No source yet");
      await expect(noStores.getByRole("button", { name: "Stores selling it: No source yet" })).toHaveText("No source yet");
      await expect(feedRow(page, "Cloud pillow slides").getByRole("button", { name: "Velocity: Insufficient signal" })).toBeVisible();
    },
  },
  {
    name: "discover-grid-loading",
    url: "/discover?view=grid",
    setup: (page) => mockFeedApi(page, { hold: true }),
    ready: async (page) => {
      await view(page, "Grid");
      await loading(page, "Loading products…");
    },
    seenIn: "p2-03/loading",
  },
  {
    name: "discover-grid-stale",
    url: "/discover?view=grid",
    setup: (page) => mockFeedApi(page, { degraded: staleShopify }),
    ready: async (page) => {
      await staleBanner(page);
      const card = page.getByRole("list", { name: "Products" }).getByRole("article").filter({ hasText: "Facial ice roller" });
      await expect(card).toContainText("3d ago· stale");
    },
  },
  {
    name: "product-loading",
    url: PRODUCT,
    setup: (page) => mockProductApi(page, { hold: true }),
    ready: (page) => expect(page.getByRole("heading", { level: 1, name: "Loading product" })).toBeAttached(),
    seenIn: "p2-02/loading",
  },
  {
    name: "overview-loading",
    url: PRODUCT,
    setup: (page) => mockProductApi(page, { holdOverview: true }),
    ready: async (page) => {
      await loading(page, "Loading the overview…");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(/Sunset projection lamp/); // the header stays
    },
    seenIn: "p2-07/loading",
  },
  {
    name: "rail-empty",
    url: PRODUCT,
    setup: (page) => mockProductApi(page, { notes: [], tags: [] }),
    ready: async (page) => {
      await expect(page.getByRole("region", { name: "Tags" })).toContainText("No tags yet.");
      await expect(page.getByRole("region", { name: "Notes" })).toContainText("No notes yet. Write what you notice, and it stays with this product.");
      // The rail sits under the tab below 1280px; centred, both panels clear the phone's bottom bar.
      await page.getByRole("region", { name: "Notes" }).evaluate((el) => el.scrollIntoView({ block: "center" }));
    },
  },
  {
    name: "sellers-loading",
    url: `${PRODUCT}?tab=sellers`,
    setup: (page) => mockSellersApi(page, { hold: true }),
    ready: (page) => loading(page, "Loading sellers…"),
    seenIn: "p2-11/loading",
  },
  {
    name: "sellers-stale",
    url: `${PRODUCT}?tab=sellers`,
    setup: (page) => mockSellersApi(page),
    ready: async (page) => {
      await expect(page.getByText(/active first, newest start first · as of Oct 22, 11:00 UTC$/)).toBeVisible();
      await sellerRow(page, "cozycorner.shop").scrollIntoViewIfNeeded(); // in the screenshot, below the summary on a phone
      await expect(sellerRow(page, "cozycorner.shop")).toContainText("2d ago· stale");
      await expect(sellerRow(page, "cozycorner.shop").getByText("2d ago")).toHaveAttribute("title", "Oct 20, 10:00 UTC · Shopify stores");
    },
  },
  {
    name: "profit-loading",
    url: `${PRODUCT}?tab=profit`,
    setup: (page) => mockProfitApi(page, { hold: true }),
    ready: (page) => loading(page, "Calculating profit…"),
    seenIn: "p2-20/loading",
  },
];
