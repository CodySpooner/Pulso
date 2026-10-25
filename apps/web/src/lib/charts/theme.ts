// The one chart theme (vault Design/Charts & Data Viz): canvas can't read CSS variables, so the colours and fonts
// are read from the design tokens at render time and read again when the theme changes.

export type ChartTokens = ReturnType<typeof chartTokens>;

export function chartTokens() {
  const css = getComputedStyle(document.documentElement);
  const v = (name: string) => css.getPropertyValue(name).trim();
  return {
    series: [1, 2, 3, 4, 5].map((i) => v(`--series-${i}`)), // identity: velocity, search, price, ads, stores
    axis: v("--chart-axis"),
    grid: v("--chart-grid"),
    crosshair: v("--chart-crosshair"),
    gap: v("--muted-foreground"),
    popover: v("--popover"),
    border: v("--border"),
    foreground: v("--foreground"),
    muted: v("--muted-foreground"),
    shadow: v("--shadow-popover"),
    sans: v("--font-geist-sans"),
    mono: v("--font-geist-mono"),
  };
}

/** The 45° hatch for gap bands (never colour alone): a faint wash with a diagonal line, tiled. */
export function hatch(color: string) {
  const tile = document.createElement("canvas");
  tile.width = tile.height = 6;
  const ctx = tile.getContext("2d");
  if (ctx) {
    ctx.fillStyle = color;
    ctx.globalAlpha = 0.1;
    ctx.fillRect(0, 0, 6, 6);
    ctx.globalAlpha = 0.45;
    ctx.strokeStyle = color;
    ctx.beginPath();
    ctx.moveTo(0, 6);
    ctx.lineTo(6, 0);
    ctx.stroke();
  }
  return { image: tile, repeat: "repeat" as const };
}

/** Axis styling shared by every chart: recessive grid, Geist Mono 11 px labels, no axis line or ticks. */
export const axisStyle = (t: ChartTokens) => ({
  axisLine: { show: false },
  axisTick: { show: false },
  axisLabel: { color: t.axis, fontFamily: t.mono, fontSize: 11 },
  splitLine: { lineStyle: { color: t.grid, width: 1 } },
});

/** Tooltip chrome from the popover tokens; tabular numbers; no movement transition. */
export const tooltipStyle = (t: ChartTokens) => ({
  transitionDuration: 0,
  confine: true,
  backgroundColor: t.popover,
  borderColor: t.border,
  padding: [8, 10],
  textStyle: { color: t.foreground, fontFamily: t.sans, fontSize: 12 },
  extraCssText: `border-radius:var(--radius);box-shadow:${t.shadow};font-variant-numeric:tabular-nums;`,
});
