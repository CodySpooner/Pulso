"use client";

import { useEffect, useId, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { keepPreviousData } from "@tanstack/react-query";
import { CircleSlash, PencilLine, RotateCcw, TriangleAlert, Truck } from "lucide-react";
import { Slider, ToggleGroup } from "radix-ui";

import { useApiReady } from "@/components/data-health/api";
import { PanelError, Pill, StaleLine, TapTooltip } from "@/components/data-health/atoms";
import { EmptyState } from "@/components/pulso/empty-state";
import { ProvenanceCard } from "@/components/pulso/metric";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, isProblem } from "@/lib/api/client";
import { formatAgo, formatDelta, formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import {
  cost, DEFAULTS, GAPS, money, needs, parseMinor, pct, priceRange, reasons, request, share, signedMoney, toInput,
  type Calc, type Missing, type Scenario, type Trace,
} from "./model";
import { parseSupplier, supplierSearch } from "../suppliers/model";

const tile = "flex min-w-0 flex-col rounded-lg border border-border-subtle bg-background/40";
const field = "h-(--input-h) w-full min-w-0 rounded-md border border-input bg-background px-2.5 text-body text-foreground";
const link = "link-inline rounded-sm underline decoration-border-strong underline-offset-2 hover:decoration-current";
const tones = { positive: "text-positive", negative: "text-negative", neutral: "text-foreground" };
const ROUNDING = "Each line is rounded to the cent once and totals add the rounded lines, so the breakdown always sums.";
const LABELS: Record<string, string> = {
  price_minor: "Sell price",
  unit_cost: "Unit cost",
  fx_unit_cost: "FX rate for the unit cost",
  freight: "Freight quote",
  fx_freight: "FX rate for the freight",
  duty_bps: "Duty rate",
  customs_fee_minor: "Customs fee",
  payment_fee_bps: "Payment fee rate",
  payment_fee_fixed_minor: "Payment fee per order",
  shopify_fee_bps: "Transaction fee rate",
  returns_bps: "Returns rate",
  ad_cost_minor: "Ad cost per order",
};

function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

// UX-8 part b (vault Features/Product Page - Profit, DEC-256): scenario inputs, three results and the landed-cost
// breakdown, each number from POST /v1/profit/calc with its source on hover. A slider move recomputes on the server
// after 120 ms; the last result stays, dimmed, until the new one arrives. An incomplete row shows why, never a margin
// from partial costs (R-16).
export function ProfitTab({ id }: { id: string }) {
  const [scenario, setScenario] = useState<Scenario>(DEFAULTS);
  const [typed, setTyped] = useState<number | null>(null); // the price slider's anchor when no store has a price
  const [resets, setResets] = useState(0);
  const settled = useDebounced(scenario, 120);
  const options = { enabled: useApiReady(), retry: (failures: number, error: unknown) => !(isProblem(error) && error.status < 500) && failures < 1 };
  // The defaults (Settings and the market price, as the endpoint applies them) seed the inputs and Reset.
  const supplier = parseSupplier(useSearchParams()); // the Suppliers tab's choice (DEC-264)
  const base = $api.useQuery("post", "/v1/profit/calc", { body: request(id, DEFAULTS, supplier) }, options);
  const calc = $api.useQuery("post", "/v1/profit/calc", { body: request(id, settled, supplier) }, { ...options, placeholderData: keepPreviousData });
  // The last answer outlives a failed recompute, so the result never blanks (vault Design/UI States, Refreshing).
  const [last, setLast] = useState<{ calc: Calc; at: number } | null>(null);
  if (calc.data && !calc.isPlaceholderData && calc.data !== last?.calc) setLast({ calc: calc.data, at: calc.dataUpdatedAt });
  const shown = calc.data ?? last?.calc;
  const defaults = base.data ?? shown;
  const retry = () => void calc.refetch();
  const recomputing = settled !== scenario || calc.isPlaceholderData || (calc.isError && !!last);
  const set = (change: Partial<Scenario>) => setScenario((s) => ({ ...s, ...change }));
  const reset = () => {
    setScenario(DEFAULTS);
    setTyped(null);
    setResets((n) => n + 1);
  };

  return (
    <div className="relative flex flex-col gap-4 p-4">
      <h2 className="sr-only">Profit</h2>
      {!shown || !defaults ? (
        calc.isError ? (
          <>
            <PanelError headingLevel="h2" size="md" title="Couldn't calculate profit" error={calc.error} retry={retry} />
            {supplier !== null && <BestMarginLink />}
          </>
        ) : (
          <ProfitSkeleton />
        )
      ) : shown.supplier_listing_id === null ? (
        <EmptyState
          icon={Truck}
          headingLevel="h2"
          title="No supplier cost yet"
          action={
            <Button asChild variant="secondary">
              <Link href="/admin/data-health">Import a CSV in Data Health</Link>
            </Button>
          }
        >
          Pulso costs a product from a matched supplier listing: its unit cost, an exact US freight quote, duty and your fees. When the
          matcher links a CJ listing, or you import one, its landed cost shows here.
        </EmptyState>
      ) : (
        <>
          {/* A 2 px hairline while a recompute is out: opacity only (vault Features/Product Page - Profit, Motion). The last
              answer stays at full contrast, no dim (imp-314); aria-busy marks it for assistive tech. */}
          <span
            aria-hidden
            className={cn(
              "pointer-events-none absolute inset-x-4 top-0 h-0.5 rounded-full bg-brand opacity-0 transition-opacity duration-(--duration-fast)",
              recomputing && !calc.isError && "opacity-100",
            )}
          />
          {calc.isError && last && <StaleLine boxed what="Couldn't recompute this scenario" error={calc.error} asOf={last.at} retry={retry} />}
          <StaleInputs calc={shown} now={last?.at ?? calc.dataUpdatedAt} />
          {!shown.complete && <Withheld calc={shown} />}
          <div aria-busy={recomputing}>
            <Results calc={shown} now={last?.at ?? calc.dataUpdatedAt} />
          </div>
          <div className="grid items-start gap-4 lg:grid-cols-[17rem_minmax(0,1fr)]">
            <ScenarioPanel
              key={resets}
              scenario={scenario}
              set={set}
              defaults={defaults}
              shown={shown}
              typed={typed}
              setTyped={setTyped}
              reset={reset}
              chosen={supplier !== null}
            />
            <div aria-busy={recomputing} className="min-w-0">
              <Breakdown calc={shown} now={last?.at ?? calc.dataUpdatedAt} />
            </div>
          </div>
          <p aria-live="polite" className="sr-only">
            {summary(shown)}
          </p>
        </>
      )}
    </div>
  );
}

function summary(calc: Calc): string {
  if (calc.net_minor === null || calc.net_bps === null) return `Profit withheld. ${needs(calc)}.`;
  return `Profit per order ${signedMoney(calc.net_minor).text}, margin ${formatDelta(calc.net_bps / 100, "up").text}%.`;
}

/** A number that opens its provenance on hover, focus and tap, styled like `<Metric>` (DEC-238 f). */
export function Amount({ label, text, hint, className, children }: { label: string; text: string; hint: React.ReactNode; className?: string; children?: React.ReactNode }) {
  return (
    <TapTooltip
      hint={<div className="flex flex-col gap-2.5 py-0.5">{hint}</div>}
      side="bottom"
      contentClassName="pointer-events-auto max-w-72 px-3 py-2"
      type="button"
      aria-label={`${label}: ${text}`}
      className={cn("relative hit-area cursor-help rounded-sm tabular-nums decoration-border-strong decoration-dotted underline-offset-4 hover:underline", className)}
    >
      {children ?? text}
    </TapTooltip>
  );
}

/** One input's provenance: an observation's source, as-of and raw payload, or where an owner input comes from. */
function TraceCard({ name, trace, now }: { name: string; trace: Trace; now: number }) {
  const label = LABELS[name] ?? name;
  if (trace.as_of)
    // ProvenanceCard reads only the trace; the value it would show is the line's own amount.
    return <ProvenanceCard label={label} now={now} stat={{ ...trace, as_of: trace.as_of, value: 0, method: null }} />;
  return (
    <div className="flex flex-col gap-1 py-0.5">
      <p className="font-medium text-foreground">{label}</p>
      <p className="text-muted-foreground">
        {trace.source === "owner_estimate"
          ? "Your estimate for this scenario. Reset to defaults to use Settings again."
          : "Workspace settings. Settings keep no change history yet, so there is no as-of time."}
      </p>
    </div>
  );
}

const traces = (calc: Calc, ...names: string[]) => names.flatMap((name) => (calc.sources[name] ? [[name, calc.sources[name]] as const] : []));
type Traces = ReturnType<typeof traces>;

export function Computed({ formula, calc, now }: { formula: string; calc: Calc; now: number }) {
  const observed = Object.values(calc.sources).filter((t) => t.as_of);
  const oldest = observed.sort((a, b) => Date.parse(a.as_of!) - Date.parse(b.as_of!))[0];
  return (
    <div className="flex flex-col gap-1 py-0.5">
      <p className="font-medium text-foreground">Computed by Pulso</p>
      <p className="text-muted-foreground">
        {formula} {ROUNDING}
      </p>
      {oldest?.as_of && (
        <p className="text-muted-foreground">
          Oldest input: {oldest.source_name}, <time dateTime={oldest.as_of}>{formatUtc(oldest.as_of)}</time> · {formatAgo(oldest.as_of, now)}
        </p>
      )}
    </div>
  );
}

const NET = "Sell price − landed cost − fees − returns − ad cost.";
export const MARGIN = "Sell price − landed cost − fees − returns: the most an order's ads can cost before it loses money.";

function Results({ calc, now }: { calc: Calc; now: number }) {
  const withheld = <span className="font-sans text-body font-normal text-muted-foreground">Withheld</span>;
  const detail = calc.complete ? null : needs(calc);
  const net = calc.net_minor !== null ? signedMoney(calc.net_minor) : null;
  const margin = calc.net_bps !== null ? formatDelta(calc.net_bps / 100, "up") : null;
  const breakEven = calc.margin_minor;
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      <Result label="Profit per order" detail={detail ?? `after ${money(calc.ad_cost_minor)} ad cost`}>
        {net ? (
          <Amount label="Profit per order" text={net.text} hint={<Computed formula={NET} calc={calc} now={now} />} className={tones[net.tone]}>
            {net.glyph && <span aria-hidden className="mr-1 text-[0.7em]">{net.glyph}</span>}
            {net.text}
          </Amount>
        ) : (
          withheld
        )}
      </Result>
      <Result label="Margin" detail={detail ?? `${share(calc.margin_bps!, 10_000)} before ads`}>
        {margin ? (
          <Amount label="Margin" text={`${margin.text}%`} hint={<Computed formula={`(${NET}) ÷ sell price.`} calc={calc} now={now} />} className={tones[margin.tone]}>
            {margin.glyph && <span aria-hidden className="mr-1 text-[0.7em]">{margin.glyph}</span>}
            {margin.text}%
          </Amount>
        ) : (
          withheld
        )}
      </Result>
      <Result
        label="Break-even ad cost"
        className="col-span-2 sm:col-span-1"
        detail={detail ?? (breakEven! > 0 ? "profit before ads: the most ads can cost" : "loses money before any ad cost")}
      >
        {breakEven !== null ? (
          <Amount label="Break-even ad cost" text={signedMoney(breakEven).text} hint={<Computed formula={MARGIN} calc={calc} now={now} />} className={cn(breakEven <= 0 && "text-negative")}>
            {breakEven > 0 ? money(breakEven) : signedMoney(breakEven).text}
          </Amount>
        ) : (
          withheld
        )}
      </Result>
    </dl>
  );
}

