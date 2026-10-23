import type { components } from "@/lib/api/schema";

// Pure Data Health rules over the DH-1 contract (DEC-068), shared by the page and the nav badge (DEC-096).

export type SourceHealth = components["schemas"]["SourceHealth"];
export type Run = components["schemas"]["Run"];
export type RunDetail = components["schemas"]["RunDetail"];
export type HostHealth = components["schemas"]["HostHealth"];
export type Gap = components["schemas"]["Gap"];
export type CoverageDay = components["schemas"]["CoverageDay"];

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;

/** An unfilled gap marks its source overdue while the missed slot ended less than this long ago (DEC-096). */
export const OVERDUE_WINDOW_MS = 24 * HOUR;
/** No successful backup for longer than this raises the missing-backup state (DEC-060). */
export const BACKUP_MAX_AGE_MS = 26 * HOUR;

export type SourceState = "blocked" | "disabled" | "running" | "failing" | "overdue" | "skipped" | "partial" | "never" | "healthy";

/** States that put a count on the Data Health nav badge (DH-3). */
export const ATTENTION: ReadonlySet<SourceState> = new Set(["blocked", "failing", "overdue"]);

export function sourceState(source: SourceHealth, latestGapEnds: HostHealth["latest_gap_ends"], now: number): SourceState {
  if (source.status === "blocked") return "blocked";
  if (!source.enabled) return "disabled";
  const run = source.last_run;
  if (run?.status === "queued" || run?.status === "running") return "running";
  if (run?.status === "failed" || run?.status === "blocked") return "failing";
  const gapEnd = latestGapEnds[source.key];
  if (gapEnd && now - Date.parse(gapEnd) < OVERDUE_WINDOW_MS) return "overdue";
  // A suppressed slot collected nothing (DEC-108); the gap audit counts it as missed (imp-042, DEC-123).
  if (run?.status === "skipped" && run.error_code === "slot_suppressed") return "skipped";
  if (run?.status === "partial" || (run?.status === "success" && !run.complete)) return "partial";
  return run ? "healthy" : "never";
}

/** Why the latest slot was skipped, naming the blocking run when the API supplies it. */
export function skipNote(run: Run): string {
  return run.blocked_by != null ? `Run #${run.blocked_by} was still active` : "An earlier run was still active";
}

export function attentionCount(sources: SourceHealth[], latestGapEnds: HostHealth["latest_gap_ends"], now: number): number {
  return sources.filter((s) => ATTENTION.has(sourceState(s, latestGapEnds, now))).length;
}

export type HostState = "none" | "online" | "late" | "offline";

/** Amber after 15 min without a heartbeat, red after 2 h (vault Features/Data Health, States). */
export function hostState(host: HostHealth, now: number): HostState {
  const at = host.latest_heartbeat?.at;
  if (!at) return "none";
  const age = now - Date.parse(at);
  return age <= 15 * MINUTE ? "online" : age <= 2 * HOUR ? "late" : "offline";
}

export type BackupState = "none" | "ok" | "running" | "failed" | "overdue";

/** `runs` are the backup source's runs, newest first. */
export function backupState(runs: Run[], now: number): { state: BackupState; latest?: Run; lastSuccess?: Run } {
  const [latest] = runs;
  if (!latest) return { state: "none" };
  const lastSuccess = runs.find((r) => r.status === "success");
  const done = lastSuccess && Date.parse(lastSuccess.finished_at ?? lastSuccess.queued_at);
  const state: BackupState =
    latest.status === "queued" || latest.status === "running"
      ? "running"
      : latest.status === "failed" || latest.status === "blocked"
        ? "failed"
        : !done || now - done > BACKUP_MAX_AGE_MS
          ? "overdue"
          : "ok";
  return { state, latest, lastSuccess };
}

export interface GapRange {
  source_key: string;
  reason: string;
  start: string;
  end: string;
  slots: number;
}

