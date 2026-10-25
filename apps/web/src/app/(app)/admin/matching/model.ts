import type { components } from "@/lib/api/schema";

// UX-1 Matching Queue (DEC-263): the keyboard map and the pure queue rules, kept out of the components so Vitest
// covers them. The queue is cleared with one key per decision; the next pair is selected at once, never after an
// animation, so a key pressed during one applies to the next pair.

export type QueueItem = components["schemas"]["QueueItem"];
export type Detail = components["schemas"]["CandidateDetail"];
export type Cluster = components["schemas"]["Cluster"];

export type Action =
  | { type: "accept" | "reject" | "skip" | "merge" | "split" | "undo" | "next" | "prev" }
  | { type: "image"; index: number };

export interface KeyInput {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
  repeat: boolean;
  target: EventTarget | null;
}

const KEYS: Record<string, Action["type"]> = { a: "accept", r: "reject", s: "skip", m: "merge", x: "split", u: "undo", j: "next", k: "prev" };
/** Held down, only moving repeats: a held A never accepts a run of pairs. */
const REPEATS = new Set<Action["type"]>(["next", "prev", "skip"]);

/** The desktop keyboard map (vault Features/Matching Queue). Typing in a field, Alt, and Shift (Shift+A batch accept
 *  isn't built) are never shortcuts; Ctrl/⌘+Z is undo. */
export function keyAction(e: KeyInput): Action | null {
  if (e.altKey || typing(e.target)) return null;
  const key = e.key.toLowerCase();
  if (e.ctrlKey || e.metaKey) return key === "z" && !e.shiftKey && !e.repeat ? { type: "undo" } : null;
  if (e.shiftKey) return null;
  if (/^[1-4]$/.test(key)) return { type: "image", index: Number(key) - 1 };
  const type = KEYS[key];
  if (!type || (e.repeat && !REPEATS.has(type))) return null;
  return { type } as Action;
}

function typing(target: EventTarget | null): boolean {
  const el = target as { tagName?: string; isContentEditable?: boolean } | null;
  return !!el && (el.isContentEditable === true || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName ?? ""));
}

/** The legend under the decision bar, in the order the keys are learned. */
export const LEGEND: { keys: string[]; label: string }[] = [
  { keys: ["A"], label: "Accept" },
  { keys: ["R"], label: "Reject" },
  { keys: ["S"], label: "Skip" },
  { keys: ["M"], label: "Merge" },
  { keys: ["X"], label: "Split" },
  { keys: ["U"], label: "Undo" },
  { keys: ["J", "K"], label: "Next, previous" },
  { keys: ["1–4"], label: "Image" },
];

/** After a decision or skip, the pair to show: the next one, else the one before, else none. */
export function nextAfter(ids: number[], current: number): number | null {
  const at = ids.indexOf(current);
  if (at === -1) return ids[0] ?? null;
  return ids[at + 1] ?? ids[at - 1] ?? null;
}

/** J/K: one step, clamped at the ends. */
export function step(ids: number[], current: number | null, by: 1 | -1): number | null {
  if (ids.length === 0) return null;
  const at = current == null ? -1 : ids.indexOf(current);
  return ids[Math.min(Math.max(at + by, 0), ids.length - 1)];
}

export interface Bar {
  id: string;
  label: string;
  value: number | null; // 0–1; null shows "n/a"
  weight?: number;
  missing?: string;
}

/** The score components against the scorer's thresholds. A missing component carries weight 0 (DEC-040). */
export function bars(detail: Detail): Bar[] {
  const t = detail.thresholds;
  const noImage = detail.a.images.length === 0 || detail.b.images.length === 0 ? "No image stored for one side" : "No image embedding yet";
  return [
    { id: "image", label: "Image (CLIP cosine)", value: detail.image_cos, weight: t.image_weight, missing: noImage },
    { id: "title", label: "Title cosine", value: detail.title_cos, weight: t.title_weight, missing: "No title embedding yet" },
    { id: "phash", label: "pHash similarity", value: detail.phash_sim, weight: t.phash_weight, missing: noImage },
  ];
}

export const isGtin = (version: string) => version.startsWith("gtin-");

/** The merge dialog's direction: the younger product into the older (first_seen_at, then id), as accept does. */
export function mergeDirection(clusters: Cluster[]): { from: Cluster; into: Cluster } | null {
  if (clusters.length !== 2) return null;
  const [older, younger] = [...clusters].sort((x, y) => x.first_seen_at.localeCompare(y.first_seen_at) || x.product_id.localeCompare(y.product_id));
  return { from: younger, into: older };
}

/** A price in its own currency's minor units, e.g. 1999 USD → "$19.99", 1500 JPY → "¥1,500". */
export function money(minor: number, currency: string): string {
  const format = new Intl.NumberFormat("en-US", { style: "currency", currency });
  const digits = format.resolvedOptions().maximumFractionDigits ?? 2;
  return format.format(minor / 10 ** digits);
}

export const SOURCE_LABELS: Record<string, string> = { cj: "CJ", shopify_stores: "Shopify", listing_images: "Images", google_trends: "Trends" };
export const sourceLabel = (key: string) => SOURCE_LABELS[key] ?? key;
export const pairLabel = (pair: string) => pair.split("+").map(sourceLabel).join(" ↔ ");

/** Score bands for the filter, at the scorer's thresholds. */
export function bands(t: { auto_link: number; queue: number }) {
  return [
    { value: "auto", label: `≥ ${t.auto_link.toFixed(2)}`, min: t.auto_link, max: undefined },
    { value: "high", label: `0.85–${t.auto_link.toFixed(2)}`, min: 0.85, max: t.auto_link },
    { value: "low", label: `${t.queue.toFixed(2)}–0.85`, min: t.queue, max: 0.85 },
  ] as const;
}