function Result({ label, detail, className, children }: { label: string; detail: string; className?: string; children: React.ReactNode }) {
  return (
    <div className={cn(tile, "gap-1 px-4 py-3", className)}>
      <dt className="text-label text-muted-foreground">{label}</dt>
      <dd className="font-mono text-stat-lg font-semibold text-foreground">{children}</dd>
      <dd className="text-micro text-subtle-foreground">{detail}</dd>
    </div>
  );
}

/** R-16: what the margin waits for, in plain words. Never a margin from partial costs. */
function Withheld({ calc }: { calc: Calc }) {
  const words = reasons(calc);
  return (
    <section aria-labelledby="withheld-title" className="rounded-lg border border-warning/40 bg-warning-muted px-4 py-3 text-data text-foreground">
      <h3 id="withheld-title" className="font-medium">
        <TriangleAlert className="mr-1.5 inline size-3.5 align-[-2px] text-warning" aria-hidden />
        Profit and margin are withheld
      </h3>
      <p className="mt-0.5">Pulso never shows a margin from partial costs. {words.length === 1 ? "One input is missing:" : `${words.length} inputs are missing:`}</p>
      <ul className="mt-1.5 flex list-disc flex-col gap-1 pl-5">
        {words.map((w) => (
          <li key={w}>{w}</li>
        ))}
      </ul>
      {calc.missing.includes("duty_not_set") && (
        <p className="mt-2">
          <Link href="/settings" className={link}>
            Set a US duty rate in Settings
          </Link>
        </p>
      )}
    </section>
  );
}

