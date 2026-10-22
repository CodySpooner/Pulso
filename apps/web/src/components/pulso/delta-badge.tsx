import { formatDelta, type GoodDirection } from "@/lib/format";
import { cn } from "@/lib/utils";

const tones = { positive: "text-positive", negative: "text-negative", neutral: "text-muted-foreground" } as const;

// DeltaBadge `text` (vault Design/Component Inventory): sign + ▲/▼, never colour alone. Colour follows
// `goodDirection`; a value that rounds to zero shows "±0.0" with no glyph.
export function DeltaBadge({
  value,
  goodDirection = "up",
  unit = "",
  digits,
  className,
}: {
  value: number;
  goodDirection?: GoodDirection;
  unit?: string;
  digits?: number;
  className?: string;
}) {
  const { glyph, text, tone } = formatDelta(value, goodDirection, digits);
  return (
    <span className={cn("inline-flex items-center gap-1 whitespace-nowrap tabular-nums", tones[tone], className)}>
      {glyph && (
        <span aria-hidden className="text-micro">
          {glyph}
        </span>
      )}
      {text}
      {unit}
    </span>
  );
}
