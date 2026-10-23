import { describe, expect, test } from "vitest";

import {
  attentionCount,
  backupState,
  commitBlocker,
  coverageRows,
  defaultImportSource,
  hostState,
  importOutcome,
  mergeGaps,
  previewSummary,
  sourceState,
  utcDays,
  type Gap,
  type ImportPreview,
  type ImportResult,
  type Run,
  type SourceHealth,
} from "./model";

const NOW = Date.parse("2026-10-22T14:00:00Z");
const ago = (hours: number) => new Date(NOW - hours * 3_600_000).toISOString();

function run(over: Partial<Run> = {}): Run {
  return {
    id: 1, source_key: "cj", trigger: "schedule", slot_key: null, status: "success", complete: true, host: "pc",
    queued_at: ago(2), started_at: ago(2), finished_at: ago(1.9), rows_fetched: 10, rows_inserted: 2, rows_updated: 1,
    rows_unchanged: 7, http_requests: 3, last_status_code: 200, error_code: null, error_message: null,
    target_count: 3, successful_target_count: 3, ...over,
  };
}

function source(over: Partial<SourceHealth> = {}): SourceHealth {
  return {
    key: "cj", name: "CJ Dropshipping", type: "official_api", phase: 1, enabled: true, status: "active",
    disabled_reason: null, disabled_at: null, retry_not_before: null, last_status_code: 200, last_run: run(),
    freshness: ago(1.9), seed_approved: true, approved_targets: 3, quota_used: null, quota_limit: null, csv_import: null, ...over,
  };
}

const gap = (over: Partial<Gap> = {}): Gap => ({
  source_key: "cj", slot_key: "2026-10-22T06", slot_start: ago(8), slot_end: ago(7), reason: "host_offline", detected_at: ago(6), ...over,
});

describe("sourceState", () => {
  test.each([
    ["blocked even when disabled", source({ status: "blocked", enabled: false }), "blocked"],
    ["disabled by the owner", source({ status: "disabled", enabled: false }), "disabled"],
    ["queued run", source({ last_run: run({ status: "queued" }) }), "running"],
    ["failed run", source({ last_run: run({ status: "failed" }) }), "failing"],
    ["partial run", source({ last_run: run({ status: "partial", complete: false }) }), "partial"],
    ["success with missing targets", source({ last_run: run({ complete: false }) }), "partial"],
    ["no run yet", source({ last_run: null }), "never"],
    ["last run fine", source(), "healthy"],
  ])("%s", (_, s, expected) => {
    expect(sourceState(s, [], NOW)).toBe(expected);
  });

  test("an unfilled gap that ended in the last 24 h makes an enabled source overdue", () => {
    expect(sourceState(source(), [gap()], NOW)).toBe("overdue");
    expect(sourceState(source(), [gap({ slot_end: ago(25) })], NOW)).toBe("healthy");
    expect(sourceState(source(), [gap({ source_key: "fx_frankfurter" })], NOW)).toBe("healthy");
    expect(sourceState(source({ enabled: false, status: "disabled" }), [gap()], NOW)).toBe("disabled");
  });
});

test("attentionCount counts blocked, failing and overdue sources only", () => {
  const sources = [
    source({ key: "a", status: "blocked", enabled: false }),
    source({ key: "b", last_run: run({ status: "failed" }) }),
    source({ key: "c" }),
    source({ key: "d", last_run: run({ status: "partial" }) }),
    source({ key: "e", enabled: false, status: "disabled" }),
  ];
  expect(attentionCount(sources, [gap({ source_key: "c" })], NOW)).toBe(3);
  expect(attentionCount(sources.slice(2), [], NOW)).toBe(0);
});

test("hostState follows the 15 min / 2 h heartbeat rule", () => {
  const host = (at: string | null) => ({ live_runs_allowed: true, open_gaps: [], latest_heartbeat: at ? { host: "pc", at } : null });
  expect(hostState(host(null), NOW)).toBe("none");
  expect(hostState(host(ago(0.2)), NOW)).toBe("online");
  expect(hostState(host(ago(1)), NOW)).toBe("late");
  expect(hostState(host(ago(3)), NOW)).toBe("offline");
});

describe("backupState", () => {
  test("no runs", () => expect(backupState([], NOW).state).toBe("none"));
  test("a recent success is ok", () => expect(backupState([run({ finished_at: ago(5) })], NOW)).toMatchObject({ state: "ok" }));
  test("older than 26 h is overdue", () => expect(backupState([run({ finished_at: ago(27) })], NOW).state).toBe("overdue"));
  test("a failed latest run wins", () => {
    const result = backupState([run({ id: 2, status: "failed" }), run({ id: 1, finished_at: ago(5) })], NOW);
    expect(result).toMatchObject({ state: "failed", lastSuccess: { id: 1 } });
  });
  test("a running backup", () => expect(backupState([run({ status: "running", finished_at: null })], NOW).state).toBe("running"));
});

