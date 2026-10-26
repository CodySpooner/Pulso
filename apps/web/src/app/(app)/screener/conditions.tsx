"use client";

import { useRef, useState } from "react";
import { AnimatePresence, useReducedMotion } from "motion/react";
import * as m from "motion/react-m";
import { DropdownMenu } from "radix-ui";
import { Check, Plus, X } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { $api } from "@/lib/api/client";
import { spring } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { conditionsOf, RANGES, STAGES, type Filters, type Range } from "./definition";

export type Key = Range | "lifecycle" | "category";
/** Changes the filters from the latest ones, so two quick edits both land. */
export type SetFilters = (update: (f: Filters) => Filters) => void;
const ORDER: Key[] = ["margin_bps", "lifecycle", "velocity", "acceleration", "saturation", "ship_days_us", "supplier_rating", "price", "category"];
const label = (key: Key) => (key === "lifecycle" ? "Lifecycle" : key === "category" ? "Category" : RANGES[key].label);
const cap = (s: string) => s[0].toUpperCase() + s.slice(1);
const UNITS: Record<string, (n: number) => string> = { "%": (n) => `${n}%`, USD: (n) => `$${n}`, "★": (n) => `${n}★`, days: (n) => `${n} days` };
export const menu =
  "z-50 min-w-52 rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-popover data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-96 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 duration-(--duration-fast)";
export const menuItem =
  "flex h-8 cursor-pointer items-center gap-2 rounded-md px-2 text-data outline-none select-none pointer-coarse:h-(--hit-target) data-highlighted:bg-accent data-disabled:cursor-default data-disabled:text-subtle-foreground";
const input =
  "h-(--button-h-md) w-full min-w-0 rounded-md border border-border bg-background px-2 text-data text-foreground tabular-nums transition-colors duration-(--duration-fast) placeholder:text-subtle-foreground hover:border-border-strong";

/** A condition in words: "Landed margin ≥ 40%", for the empty state's Remove buttons. */
export function describe(key: Key, f: Filters): string {
  if (key === "lifecycle") return `Lifecycle: ${f.lifecycle?.join(", ")}`;
  if (key === "category") return "Category";
  const { scale, unit } = RANGES[key];
  const [lo, hi] = [f[`${key}_min`], f[`${key}_max`]].map((v) => (v == null ? null : (UNITS[unit] ?? String)(v / scale)));
  return `${label(key)} ${lo && hi ? `${lo} to ${hi}` : lo ? `≥ ${lo}` : `≤ ${hi}`}`;
}

export function without(f: Filters, key: Key): Filters {
  const next = { ...f };
  if (key === "lifecycle" || key === "category") delete next[key];
  else {
    delete next[`${key}_min`];
    delete next[`${key}_max`];
  }
  return next;
}

/** First visit: three example conditions as chips (vault Features/Product Screener, States). */
const EXAMPLES: [string, Filters][] = [
  ["Landed margin ≥ 40%", { margin_bps_min: 4000 }],
  ["Ships to US in ≤ 10 days", { ship_days_us_max: 10 }],
  ["Emerging or rising", { lifecycle: ["emerging", "rising"] }],
];

// The filter builder: one row per condition, all combined with AND (DEC-336 b). Rows reflow with the layout pattern
// (Motion System pattern 5), opacity only under reduced motion. A typed bound applies on Enter or leaving the box.
export function Conditions({ filters, set, open, onOpenChange }: { filters: Filters; set: SetFilters; open: boolean; onOpenChange: (open: boolean) => void }) {
  const [added, setAdded] = useState<Key[]>([]);
  const adding = useRef<Key | null>(null);
  const addButton = useRef<HTMLButtonElement>(null);
  const given = conditionsOf(filters);
  const shown = ORDER.filter((k) => given.includes(k) || added.includes(k));
  const gone = useReducedMotion() ? { opacity: 0 } : { opacity: 0, scale: 0.9 };
  const remove = (key: Key) => {
    setAdded((a) => a.filter((k) => k !== key));
    set((f) => without(f, key));
    addButton.current?.focus();
  };
  return (
    <div className="flex flex-col gap-3">
      {shown.length === 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-data text-muted-foreground">Add your first filter, or start from one of these:</p>
          <div className="flex flex-wrap gap-1.5">
            {EXAMPLES.map(([text, example]) => (
              <Button key={text} size="sm" variant="secondary" onClick={() => set((f) => ({ ...f, ...example }))}>
                {text}
              </Button>
            ))}
          </div>
        </div>
      )}
      <ul aria-label="Conditions" className="flex flex-col gap-2 empty:hidden">
        <AnimatePresence initial={false}>
          {shown.map((key) => (
            <m.li key={key} data-condition={key} layout initial={gone} animate={{ opacity: 1, scale: 1 }} exit={gone} transition={spring.smooth} className="rounded-lg border border-border bg-card p-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-label font-medium text-foreground">{label(key)}</span>
                <button
                  type="button"
                  aria-label={`Remove ${label(key)}`}
                  onClick={() => remove(key)}
                  className="relative hit-area grid size-6 place-items-center rounded-sm text-muted-foreground transition-colors duration-(--duration-fast) hover:bg-accent hover:text-foreground"
                >
                  <X className="size-3.5" aria-hidden />
                </button>
              </div>
              <div className="mt-2">{key === "lifecycle" ? <Stages filters={filters} set={set} /> : key === "category" ? <CategoryPick filters={filters} set={set} /> : <Bounds metric={key} filters={filters} set={set} />}</div>
            </m.li>
          ))}
        </AnimatePresence>
      </ul>
      <DropdownMenu.Root open={open} onOpenChange={onOpenChange}>
        <DropdownMenu.Trigger asChild>
          <Button ref={addButton} size="sm" variant="secondary" aria-keyshortcuts="F" className="self-start">
            <Plus aria-hidden />
            Add filter
            <Kbd className="ml-1 max-md:hidden">F</Kbd>
          </Button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="start"
            sideOffset={4}
            className={menu}
            // The new condition's first control takes focus, not the trigger.
            onCloseAutoFocus={(e) => {
              if (!adding.current) return;
              e.preventDefault();
              document.querySelector<HTMLElement>(`[data-condition="${adding.current}"] :is(input, select, button[aria-pressed])`)?.focus();
              adding.current = null;
            }}
          >
            {ORDER.filter((k) => !shown.includes(k)).map((k) => (
              <DropdownMenu.Item
                key={k}
                className={menuItem}
                onSelect={() => {
                  adding.current = k;
                  setAdded((a) => [...a, k]);
                }}
              >
                {label(k)}
              </DropdownMenu.Item>
            ))}
            <DropdownMenu.Item disabled className={menuItem}>
              Risk
              <span className="ml-auto text-micro font-medium">Phase 5</span>
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      <p className="text-label text-subtle-foreground">Every condition must hold. A product missing a metric never passes its condition.</p>
    </div>
  );
}

