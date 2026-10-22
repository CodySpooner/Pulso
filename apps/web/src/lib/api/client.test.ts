import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchClient, isProblem } from "./client";

afterEach(() => vi.unstubAllGlobals());

async function getMe(response: Response, token: string | null) {
  vi.stubGlobal("window", { Clerk: { session: { getToken: async () => token } } });
  const fetch = vi.fn<(request: Request) => Promise<Response>>(async () => response);
  // An absolute base: Node can't resolve the browser's relative "/api".
  const result = await fetchClient.GET("/v1/me", { baseUrl: "http://web.test/api", fetch });
  return { result, request: fetch.mock.calls[0][0] };
}

describe("typed API client", () => {
  it("calls /api/v1/me with the Clerk session token", async () => {
    const me = { user_id: "u", workspace_id: "w", is_admin: true };
    const { result, request } = await getMe(Response.json(me), "token-1");
    expect(request.url).toBe("http://web.test/api/v1/me");
    expect(request.headers.get("Authorization")).toBe("Bearer token-1");
    expect(result.data).toEqual(me);
  });

  it("sends no Authorization header without a Clerk session", async () => {
    const { request } = await getMe(Response.json({}), null);
    expect(request.headers.has("Authorization")).toBe(false);
  });

  it("tells an API error from an API that isn't reachable", async () => {
    const problem = { title: "Forbidden", status: 403, code: "not_allowlisted", detail: "This Pulso is private.", request_id: "r-1" };
    const api = await getMe(Response.json(problem, { status: 403, headers: { "content-type": "application/problem+json" } }), "t");
    expect(isProblem(api.result.error)).toBe(true);

    // Next's /api rewrite answers a plain-text 500 when nothing listens on API_URL.
    const down = await getMe(new Response("Internal Server Error", { status: 500 }), "t");
    expect(isProblem(down.result.error)).toBe(false);
    expect(isProblem(new TypeError("fetch failed"))).toBe(false);
  });
});
