"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";
import { useTheme } from "next-themes";
import { LineChart } from "echarts/charts";
import { AxisPointerComponent, GridComponent, MarkAreaComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

import { axisStyle, chartTokens, hatch, tooltipStyle, type ChartTokens } from "@/lib/charts/theme";
import { formatUtc } from "@/lib/format";

import { align, DAY, dayMs, LAYOUT, type ChartPane, type Point } from "./trends-model";

// Modular ECharts (DEC-026, DEC-245): only what this chart draws, loaded only with the Trends tab (next/dynamic).
echarts.use([LineChart, GridComponent, TooltipComponent, AxisPointerComponent, MarkAreaComponent, CanvasRenderer]);

const dayLabel = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
const fullDay = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const GAP = { gap: "collection gap", failed: "every run failed" } as const;

type Row = { pane: ChartPane; name: string; color: string; value: string; detail: string };

/** What every visible line says about day `k`: its value with source and as of, or why there is none. */
function rowsFor(panes: ChartPane[], aligned: (Point | null)[][][], days: string[], k: number, t: ChartTokens): Row[] {
  return panes.flatMap((pane, i) =>
    pane.lines.map((line, j) => {
      const point = aligned[i][j][k];
      const gap = line.series.gaps.find((g) => g.day === days[k]);
      const color = t.series[pane.color - 1];
      if (point) return { pane, name: line.name, color, value: pane.format(point), detail: `${line.series.source_name} · as of ${formatUtc(point.as_of)}` };
      return { pane, name: line.name, color, value: gap ? "No data" : "Not observed", detail: `${line.series.source_name} · ${gap ? GAP[gap.status] : "no capture that day"}` };
    }),
  );
}

function option(panes: ChartPane[], aligned: (Point | null)[][][], days: string[], t: ChartTokens, animate: boolean): echarts.EChartsCoreOption {
  const min = dayMs(days[0]);
  const max = dayMs(days[days.length - 1]) + DAY;
  const at = (k: number) => dayMs(days[k]) + DAY / 2; // a day's point sits mid-band, so its gap band centres on it
  const axis = axisStyle(t);
  return {
    animation: animate,
    animationDuration: 400,
    animationEasing: "cubicOut",
    animationDurationUpdate: 0,
    useUTC: true,
    textStyle: { fontFamily: t.sans },
    grid: panes.map((_, i) => ({ left: LAYOUT.left, right: LAYOUT.right, top: i * (LAYOUT.header + LAYOUT.pane) + LAYOUT.header + LAYOUT.inset, height: LAYOUT.pane - LAYOUT.inset })),
    axisPointer: { link: [{ xAxisIndex: "all" }], lineStyle: { color: t.crosshair, type: "dashed" }, label: { show: false } },
    xAxis: panes.map((_, i) => ({
      type: "time", gridIndex: i, min, max, ...axis, splitLine: { show: false },
      axisLabel: { ...axis.axisLabel, show: i === panes.length - 1, hideOverlap: true, formatter: (v: number) => dayLabel.format(v) },
      axisPointer: { snap: true },
    })),
    yAxis: panes.map((pane, i) => ({
      type: "value", gridIndex: i, position: "right", scale: pane.key === "price", boundaryGap: [0, "12%"], splitNumber: 2, ...axis,
      axisLabel: { ...axis.axisLabel, formatter: pane.tick },
    })),
    tooltip: {
      trigger: "axis",
      ...tooltipStyle(t),
      formatter: (params: { axisValue: number } | { axisValue: number }[]) => {
        const k = Math.floor(((Array.isArray(params) ? params[0] : params).axisValue - min) / DAY);
        if (!days[k]) return "";
        const rows = rowsFor(panes, aligned, days, k, t).map(
          (r) => `<div class="mt-1.5 flex items-baseline gap-4"><span class="flex items-center gap-1.5"><span class="inline-block size-2 rounded-sm" style="background:${r.color}"></span>${esc(r.name)}</span><b class="ml-auto font-mono font-medium">${esc(r.value)}</b></div><div class="text-micro text-muted-foreground">${esc(r.detail)}</div>`,
        );
        return `<div class="font-medium">${fullDay.format(dayMs(days[k]))} · UTC</div>${rows.join("")}`;
      },
    },
    series: panes.flatMap((pane, i) =>
      pane.lines.flatMap((line, j): object[] => {
        const points = aligned[i][j];
        const color = t.series[pane.color - 1];
        const lone = points.map((p, k) => p !== null && !points[k - 1] && !points[k + 1]); // a dot, or it wouldn't show
        const base = {
          type: "line", xAxisIndex: i, yAxisIndex: i, name: line.name, connectNulls: false, symbol: "circle", showSymbol: true,
          symbolSize: (_: unknown, p: { dataIndex: number }) => (lone[p.dataIndex] ? 5 : 0),
          lineStyle: { color, width: 2, type: line.dashed ? "dashed" : "solid" }, itemStyle: { color }, emphasis: { disabled: true },
        };
        const low = {
          ...base, data: points.map((p, k) => [at(k), p?.value ?? null]),
          markArea: j === 0 && pane.bands.length ? { silent: true, itemStyle: { color: hatch(t.gap) }, data: pane.bands.map((b) => [{ xAxis: b.from }, { xAxis: b.to }]) } : undefined,
        };
        if (!points.some((p) => p?.high != null)) return [low];
        // The price band: the lowest price, with the spread to the highest stacked on it and filled.
        return [
          { ...low, stack: pane.key },
          { ...base, name: `${line.name} (highest)`, stack: pane.key, lineStyle: { ...base.lineStyle, width: 1 }, areaStyle: { color, opacity: 0.1 },
            data: points.map((p, k) => [at(k), p && p.high != null ? p.high - p.value : null]) },
        ];
      }),
    ),
  };
}

/** The Trends panes on one canvas: shared UTC time axis, one crosshair and tooltip across panes, hatched gap bands.
 *  Draws once with motion, then redraws instantly (ranges never morph); no motion at all under reduced motion. */
export default function TrendsChart({ panes, days, summary }: { panes: ChartPane[]; days: string[]; summary: string }) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const drawn = useRef(false);
  const reduced = useReducedMotion();
  const { resolvedTheme } = useTheme();
  // The day the keyboard is on; a new window (range or panes) starts with none.
  const [cursor, setCursor] = useState<{ days: string[]; k: number } | null>(null);
  const focus = cursor?.days === days ? cursor.k : null;
  const setFocus = (k: number | null) => setCursor(k === null ? null : { days, k });
  const aligned = useMemo(() => panes.map((p) => p.lines.map((l) => align(l.series, days))), [panes, days]);

  useEffect(() => {
    const instance = echarts.init(el.current);
    chart.current = instance;
    const observer = new ResizeObserver(() => instance.resize());
    if (el.current) observer.observe(el.current);
    return () => {
      observer.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    // Tokens are read again on a theme change, so the canvas follows it.
    chart.current?.setOption(option(panes, aligned, days, chartTokens(), !drawn.current && !reduced), { notMerge: true });
    chart.current?.resize();
    drawn.current = true;
  }, [panes, aligned, days, resolvedTheme, reduced]);

  // ←/→ step the crosshair a day, Home/End jump, Esc hides it; the live region reads the same rows aloud.
  const onKeyDown = (e: React.KeyboardEvent) => {
    const last = days.length - 1;
    const next = { ArrowLeft: (focus ?? last + 1) - 1, ArrowRight: (focus ?? -1) + 1, Home: 0, End: last }[e.key];
    if (e.key === "Escape") {
      chart.current?.dispatchAction({ type: "hideTip" });
      setFocus(null);
    }
    if (next === undefined) return;
    e.preventDefault();
    const k = Math.max(0, Math.min(last, next));
    // By position, not data index: the first line may have no point that day, and the tooltip still explains why.
    const x = chart.current?.convertToPixel({ xAxisIndex: 0 }, dayMs(days[k]) + DAY / 2);
    chart.current?.dispatchAction({ type: "showTip", x, y: LAYOUT.header + LAYOUT.pane / 2 });
    setFocus(k);
  };
  const spoken = focus === null ? "" : `${fullDay.format(dayMs(days[focus]))} UTC. ${rowsFor(panes, aligned, days, focus, chartTokens()).map((r) => `${r.name}: ${r.value}, ${r.detail}`).join(". ")}`;

  return (
    <>
      <div
        ref={el}
        role="group"
        aria-roledescription="chart"
        aria-label={`${summary} Use the arrow keys to read each day.`}
        tabIndex={0}
        onKeyDown={onKeyDown}
        onBlur={() => {
          chart.current?.dispatchAction({ type: "hideTip" });
          setFocus(null);
        }}
        className="absolute inset-0 rounded-lg"
        data-testid="trends-canvas"
      />
      <p aria-live="polite" className="sr-only">
        {spoken}
      </p>
    </>
  );
}