/** Consecutive missed slots of one source and reason become one start–end range, newest first. */
export function mergeGaps(gaps: Gap[]): GapRange[] {
  const sorted = [...gaps].sort(
    (a, b) =>
      a.source_key.localeCompare(b.source_key) || a.reason.localeCompare(b.reason) || Date.parse(a.slot_start) - Date.parse(b.slot_start),
  );
  const ranges: GapRange[] = [];
  for (const g of sorted) {
    const last = ranges.at(-1);
    if (last && last.source_key === g.source_key && last.reason === g.reason && Date.parse(last.end) >= Date.parse(g.slot_start)) {
      if (Date.parse(g.slot_end) > Date.parse(last.end)) last.end = g.slot_end;
      last.slots++;
    } else {
      ranges.push({ source_key: g.source_key, reason: g.reason, start: g.slot_start, end: g.slot_end, slots: 1 });
    }
  }
  return ranges.sort((a, b) => Date.parse(b.start) - Date.parse(a.start));
}

/** The last `count` UTC dates (YYYY-MM-DD), oldest first, ending today in UTC (DEC-031). */
export function utcDays(count: number, now: number): string[] {
  const today = Math.floor(now / (24 * HOUR));
  return Array.from({ length: count }, (_, i) => new Date((today - count + 1 + i) * 24 * HOUR).toISOString().slice(0, 10));
}

export interface CoverageRow {
  key: string;
  name: string;
  /** One entry per day in `days`; null when the view has no row for that day. */
  cells: (CoverageDay | null)[];
}

/** One heatmap row per non-internal source, in the API's source order (the backup has its own card). */
export function coverageRows(coverage: CoverageDay[], sources: SourceHealth[], days: string[]): CoverageRow[] {
  const byKey = new Map(coverage.map((c) => [`${c.source_key} ${c.day}`, c]));
  return sources
    .filter((s) => s.type !== "internal")
    .map((s) => ({ key: s.key, name: s.name, cells: days.map((d) => byKey.get(`${s.key} ${d}`) ?? null) }));
}

export type ImportPreview = components["schemas"]["ImportPreview"];
export type ImportResult = components["schemas"]["ImportResult"];

/** The API's upload cap (decode_upload): a bigger file is refused before it is sent. */
export const IMPORT_MAX_BYTES = 20 * 1024 * 1024;

const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;

/** The preselected import source: the first that can commit, so the common case needs no change. */
export function defaultImportSource(sources: SourceHealth[]): SourceHealth | undefined {
  return sources.find((s) => s.csv_import === "ready") ?? sources.find((s) => s.csv_import != null);
}

/** Why the previewed file can't be imported, or null when it can. */
export function commitBlocker(source: SourceHealth, preview: ImportPreview): string | null {
  if (source.csv_import !== "ready") return `Importing into ${source.name} arrives with its import adapter. You can check files now.`;
  if (preview.valid === 0) return "No valid rows to import. Fix the rows below and choose the file again.";
  return null;
}

export function previewSummary(p: ImportPreview): string {
  const parts = [plural(p.valid, "valid row"), plural(p.invalid, "invalid row")];
  if (p.skipped > 0) parts.push(`${plural(p.skipped, "blank line")} skipped`);
  return parts.join(" · ");
}

/** The commit's outcome in words (vault Features/CSV Export & Import, Duplicate state). */
export function importOutcome(result: ImportResult, sourceName: string): { tone: "ok" | "error"; text: string } {
  const { run, original_run_id: original } = result;
  if (run.status === "skipped") {
    return result.in_progress
      ? { tone: "ok", text: `This file is still importing as run #${original}.` }
      : { tone: "ok", text: `This exact file was already imported as run #${original}. Nothing new was written.` };
  }
  if (run.status === "failed") {
    const why = run.error_code === "no_valid_rows" ? "the file has no valid rows" : (run.error_code ?? "unknown error");
    return { tone: "error", text: `Import failed as run #${run.id}: ${why}.` };
  }
  if (run.status !== "success" && run.status !== "partial") return { tone: "ok", text: `Import ${run.status} as run #${run.id}.` };
  const counts = `${run.rows_inserted.toLocaleString("en-US")} new, ${run.rows_updated.toLocaleString("en-US")} updated, ${run.rows_unchanged.toLocaleString("en-US")} unchanged`;
  const skipped = result.error_count > 0 ? ` Rows with errors were skipped (${plural(result.error_count, "error")}).` : "";
  return { tone: "ok", text: `Imported into ${sourceName} as run #${run.id}: ${counts}.${skipped}` };
}
