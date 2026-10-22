import createFetchClient from "openapi-fetch";
import createClient from "openapi-react-query";

import type { paths } from "./schema";

// clerk-js sets `window.Clerk` once it loads. @clerk/nextjs doesn't type it (and @clerk/testing declares it
// globally for the e2e files), so this names only the one call used below.
type ClerkWindow = { Clerk?: { session?: { getToken(): Promise<string | null> } | null } };

// Browser client for the FastAPI service (DEC-019). Calls go through Next's same-origin /api/* rewrite
// (no CORS) with the Clerk session token as a Bearer header, which the API verifies (DEC-020). Types come
// from schema.d.ts, which `pnpm gen:api` regenerates: never edit it by hand.
export const fetchClient = createFetchClient<paths>({ baseUrl: "/api" });

fetchClient.use({
  async onRequest({ request }) {
    const token = await (window as unknown as ClerkWindow).Clerk?.session?.getToken();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
});

export const $api = createClient(fetchClient);

/** The API's RFC 9457 error body. Every API route can answer with it (apps/api errors.py). */
export type Problem = paths["/v1/me"]["get"]["responses"][401]["content"]["application/problem+json"];

/**
 * True when the API itself answered with an error. Anything else means the request never reached it: the
 * fetch failed, or the /api rewrite couldn't connect and Next answered with its own non-JSON 500.
 */
export function isProblem(error: unknown): error is Problem {
  return typeof error === "object" && error !== null && "request_id" in error && "code" in error;
}