function StaleInputs({ calc, now }: { calc: Calc; now: number }) {
  const stale = [...new Map(Object.values(calc.sources).filter((t) => t.stale && t.as_of).map((t) => [t.source, t])).values()];
  if (!stale.length) return null;
  return (
    <p className="rounded-lg border border-warning/40 bg-warning-muted px-4 py-2.5 text-data text-foreground">
      <TriangleAlert className="mr-1.5 inline size-3.5 align-[-2px] text-warning" aria-hidden />
      <span className="font-medium">Some inputs are older than expected.</span>{" "}
      {stale.map((t) => `${t.source_name} last captured ${formatUtc(t.as_of!)} (${formatAgo(t.as_of!, now)})`).join("; ")}. The collector
      host may be off or the source paused.{" "}
      <Link href="/admin/data-health" className={cn(link, "whitespace-nowrap")}>
        Open Data Health
      </Link>
    </p>
  );
}

function ScenarioPanel({
  scenario,
  set,
  defaults,
  shown,
  typed,
  setTyped,
  reset,
  chosen,
}: {
  scenario: Scenario;
  set: (change: Partial<Scenario>) => void;
  defaults: Calc;
  shown: Calc;
  typed: number | null;
  setTyped: (minor: number) => void;
  reset: () => void;
  chosen: boolean;
}) {
  const changed = (["price", "returns", "fee", "ad"] as const).some((k) => scenario[k] !== undefined) || scenario.quantity !== 1;
  const supplier = shown.sources.unit_cost?.source_name ?? "matched supplier";
  return (
    <section aria-labelledby="scenario-title" className={cn(tile, "gap-5 p-4")}>
      <div className="flex items-center justify-between gap-2">
        <h3 id="scenario-title" className="text-body font-medium text-foreground">
          Scenario
        </h3>
        <Button variant="ghost" size="sm" onClick={reset} disabled={!changed}>
          <RotateCcw aria-hidden />
          Reset to defaults
        </Button>
      </div>
      <PriceField scenario={scenario} set={set} reference={defaults.price_minor} typed={typed} setTyped={setTyped} />
      <div className="flex flex-col gap-2">
        <span id="quantity-label" className="text-label text-muted-foreground">
          Units per order
        </span>
        <ToggleGroup.Root
          type="single"
          value={String(scenario.quantity)}
          onValueChange={(v) => v && set({ quantity: Number(v) })}
          aria-labelledby="quantity-label"
          className="grid grid-cols-4 gap-0.5 rounded-md border border-border bg-secondary p-0.5"
        >
          {[1, 2, 3, 4].map((n) => (
            <ToggleGroup.Item
              key={n}
              value={String(n)}
              aria-label={`${n} ${n === 1 ? "unit" : "units"}`}
              className="relative hit-area h-(--button-h-sm) rounded-[calc(var(--radius-md)-2px)] font-mono text-label text-muted-foreground tabular-nums transition-colors duration-(--duration-fast) hover:text-foreground data-[state=on]:text-foreground data-[state=on]:segment-thumb"
            >
              {n}
            </ToggleGroup.Item>
          ))}
        </ToggleGroup.Root>
      </div>
      <RateField
        label="Returns"
        value={scenario.returns ?? defaults.returns_bps}
        changed={scenario.returns !== undefined}
        max={Math.max(2500, defaults.returns_bps)}
        step={50}
        format={pct}
        onChange={(v) => set({ returns: v })}
        note="of the price refunded"
      />
      <RateField
        label="Payment fee"
        value={scenario.fee ?? defaults.payment_fee_bps}
        changed={scenario.fee !== undefined}
        max={Math.max(1000, defaults.payment_fee_bps)}
        step={10}
        format={pct}
        onChange={(v) => set({ fee: v })}
        note={`plus ${money(defaults.payment_fee_fixed_minor)} per order`}
      />
      <RateField
        label="Ad cost per order"
        value={scenario.ad ?? defaults.ad_cost_minor}
        changed={scenario.ad !== undefined}
        max={Math.max(6000, defaults.ad_cost_minor)}
        step={50}
        format={(v) => money(v)}
        onChange={(v) => set({ ad: v })}
        note="your CPA"
      />
      <p className="text-micro text-subtle-foreground">
        Costed from the {supplier} listing{" "}
        {/* Sold out: the chosen listing, or the default's when none is in stock (imp-351, DEC-291). */}
        {!shown.in_stock && (
          <>
            <Pill tone="negative" icon={CircleSlash} className="align-middle">
              Out of stock
            </Pill>{" "}
          </>
        )}
        {chosen ? "you opened from Suppliers" : `with the best complete margin${shown.in_stock ? "" : "; none is in stock"}`}. Defaults come from{" "}
        <Link href="/settings" className={link}>
          Settings
        </Link>
        .
      </p>
      {chosen && <BestMarginLink />}
    </section>
  );
}

