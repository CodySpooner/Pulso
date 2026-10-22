// Number formatting shared by every view (vault Design/Typography, Design System › The delta rule).

export type GoodDirection = "up" | "down" | "neutral";

export interface DeltaParts {
  /** Direction of change; null when the value rounds to zero (flat). */
  glyph: "▲" | "▼" | null;
  /** Signed value at the display precision: "+12.4", "−3.1" (U+2212) or "±0.0". */
  text: string;
  /** Whether the change is good for the owner, which picks the colour. */
  tone: "positive" | "negative" | "neutral";
}

export function formatDelta(value: number, goodDirection: GoodDirection, digits = 1): DeltaParts {
  const magnitude = Math.abs(value).toFixed(digits);
  if (Number(magnitude) === 0) return { glyph: null, text: `±${magnitude}`, tone: "neutral" };
  const up = value > 0;
  const tone = goodDirection === "neutral" ? "neutral" : up === (goodDirection === "up") ? "positive" : "negative";
  return { glyph: up ? "▲" : "▼", text: `${up ? "+" : "−"}${magnitude}`, tone };
}
