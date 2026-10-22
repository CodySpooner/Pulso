import { formatDelta, type GoodDirection } from "@/lib/format";
import { cn } from "@/lib/utils";

const tones = { positive: "text-positive", negative: "text-negative", neutral: "text-muted-foreground" } as const;

// DeltaBadge `text` (vault Design/Component Inventory): sign + ▲/▼, never colour alone. Colour follows
// `goodDirection`; a value that rounds to zero shows "±0.0" with no glyph. A missing or non-finite value
// shows a tertiary "—" with its reason on hover and for screen readers, and no unit (vault Design/Typography).
export function DeltaBadge({
  value,
  goodDirection = "up",
  unit = "",
  digits,
  missingReason = "No source yet",
  className,
}: {
  value: number | null | undefined;
  goodDirection?: GoodDirection;
  unit?: string;
  digits?: number;
  missingReason?: string;
  className?: string;
}) {
  const { glyph, text, tone, missing } = formatDelta(value, goodDirection, digits);
  if (missing) {
    return (
      <span title={missingReason} className={cn("whitespace-nowrap text-subtle-foreground", className)}>
        <span aria-hidden>{text}</span>
        <span className="sr-only">{missingReason}</span>
      </span>
    );
  }
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