function PriceField({
  scenario,
  set,
  reference,
  typed,
  setTyped,
}: {
  scenario: Scenario;
  set: (change: Partial<Scenario>) => void;
  reference: number | null;
  typed: number | null;
  setTyped: (minor: number) => void;
}) {
  const id = useId();
  const [draft, setDraft] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);
  const q = scenario.quantity;
  // A one-unit store price never prices a q-unit order (DEC-246 f): above 1 unit the owner enters it.
  const price = scenario.price ?? (q === 1 ? reference : null);
  const anchor = reference !== null ? reference * q : typed;
  const commit = () => {
    if (draft === null) return;
    if (draft.trim() === "") {
      setDraft(null);
      set({ price: undefined });
      return;
    }
    const minor = parseMinor(draft);
    if (!minor) return setInvalid(true);
    setDraft(null);
    set({ price: minor });
    if (anchor === null) setTyped(minor);
  };
  const hint = invalid
    ? "Enter a price like 29.99."
    : scenario.price !== undefined
      ? null
      : price !== null
        ? "Median live store price"
        : reference !== null
          ? `Enter the price of a ${q}-unit order`
          : "No market price yet: enter one";
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-label text-muted-foreground">
        Sell price{q > 1 && ` (${q} units)`}
      </label>
      <div className="relative">
        <span aria-hidden className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-body text-subtle-foreground">
          $
        </span>
        <input
          id={id}
          value={draft ?? (price === null ? "" : toInput(price))}
          onChange={(e) => {
            setDraft(e.target.value);
            setInvalid(false);
            const minor = parseMinor(e.target.value);
            if (minor) set({ price: minor });
          }}
          onBlur={commit}
          onKeyDown={(e) => e.key === "Enter" && commit()}
          inputMode="decimal"
          autoComplete="off"
          enterKeyHint="done"
          placeholder="0.00"
          aria-invalid={invalid}
          aria-describedby={`${id}-hint`}
          className={cn(field, "pl-6 font-mono tabular-nums")}
        />
      </div>
      {anchor !== null && price !== null && (
        <ScenarioSlider
          label="Sell price"
          value={price}
          {...priceRange(anchor)}
          format={(v) => money(v)}
          onChange={(v) => {
            setDraft(null);
            setInvalid(false);
            set({ price: v });
          }}
        />
      )}
      <p id={`${id}-hint`} className={cn("text-micro", invalid ? "text-negative" : "text-subtle-foreground")}>
        {hint ?? <EstimateChip />}
      </p>
    </div>
  );
}

