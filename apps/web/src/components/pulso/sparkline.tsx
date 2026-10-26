// Inline SVG sparklines for rows and lists (vault Design/Charts & Data Viz): Daily Pulse and Watchlists.

/** Polyline segments for a sparkline: scaled min to max, a null starts a new segment, so a gap is never bridged. */
export function sparkSegments(values: (number | null)[], width: number, height: number): string[] {
  const nums = values.filter((v): v is number => v !== null);
  const [min, max] = [Math.min(...nums), Math.max(...nums)];
  const x = (i: number) => ((i / (values.length - 1)) * (width - 2) + 1).toFixed(1);
  const y = (v: number) => (height - 1 - ((v - min) / (max - min || 1)) * (height - 2)).toFixed(1);
  const segments: string[][] = [[]];
  values.forEach((v, i) => (v === null ? segments.push([]) : segments.at(-1)!.push(`${x(i)},${y(v)}`)));
  return segments.filter((s) => s.length > 0).map((s) => s.join(" "));
}

/** Sparkline `row`: 64×20, neutral, a day without a value breaks the line; under 3 points a dashed baseline. The parent
 *  carries its meaning and text alternative, so it is hidden from screen readers. */
export function Sparkline({ values }: { values: (number | null)[] }) {
  const [w, h] = [64, 20];
  const points = values.filter((v) => v !== null).length;
  return (
    <svg width={w} height={h} aria-hidden className="shrink-0 text-muted-foreground">
      {points < 3 ? (
        <line x1="0" x2={w} y1={h / 2} y2={h / 2} className="stroke-border" strokeDasharray="2 3" />
      ) : (
        sparkSegments(values, w, h).map((s) =>
          s.includes(" ") ? (
            <polyline key={s} points={s} fill="none" stroke="currentColor" strokeWidth="var(--sparkline-stroke)" strokeLinejoin="round" strokeLinecap="round" />
          ) : (
            <circle key={s} cx={s.split(",")[0]} cy={s.split(",")[1]} r="1" fill="currentColor" />
          ),
        )
      )}
    </svg>
  );
}
