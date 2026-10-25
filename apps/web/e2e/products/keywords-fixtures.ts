import type { Page } from "@playwright/test";

import { decide, type Keyword } from "../../src/app/(app)/products/[id]/keywords-model";
import type { components } from "../../src/lib/api/schema";
import { NOW, problem } from "../data-health/fixtures";

// p3-02 (KW-1): fixture GET/POST /v1/products/{id}/keywords, never a database restore. The candidates and scores are
// what the API's grams() returns for the fixture product's name and three listing titles (apps/api/tests).

type S = components["schemas"];
const AS_OF = new Date(NOW.getTime() - 6 * 3_600_000).toISOString(); // the newest listing title, 6 h before NOW
const DECIDED = new Date(NOW.getTime() - 26 * 3_600_000).toISOString();
const candidate = (keyword: string, relevance: number): Keyword => ({ keyword, relevance, as_of: AS_OF, source: "title", status: "candidate", decided_at: null });

/** Nothing decided yet: every suggestion is a candidate, best first. */
export const undecided: S["KeywordList"] = {
  keywords: [
    candidate("sunset projection lamp", 0.833),
    candidate("lamp", 0.5),
    candidate("sunset", 0.5),
    candidate("led sunset lamp projector", 0.438),
    candidate("rainbow night light", 0.25),
    candidate("colour modes", 0.212),
    candidate("bedroom", 0.125),
    candidate("remote", 0.125),
    candidate("usb", 0.125),
  ],
};

/** Two confirmed (one typed in), one rejected, the rest still suggested. */
export const decided: S["KeywordList"] = {
  keywords: order([
    ...undecided.keywords.map((k): Keyword =>
      k.keyword === "sunset projection lamp" ? { ...k, status: "confirmed", decided_at: DECIDED } : k.keyword === "usb" ? { ...k, status: "rejected", decided_at: DECIDED } : k,
    ),
    { keyword: "sunset lamp for bedroom", relevance: null, as_of: AS_OF, source: "manual", status: "confirmed", decided_at: DECIDED },
  ]),
};

/** Titles with no usable phrase, nothing decided. */
export const empty: S["KeywordList"] = { keywords: [] };

/** The API's order: relevance, best first, typed-in ones last, then A to Z. */
function order(keywords: Keyword[]): Keyword[] {
  return [...keywords].sort((a, b) => (a.relevance === null ? 1 : 0) - (b.relevance === null ? 1 : 0) || (b.relevance ?? 0) - (a.relevance ?? 0) || a.keyword.localeCompare(b.keyword));
}

export interface KeywordsMock {
  body?: S["KeywordList"];
  /** Answer the GET with a problem, or never. */
  status?: number;
  hold?: boolean;
  /** Answer every GET after the first with this problem: a refresh that fails while the list stays. */
  refetchStatus?: number;
  /** Answer every POST with a 503, or never. */
  failSaves?: boolean;
  holdSaves?: boolean;
  /** Answer a 503 to the POSTs for these keywords only. */
  failKeywords?: string[];
}

/** The keywords endpoint, keeping what the page decides like the API. Register after mockProductApi: Playwright tries
 *  the newest route first. Returns the POST bodies. */
export async function mockKeywordsApi(page: Page, options: KeywordsMock = {}) {
  const posts: S["KeywordIn"][] = [];
  let saved = (options.body ?? undecided).keywords;
  let gets = 0;
  await page.route("**/api/v1/products/*/keywords", async (route) => {
    const request = route.request();
    if (request.method() === "GET") {
      if (options.hold) return;
      const status = options.status ?? (gets++ > 0 ? options.refetchStatus : undefined);
      if (status) return route.fulfill({ status, contentType: "application/problem+json", json: problem(status, `e2e-keywords-${status}`) });
      return route.fulfill({ json: { keywords: saved } });
    }
    const body = request.postDataJSON() as S["KeywordIn"];
    posts.push(body);
    if (options.holdSaves) return;
    if (options.failSaves || options.failKeywords?.includes(body.keyword)) return route.fulfill({ status: 503, contentType: "application/problem+json", json: problem(503, "e2e-keywords-save") });
    saved = order(decide(saved, body.keyword, body.status, NOW.toISOString()));
    return route.fulfill({ json: { keywords: saved } });
  });
  return posts;
}