const EstimateChip = () => (
  <Pill tone="info" icon={PencilLine}>
    Your estimate
  </Pill>
);

function RateField({
  label,
  value,
  changed,
  max,
  step,
  format,
  onChange,
  note,
}: {
  label: string;
  value: number;
  changed: boolean;
  max: number;
  step: number;
  format: (v: number) => string;
  onChange: (v: number) => void;
  note: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-label text-muted-foreground">{label}</span>
        <span className="font-mono text-data text-foreground tabular-nums">{format(value)}</span>
      </div>
      <ScenarioSlider label={label} value={value} min={0} max={max} step={step} format={format} onChange={onChange} />
      <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-micro text-subtle-foreground">
        {changed ? <EstimateChip /> : "Settings"} · {note}
      </p>
    </div>
  );
}

/** Radix Slider: arrows move one step, Shift + arrow or Page Up/Down ten, Home/End the ends; the value is read out
 *  with its unit. The thumb follows the pointer without easing (vault Features/Product Page - Profit, Motion). */
function ScenarioSlider({
  label,
  value,
  min,
  max,
  step,
  format,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  onChange: (v: number) => void;
}) {
  const shown = Math.min(max, Math.max(min, value));
  return (
    <Slider.Root
      value={[shown]}
      min={min}
      max={max}
      step={step}
      onValueChange={([v]) => onChange(v)}
      className="relative flex h-5 w-full touch-none items-center select-none"
    >
      <Slider.Track className="relative h-1 grow overflow-hidden rounded-full bg-border">
        <Slider.Range className="absolute h-full bg-brand" />
      </Slider.Track>
      <Slider.Thumb
        aria-label={label}
        aria-valuetext={format(shown)}
        className="relative hit-area block size-4 cursor-grab rounded-full border-2 border-brand bg-background shadow-card active:cursor-grabbing"
      />
    </Slider.Root>
  );
}

