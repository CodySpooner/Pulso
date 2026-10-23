// Number formatting shared by every view (vault Design/Typography, Design System › The delta rule).

export type GoodDirection = "up" | "down" | "neutral";

export interface DeltaParts {
  /** Direction of change; null when the value rounds to zero (flat) or is missing. */
  glyph: "▲" | "▼" | null;
  /** Signed value at the display precision: "+12.4", "−3.1" (U+2212) or "±0.0"; "—" when missing. */
  text: string;
  /** Whether the change is good for the owner, which picks the colour. */
  tone: "positive" | "negative" | "neutral";
  /** Set when the value is null, undefined, NaN or ±Infinity; it is never shown as zero (vault Design/Typography). */
  missing?: true;
}

export function formatDelta(value: number | null | undefined, goodDirection: GoodDirection, digits = 1): DeltaParts {
  if (value == null || !Number.isFinite(value)) return { glyph: null, text: "—", tone: "neutral", missing: true };
  const magnitude = Math.abs(value).toFixed(digits);
  if (Number(magnitude) === 0) return { glyph: null, text: `±${magnitude}`, tone: "neutral" };
  const up = value > 0;
  const tone = goodDirection === "neutral" ? "neutral" : up === (goodDirection === "up") ? "positive" : "negative";
  return { glyph: up ? "▲" : "▼", text: `${up ? "+" : "−"}${magnitude}`, tone };
}

/** Compact relative time for dense views: "just now", "4m ago", "3h ago", "2d ago", "in 1h". */
export function formatAgo(iso: string, now: number): string {
  const seconds = Math.round((now - Date.parse(iso)) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 60) return "just now";
  const text = abs < 3600 ? `${Math.floor(abs / 60)}m` : abs < 86_400 ? `${Math.floor(abs / 3600)}h` : `${Math.floor(abs / 86_400)}d`;
  return seconds < 0 ? `in ${text}` : `${text} ago`;
}

const utcStamp = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "UTC" });

/** Absolute UTC time, the hover partner of `formatAgo` (all timestamps are UTC, AGENTS.md §3). */
export function formatUtc(iso: string): string {
  return `${utcStamp.format(new Date(iso))} UTC`;
}

export function formatDuration(ms: number): string {
  const s = Math.round(ms / 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${pad(s % 60)}s`;
  return `${Math.floor(s / 3600)}h ${pad(Math.floor(s / 60) % 60)}m`;
}