test("mergeGaps joins consecutive slots per source and reason, newest first", () => {
  const ranges = mergeGaps([
    gap({ slot_key: "a", slot_start: ago(10), slot_end: ago(9) }),
    gap({ slot_key: "b", slot_start: ago(9), slot_end: ago(8) }),
    gap({ slot_key: "c", slot_start: ago(5), slot_end: ago(4) }),
    gap({ slot_key: "d", slot_start: ago(9), slot_end: ago(8), reason: "run_failed" }),
    gap({ slot_key: "e", source_key: "fx", slot_start: ago(9), slot_end: ago(8) }),
  ]);
  expect(ranges.map((r) => [r.source_key, r.reason, r.slots, r.start, r.end])).toEqual([
    ["cj", "host_offline", 1, ago(5), ago(4)],
    ["cj", "run_failed", 1, ago(9), ago(8)],
    ["fx", "host_offline", 1, ago(9), ago(8)],
    ["cj", "host_offline", 2, ago(10), ago(8)],
  ]);
});

test("utcDays ends on today's UTC date", () => {
  expect(utcDays(3, Date.parse("2026-10-22T23:30:00-05:00"))).toEqual(["2026-10-21", "2026-10-22", "2026-10-23"]);
});

test("coverageRows places days per source and skips internal sources", () => {
  const days = utcDays(3, NOW);
  const rows = coverageRows(
    [{ source_key: "cj", day: days[2], status: "success", runs: 1, rows: 5, targets: 3, successful_targets: 3 }],
    [source(), source({ key: "backup", name: "Backups", type: "internal" })],
    days,
  );
  expect(rows).toHaveLength(1);
  expect(rows[0].cells.map((c) => c?.status ?? null)).toEqual([null, null, "success"]);
});

describe("CSV import flow", () => {
  const preview = (over: Partial<ImportPreview> = {}): ImportPreview => ({
    rows: [], valid: 3, invalid: 1, skipped: 0, error_count: 1, errors: [{ row: 5, column: "rate", message: "Invalid rate value" }], ...over,
  });
  const result = (over: Partial<ImportResult> = {}, runOver: Partial<Run> = {}): ImportResult => ({
    run: run({ id: 42, trigger: "csv", rows_inserted: 3, rows_updated: 0, rows_unchanged: 0, ...runOver }),
    raw_payload_id: 77, original_run_id: null, in_progress: false, error_count: 1, errors: [], ...over,
  });
  const fx = source({ key: "fx_frankfurter", name: "Frankfurter FX", csv_import: "ready" });
  const cj = source({ csv_import: "preview_only" });

  test("preselects the first source that can import, skipping sources without a template", () => {
    expect(defaultImportSource([source({ key: "backup" }), cj, fx])?.key).toBe("fx_frankfurter");
    expect(defaultImportSource([source({ key: "backup" }), cj])?.key).toBe("cj");
    expect(defaultImportSource([source({ key: "backup" })])).toBeUndefined();
  });

  test("import is blocked without an adapter or without a valid row, never silently", () => {
    expect(commitBlocker(fx, preview())).toBeNull();
    expect(commitBlocker(cj, preview())).toMatch(/^Importing into CJ Dropshipping arrives with its import adapter/);
    expect(commitBlocker(fx, preview({ valid: 0 }))).toMatch(/^No valid rows/);
  });

  test("the preview summary counts rows and blank lines", () => {
    expect(previewSummary(preview())).toBe("3 valid rows · 1 invalid row");
    expect(previewSummary(preview({ valid: 1, invalid: 0, skipped: 2 }))).toBe("1 valid row · 0 invalid rows · 2 blank lines skipped");
  });

  test("outcomes: imported, already imported, still importing, failed", () => {
    expect(importOutcome(result(), "Frankfurter FX")).toEqual({
      tone: "ok",
      text: "Imported into Frankfurter FX as run #42: 3 new, 0 updated, 0 unchanged. Rows with errors were skipped (1 error).",
    });
    expect(importOutcome(result({ original_run_id: 42 }, { id: 43, status: "skipped" }), "FX").text).toBe(
      "This exact file was already imported as run #42. Nothing new was written.",
    );
    expect(importOutcome(result({ original_run_id: 42, in_progress: true }, { id: 44, status: "skipped" }), "FX").text).toBe(
      "This file is still importing as run #42.",
    );
    expect(importOutcome(result({}, { status: "failed", error_code: "no_valid_rows" }), "FX")).toEqual({
      tone: "error",
      text: "Import failed as run #42: the file has no valid rows.",
    });
  });
});