interface Line {
  label: string;
  detail?: string;
  minor: number | null;
  /** costs read with a minus; landed cost and the profits are totals, under a rule */
  kind: "price" | "cost" | "landed" | "profit";
  strong?: boolean;
  traces?: Traces;
  /** the codes that would leave this line empty, most specific first */
  gaps?: Missing[];
  /** a total's share from the server's basis points (margin_bps, net_bps), not recomputed here */
  bps?: number | null;
  formula?: string;
}

function lines(calc: Calc): Line[] {
  const q = calc.quantity;
  const days = calc.freight_min_days === null ? null : calc.freight_min_days === calc.freight_max_days || calc.freight_max_days === null ? `${calc.freight_min_days} days` : `${calc.freight_min_days}–${calc.freight_max_days} days`;
  return [
    { label: "Sell price", detail: q > 1 ? `${q} units` : undefined, minor: calc.price_minor, kind: "price", traces: traces(calc, "price_minor"), gaps: ["price_missing"] },
    { label: q > 1 ? `Unit cost × ${q}` : "Unit cost", minor: calc.goods_minor, kind: "cost", traces: traces(calc, "unit_cost", "fx_unit_cost"), gaps: ["supplier_cost_missing", "amount_out_of_range", "fx_missing"] },
    {
      label: "Freight",
      detail: [calc.method, days].filter(Boolean).join(" · ") || undefined,
      minor: calc.freight_minor,
      kind: "cost",
      traces: traces(calc, "freight", "fx_freight"),
      gaps: ["freight_variant_mismatch", "freight_missing", "amount_out_of_range", "fx_missing"],
    },
    {
      label: "Duty",
      detail: calc.ddp ? "included (DDP)" : calc.duty_bps !== null ? `${pct(calc.duty_bps)} of goods` : undefined,
      minor: calc.duty_minor,
      kind: "cost",
      traces: traces(calc, "duty_bps"),
      gaps: ["duty_not_set", "supplier_cost_missing", "fx_missing", "amount_out_of_range"],
    },
    { label: "Customs fee", detail: "per order", minor: calc.customs_fee_minor, kind: "cost", traces: traces(calc, "customs_fee_minor") },
    { label: "Landed cost", minor: calc.landed_cost_minor, kind: "landed", formula: "Unit cost + freight + duty + customs fee." },
    {
      label: "Payment fee",
      detail: `${pct(calc.payment_fee_bps)} + ${money(calc.payment_fee_fixed_minor)}`,
      minor: calc.payment_fee_minor,
      kind: "cost",
      traces: traces(calc, "payment_fee_bps", "payment_fee_fixed_minor"),
      gaps: ["price_missing", "amount_out_of_range"],
    },
    { label: "Transaction fee", detail: pct(calc.shopify_fee_bps), minor: calc.shopify_fee_minor, kind: "cost", traces: traces(calc, "shopify_fee_bps"), gaps: ["price_missing"] },
    { label: "Returns allowance", detail: pct(calc.returns_bps), minor: calc.returns_minor, kind: "cost", traces: traces(calc, "returns_bps"), gaps: ["price_missing"] },
    { label: "Profit before ads", minor: calc.margin_minor, kind: "profit", bps: calc.margin_bps, formula: MARGIN },
    { label: "Ad cost", detail: "per order", minor: calc.ad_cost_minor, kind: "cost", traces: traces(calc, "ad_cost_minor") },
    { label: "Profit per order", minor: calc.net_minor, kind: "profit", strong: true, bps: calc.net_bps, formula: NET },
  ];
}

