import { readFileSync } from "node:fs";
import path from "node:path";

import type { Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";

// Fixture DH-1 responses for the Data Health e2e tests and screenshots (never a database restore). Every
// time is relative to NOW, which the tests pin with page.clock, so relative times and the heatmap are stable.

type S = components["schemas"];
export const NOW = new Date("2026-10-22T14:00:00Z");
const at = (hoursAgo: number) => new Date(NOW.getTime() - hoursAgo * 3_600_000).toISOString();

function run(over: Partial<S["Run"]> & Pick<S["Run"], "id" | "source_key">): S["Run"] {
  return {
    trigger: "schedule", slot_key: null, status: "success", complete: true, host: "pulso-pc",
    queued_at: at(2), started_at: at(2), finished_at: at(1.95), rows_fetched: 0, rows_inserted: 0, rows_updated: 0,
    rows_unchanged: 0, http_requests: 1, last_status_code: 200, error_code: null, error_message: null,
    target_count: 1, successful_target_count: 1, ...over,
  };
}

const shopifyFailed = run({
  id: 412, source_key: "shopify_stores", status: "blocked", complete: false, slot_key: "2026-10-22", queued_at: at(5.1), started_at: at(5.1),
  finished_at: at(5), rows_fetched: 250, rows_inserted: 0, rows_updated: 0, http_requests: 6, last_status_code: 429,
  error_code: "blocked_429", error_message: "429 Too Many Requests (retry-after 60). 5 in a row, so the adapter turned itself off.",
  target_count: 4, successful_target_count: 1,
});

export const sources: S["SourceHealth"][] = [
  {
    key: "shopify_stores", name: "Shopify stores", type: "public_endpoint", phase: 1, enabled: false, status: "blocked",
    disabled_reason: "5 consecutive 429 responses", disabled_at: at(5), retry_not_before: at(-1), last_status_code: 429,
    last_run: shopifyFailed, freshness: at(29), seed_approved: true, approved_targets: 4, quota_used: null, quota_limit: null,
    csv_import: "preview_only",
  },
  {
    key: "cj", name: "CJ Dropshipping", type: "official_api", phase: 1, enabled: true, status: "active", disabled_reason: null,
    disabled_at: null, retry_not_before: null, last_status_code: 200,
    last_run: run({ id: 418, source_key: "cj", slot_key: "2026-10-22T12", queued_at: at(1.6), started_at: at(1.6), finished_at: at(1.5), rows_fetched: 1240, rows_inserted: 36, rows_updated: 112, rows_unchanged: 1092, http_requests: 26, target_count: 10, successful_target_count: 10 }),
    freshness: at(1.5), seed_approved: true, approved_targets: 10, quota_used: 2650, quota_limit: 50000, csv_import: "preview_only",
  },
  {
    key: "google_trends", name: "Google Trends", type: "vendor", phase: 1, enabled: true, status: "active", disabled_reason: null,
    disabled_at: null, retry_not_before: null, last_status_code: 200,
    last_run: run({ id: 405, source_key: "google_trends", slot_key: "2026-10-21", queued_at: at(14), started_at: at(14), finished_at: at(13.9), rows_fetched: 180, rows_inserted: 180, http_requests: 12, target_count: 12, successful_target_count: 12 }),
    freshness: at(13.9), seed_approved: true, approved_targets: 12, quota_used: null, quota_limit: null, csv_import: "preview_only",
  },
  {
    key: "fx_frankfurter", name: "Frankfurter FX", type: "official_api", phase: 1, enabled: false, status: "disabled", disabled_reason: null,
    disabled_at: null, retry_not_before: null, last_status_code: null, last_run: null, freshness: null, seed_approved: null,
    approved_targets: null, quota_used: null, quota_limit: null, csv_import: "ready",
  },
  {
    key: "backup", name: "Backups", type: "internal", phase: 1, enabled: true, status: "active", disabled_reason: null, disabled_at: null,
    retry_not_before: null, last_status_code: null, last_run: run({ id: 417, source_key: "backup", queued_at: at(11), started_at: at(11), finished_at: at(10.95) }),
    freshness: null, seed_approved: null, approved_targets: null, quota_used: null, quota_limit: null, csv_import: null,
  },
];

/** Every source healthy and enabled: the badge has nothing to count. */
export const healthySources: S["SourceHealth"][] = sources.map((s) => ({
  ...s, enabled: true, status: "active", disabled_reason: null, disabled_at: null, retry_not_before: null,
  last_run: s.last_run && { ...s.last_run, status: "success", complete: true },
}));

const gap = (source_key: string, slot_key: string, startHoursAgo: number, reason = "host_offline"): S["Gap"] => ({
  source_key, slot_key, slot_start: at(startHoursAgo), slot_end: at(startHoursAgo - 1), reason, detected_at: at(startHoursAgo - 1.5),
});

export const host: S["HostHealth"] = {
  live_runs_allowed: false,
  latest_heartbeat: { host: "pulso-pc", at: at(4 / 60) },
  open_gaps: [gap("google_trends", "2026-10-22T10", 4), gap("google_trends", "2026-10-22T11", 3), gap("cj", "2026-10-19T06", 80, "run_failed")],
};

/** 90 UTC days per collecting source: collection starts 40 days ago, with a few failures and gaps. */
export function coverage(): S["CoverageDay"][] {
  const days: S["CoverageDay"][] = [];
  const statuses: Record<string, (i: number) => S["CoverageDay"]["status"] | null> = {
    cj: (i) => (i === 3 ? "gap" : i === 9 ? "partial" : i === 17 ? "filled" : "success"),
    google_trends: (i) => (i === 0 ? "gap" : i === 12 || i === 13 ? "gap" : i === 22 ? "failed" : "success"),
    shopify_stores: (i) => (i <= 1 ? "failed" : i === 6 ? "partial" : i > 30 ? null : "success"),
  };
  for (const [source_key, status] of Object.entries(statuses)) {
    for (let i = 39; i >= 0; i--) {
      const s = status(i);
      if (!s) continue;
      const day = new Date(NOW.getTime() - i * 86_400_000).toISOString().slice(0, 10);
      const ok = s === "success" || s === "filled";
      days.push({ source_key, day, status: s, runs: s === "gap" ? 0 : 1, rows: ok ? 120 : 0, targets: 4, successful_targets: ok ? 4 : s === "partial" ? 2 : 0 });
    }
  }
  return days;
}

export const backupRuns: S["RunPage"] = {
  next_cursor: null,
  items: Array.from({ length: 14 }, (_, i) => {
    const hoursAgo = 11 + 24 * i;
    return run({
      id: 417 - i * 30, source_key: "backup", trigger: "schedule", queued_at: at(hoursAgo), started_at: at(hoursAgo), finished_at: at(hoursAgo - 0.05),
      ...(i === 6 ? { status: "failed", complete: false, error_code: "pg_dump_failed", error_message: "pg_dump exited with status 1" } : {}),
    });
  }),
};

const shopifyRuns: S["Run"][] = [
  shopifyFailed,
  run({ id: 380, source_key: "shopify_stores", slot_key: "2026-10-21", queued_at: at(29.1), started_at: at(29.1), finished_at: at(29), rows_fetched: 1000, rows_inserted: 14, rows_updated: 220, http_requests: 8, target_count: 4, successful_target_count: 4 }),
];

export function runDetail(id: number): S["RunDetail"] | undefined {
  const r = [...shopifyRuns, ...sources.flatMap((s) => (s.last_run ? [s.last_run] : []))].find((x) => x.id === id);
  if (!r) return undefined;
  const stores = ["bleame.com", "meowingtons.com", "pawz.com", "northwind-home.example"];
  return {
    ...r,
    targets: stores.slice(0, r.target_count).map((store, i) => ({
      scope: "store", target_id: store, captured_at: r.finished_at ?? r.queued_at,
      status: i < r.successful_target_count ? "success" : "failed", raw_payload_id: i < r.successful_target_count ? 9001 + i : null,
    })),
  };
}

/** A Frankfurter FX file with one bad rate (P1-11b): the preview names its row; nothing is written. */
export const importPreview: S["ImportPreview"] = {
  rows: [], valid: 3, invalid: 1, skipped: 0, error_count: 1, errors: [{ row: 5, column: "rate", message: "Invalid rate value" }],
};

// apps/api/openapi.json is the exported contract; tests resolve operation ids from it, not from memory.
const openapi = JSON.parse(readFileSync(path.join(__dirname, "../../../api/openapi.json"), "utf8")) as {
  paths: Record<string, Record<string, { operationId: string }>>;
};

/** The operation id the API declares for a method and a concrete path such as /v1/admin/sources/cj/run. */
export function operationId(method: string, concretePath: string): string | undefined {
  for (const [template, ops] of Object.entries(openapi.paths)) {
    const pattern = new RegExp(`^${template.replace(/\{[^}]+\}/g, "[^/]+")}$`);
    if (pattern.test(concretePath)) return ops[method.toLowerCase()]?.operationId;
  }
}

export interface Call {
  method: string;
  path: string;
  body: unknown;
}

export interface MockOptions {
  sources?: S["SourceHealth"][];
  host?: Partial<S["HostHealth"]>;
  coverage?: S["CoverageDay"][];
  /** Abort every admin call, as when the API (on the home PC) is down. */
  down?: boolean;
  /** Hold every response this long, to show loading skeletons. */
  delayMs?: number;
}

/** Answers /api/v1/admin/* from the fixtures and records every call. Call before page.goto. */
export async function mockAdminApi(page: Page, options: MockOptions = {}): Promise<Call[]> {
  const calls: Call[] = [];
  const imported = new Map<string, number>(); // file bytes → the run that imported them
  const list = options.sources ?? sources;
  await page.clock.setFixedTime(NOW);
  await page.route("**/api/v1/admin/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const apiPath = url.pathname.replace(/^\/api/, "");
    const method = request.method();
    const upload = request.headers()["content-type"] === "application/octet-stream";
    calls.push({ method, path: apiPath, body: upload ? request.postData() : request.postDataJSON() });
    if (options.down) return route.abort("connectionrefused");
    if (options.delayMs) await new Promise((resolve) => setTimeout(resolve, options.delayMs));

    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body });
    if (method === "GET" && apiPath === "/v1/admin/sources") return json(list);
    if (method === "GET" && apiPath === "/v1/admin/host") return json({ ...host, ...options.host });
    if (method === "GET" && apiPath === "/v1/admin/coverage") return json(options.coverage ?? coverage());
    if (method === "GET" && apiPath === "/v1/admin/runs") {
      const source = url.searchParams.get("source");
      if (source === "backup") return json(backupRuns);
      const items = source === "shopify_stores" ? shopifyRuns : list.filter((s) => s.key === source && s.last_run).map((s) => s.last_run!);
      return json({ items, next_cursor: null });
    }
    const runMatch = apiPath.match(/^\/v1\/admin\/runs\/(\d+)$/);
    if (method === "GET" && runMatch) return json(runDetail(Number(runMatch[1])) ?? {}, runDetail(Number(runMatch[1])) ? 200 : 404);
    const sourceMatch = apiPath.match(/^\/v1\/admin\/sources\/([^/]+)(\/run)?$/);
    const source = sourceMatch && list.find((s) => s.key === sourceMatch[1]);
    if (source && method === "PATCH") {
      const { enabled } = request.postDataJSON() as { enabled: boolean };
      return json({ ...source, enabled, status: enabled ? "active" : source.status === "blocked" ? "blocked" : "disabled" });
    }
    if (source && method === "POST" && sourceMatch[2]) {
      return json(run({ id: 500, source_key: source.key, trigger: "manual", status: "queued", started_at: null, finished_at: null, queued_at: NOW.toISOString() }), 202);
    }
    const importMatch = apiPath.match(/^\/v1\/admin\/sources\/([^/]+)\/import(\/preview|\/template)?$/);
    if (importMatch?.[2] === "/template") return route.fulfill({ contentType: "text/csv", body: "date,base,quote,rate\n2026-01-01,USD,JPY,150\n" });
    if (importMatch?.[2] === "/preview") return json(importPreview);
    if (importMatch && method === "POST") {
      const bytes = request.postData() ?? "";
      const original = imported.get(bytes) ?? null;
      imported.set(bytes, original ?? 501);
      return json({
        run: run({
          id: original ? 502 : 501, source_key: importMatch[1], trigger: "csv", status: original ? "skipped" : "success", queued_at: NOW.toISOString(),
          rows_fetched: original ? 0 : 3, rows_inserted: original ? 0 : 3, target_count: original ? 0 : 1, successful_target_count: original ? 0 : 1,
        }),
        raw_payload_id: 77, original_run_id: original, in_progress: false, error_count: original ? 0 : 1, errors: original ? [] : importPreview.errors,
      } satisfies S["ImportResult"]);
    }
    return json({ type: "about:blank", title: "Not Found", status: 404, code: "not_found", detail: "No fixture.", request_id: "e2e", errors: [] }, 404);
  });
  return calls;
}
