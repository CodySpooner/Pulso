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

export type SourceState = "blocked" | "disabled" | "running" | "failing" | "overdue" | "partial" | "never" | "healthy";

/** States that put a count on the Data Health nav badge (DH-3). */
export const ATTENTION: ReadonlySet<SourceState> = new Set(["blocked", "failing", "overdue"]);

export function sourceState(source: SourceHealth, openGaps: Gap[], now: number): SourceState {
  if (source.status === "blocked") return "blocked";
  if (!source.enabled) return "disabled";
  const run = source.last_run;
  if (run?.status === "queued" || run?.status === "running") return "running";
  if (run?.status === "failed" || run?.status === "blocked") return "failing";
  if (openGaps.some((g) => g.source_key === source.key && now - Date.parse(g.slot_end) < OVERDUE_WINDOW_MS)) return "overdue";
  if (run?.status === "partial" || (run?.status === "success" && !run.complete)) return "partial";
  return run ? "healthy" : "never";
}

export function attentionCount(sources: SourceHealth[], openGaps: Gap[], now: number): number {
  return sources.filter((s) => ATTENTION.has(sourceState(s, openGaps, now))).length;
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