function Breakdown({ calc, now }: { calc: Calc; now: number }) {
  const fx = traces(calc, "fx_unit_cost", "fx_freight");
  const fxMissing = calc.missing.includes("fx_missing");
  return (
    <section aria-labelledby="breakdown-title" className="min-w-0">
      <h3 id="breakdown-title" className="mb-1 text-body font-medium text-foreground">
        Per order
      </h3>
      <table className="w-full border-collapse text-data">
        <thead>
          <tr className="text-micro text-subtle-foreground">
            <th scope="col" className="py-1.5 text-left font-normal">
              Line
            </th>
            <th scope="col" className="py-1.5 text-right font-normal">
              Amount
            </th>
            <th scope="col" className="py-1.5 pl-3 text-right font-normal sm:whitespace-nowrap">
              <abbr title="Share of the sell price" className="no-underline">
                % of price
              </abbr>
            </th>
            <th scope="col" className="hidden py-1.5 pl-4 text-left font-normal sm:table-cell">
              Source
            </th>
          </tr>
        </thead>
        <tbody>
          {lines(calc).map((line) => (
            <LineRow key={line.label} line={line} calc={calc} now={now} />
          ))}
          <tr className="border-t border-border-subtle">
            <th scope="row" className="py-1.5 pr-3 text-left font-normal">
              <span className="text-foreground">FX</span>
              <span className="ml-1.5 text-micro text-subtle-foreground">
                {fx.length ? "at the rate for each price's UTC date" : fxMissing ? "no rate within 4 days" : "supplier prices in USD"}
              </span>
            </th>
            <td className="py-1.5 text-right whitespace-nowrap">
              {fx.length ? (
                <Amount label="FX" text={fx.length === 1 ? "1 rate" : `${fx.length} rates`} hint={fx.map(([n, t]) => <TraceCard key={n} name={n} trace={t} now={now} />)} />
              ) : fxMissing ? (
                <Gap text={GAPS.fx_missing} />
              ) : (
                <span className="text-subtle-foreground">None needed</span>
              )}
            </td>
            <td />
            <td className="hidden py-1.5 pl-4 sm:table-cell">{fx.length > 0 && <SourceTag traces={fx} now={now} />}</td>
          </tr>
        </tbody>
      </table>
    </section>
  );
}