function Bounds({ metric, filters, set }: { metric: Range; filters: Filters; set: SetFilters }) {
  const { label: name, unit } = RANGES[metric];
  return (
    <div className="flex items-center gap-1.5">
      <Bound metric={metric} bound="min" filters={filters} set={set} label={`${name}, at least (${unit})`} />
      <span aria-hidden className="text-subtle-foreground">
        –
      </span>
      <Bound metric={metric} bound="max" filters={filters} set={set} label={`${name}, at most (${unit})`} />
      <span className="w-14 shrink-0 text-label text-subtle-foreground">{unit}</span>
    </div>
  );
}

/** One bound, typed in the metric's display unit and stored in the API's. It keeps its draft while focused, so
 *  applying it never moves focus. */
function Bound({ metric, bound, filters, set, label: name }: { metric: Range; bound: "min" | "max"; filters: Filters; set: SetFilters; label: string }) {
  const key = `${metric}_${bound}` as const;
  const { scale, int } = RANGES[metric];
  const stored = filters[key] ?? null;
  const shown = stored === null ? "" : String(stored / scale);
  const [draft, setDraft] = useState(shown);
  const [seen, setSeen] = useState(shown);
  if (seen !== shown) {
    setSeen(shown);
    setDraft(shown);
  }
  const apply = () => {
    const typed = draft.trim() === "" ? null : Number(draft);
    if (typed !== null && !Number.isFinite(typed)) return setDraft(shown);
    const value = typed === null ? null : int ? Math.round(typed * scale) : typed * scale;
    if (value !== stored) set((f) => ({ ...f, [key]: value }));
  };
  return (
    <input
      type="number"
      inputMode="decimal"
      step="any"
      aria-label={name}
      placeholder={bound === "min" ? "Min" : "Max"}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={apply}
      onKeyDown={(e) => e.key === "Enter" && apply()}
      className={input}
    />
  );
}

function Stages({ filters, set }: { filters: Filters; set: SetFilters }) {
  const on = filters.lifecycle ?? [];
  return (
    <div role="group" aria-label="Lifecycle is any of" className="flex flex-wrap gap-1.5">
      {STAGES.map((stage) => (
        <button
          key={stage}
          type="button"
          aria-pressed={on.includes(stage)}
          onClick={() => {
            set((f) => {
              const next = STAGES.filter((s) => (s === stage) !== (f.lifecycle ?? []).includes(s));
              return { ...f, lifecycle: next.length ? next : null };
            });
          }}
          // Pressed is neutral with a check, so it never reads as a stage's status colour (design review).
          className="relative hit-area flex h-(--button-h-sm) items-center gap-1 rounded-md border border-border px-2 text-label text-muted-foreground transition-colors duration-(--duration-fast) hover:text-foreground aria-pressed:border-border-strong aria-pressed:bg-accent aria-pressed:font-medium aria-pressed:text-foreground"
        >
          {on.includes(stage) && <Check className="size-3" aria-hidden />}
          {cap(stage)}
        </button>
      ))}
    </div>
  );
}

function CategoryPick({ filters, set }: { filters: Filters; set: SetFilters }) {
  const categories = $api.useQuery("get", "/v1/categories", {}, { enabled: useApiReady(), staleTime: 5 * 60_000 });
  return (
    <select
      aria-label="Category is"
      value={String(filters.category ?? "")}
      onChange={(e) => set((f) => ({ ...f, category: e.target.value ? Number(e.target.value) : null }))}
      className={cn(input, "bg-secondary")}
    >
      <option value="">Choose a category</option>
      {categories.data?.map((c) => (
        <option key={c.id} value={c.id}>
          {c.path.replaceAll(" > ", " › ")}
        </option>
      ))}
      {filters.category != null && !categories.data?.some((c) => c.id === filters.category) && <option value={filters.category}>Category #{filters.category}</option>}
    </select>
  );
}
