import type { Page } from "@playwright/test";

// The API's `?format=csv` answer for p4-09 specs (DEC-316), from fixtures only. Registered after mockFeedApi, so it
// answers the export while the feed mock keeps answering the JSON pages.
export const FILE = `pulso_discover_${new Date().toISOString().slice(0, 10)}.csv`;
export const OVER_CAP = "54,210 rows exceed the 50,000 export limit. Narrow your filters.";

type Reply = "file" | "over-cap" | "down" | "hold";

/** `path` and `file` default to Discover's; the Testing Board passes its own (p4-30). */
export async function mockExport(page: Page, replies: Reply[] = ["file"], { path = "/api/v1/products", file = FILE } = {}) {
  const calls: URL[] = [];
  await page.route(
    (url) => url.pathname === path && url.searchParams.get("format") === "csv",
    (route) => {
      calls.push(new URL(route.request().url()));
      const reply = replies[Math.min(calls.length, replies.length) - 1];
      if (reply === "hold") return;
      if (reply === "down") return route.abort("connectionrefused");
      if (reply === "over-cap")
        return route.fulfill({
          status: 422,
          contentType: "application/problem+json",
          json: { type: "about:blank", title: "Unprocessable Content", status: 422, code: "export_too_large", detail: OVER_CAP, request_id: "e2e-export-422", errors: [] },
        });
      return route.fulfill({
        body: "﻿id,product,price_min,currency\r\nf-1,Sunset lamp,24.00,USD\r\n",
        headers: { "content-type": "text/csv; charset=utf-8", "content-disposition": `attachment; filename="${file}"`, "x-total-count": "1" },
      });
    },
  );
  return calls;
}