function LineRow({ line, calc, now }: { line: Line; calc: Calc; now: number }) {
  const gap = line.gaps?.find((code) => calc.missing.includes(code));
  const total = line.kind === "landed" || line.kind === "profit";
  const m = line.minor;
  const text = m === null ? "" : line.kind === "price" ? money(m) : line.kind === "profit" ? (m < 0 ? signedMoney(m).text : money(m)) : cost(m);
  // A profit's share is the server's basis points; any other line's is display arithmetic on two returned amounts.
  const ratio = m === null || calc.price_minor === null ? null : line.bps !== undefined ? line.bps !== null && share(line.bps, 10_000) : share(m, calc.price_minor);
  const source = line.traces?.length ? <SourceTag traces={line.traces} now={now} /> : total ? <span className="text-subtle-foreground">Pulso</span> : null;
  return (
    <tr className={cn("border-t", total ? "border-border" : "border-border-subtle", line.strong && "text-body")}>
      <th scope="row" className={cn("py-1.5 pr-3 text-left align-top", total ? "font-medium" : "font-normal")}>
        <span className="text-foreground">{line.label}</span>
        {line.detail && <span className="ml-1.5 text-micro font-normal text-subtle-foreground">{line.detail}</span>}
        {source && <span className="block text-micro font-normal sm:hidden">{source}</span>}
      </th>
      <td className={cn("py-1.5 text-right align-top font-mono whitespace-nowrap tabular-nums", total && "font-medium", line.kind === "profit" && m !== null && m < 0 && "text-negative")}>
        {m === null ? (
          gap && !total ? <Gap text={GAPS[gap]} /> : <span className="font-sans text-muted-foreground">Withheld</span>
        ) : (
          <Amount
            label={line.label}
            text={text}
            className="text-right"
            hint={line.formula ? <Computed formula={line.formula} calc={calc} now={now} /> : line.traces?.map(([n, t]) => <TraceCard key={n} name={n} trace={t} now={now} />)}
          />
        )}
      </td>
      <td className="py-1.5 pl-3 text-right align-top font-mono text-muted-foreground tabular-nums">{ratio}</td>
      <td className="hidden py-1.5 pl-4 align-top text-micro sm:table-cell">{source}</td>
    </tr>
  );
}

function Gap({ text }: { text: string }) {
  return (
    <span className="font-sans whitespace-nowrap text-warning">
      <TriangleAlert className="mr-1 inline size-3.5 align-[-2px]" aria-hidden />
      {text}
    </span>
  );
}

/** Where a line's main input comes from: an observation with its age (amber when stale), Settings, or your estimate. */
function SourceTag({ traces: [[, main]], now }: { traces: Traces; now: number }) {
  if (main.source === "owner_estimate") return <EstimateChip />;
  if (!main.as_of) return <span className="text-subtle-foreground">Settings</span>;
  return (
    <span className={cn("whitespace-nowrap", main.stale ? "text-warning" : "text-subtle-foreground")}>
      {main.stale && <TriangleAlert className="mr-1 inline size-3 align-[-2px]" aria-hidden />}
      {main.source_name} · {formatAgo(main.as_of, now)}
      {main.stale && " · stale"}
    </span>
  );
}

function ProfitSkeleton() {
  return (
    <>
      <span className="sr-only" role="status">
        Calculating profit…
      </span>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className={cn(tile, "gap-2 px-4 py-3", i === 2 && "col-span-2 sm:col-span-1")}>
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-7 w-20" />
            <Skeleton className="h-3 w-32" />
          </div>
        ))}
      </div>
      <div className="grid items-start gap-4 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <div className={cn(tile, "gap-6 p-4")}>
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="flex flex-col gap-2.5">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-1.5 w-full" />
            </div>
          ))}
        </div>
        <div className="flex flex-col gap-2">
          {Array.from({ length: 10 }, (_, i) => (
            <Skeleton key={i} className="h-6 w-full" />
          ))}
        </div>
      </div>
    </>
  );
}

/** Back to the server's pick: drops `supplier=` from the URL, like the tab bar, with no history entry. */
function BestMarginLink() {
  const clear = () => {
    const query = supplierSearch(window.location.search, null);
    window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
  };
  return (
    <button type="button" onClick={clear} className={cn(link, "relative hit-area self-start text-micro")}>
      Let Pulso pick the supplier
    </button>
  );
}
