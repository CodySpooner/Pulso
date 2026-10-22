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
