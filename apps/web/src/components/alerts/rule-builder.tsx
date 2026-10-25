"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { BellPlus, Check, CircleCheck } from "lucide-react";

import { money } from "@/app/(app)/products/[id]/profit/model";
import { useApiReady } from "@/components/data-health/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { $api } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { useRuleWrites } from "./api";
import { autoName, createBody, draftOf, fieldErrors, hasPct, patchBody, targetOf, VERBS, type Draft, type Rule, type RuleType } from "./model";

const field =
  "h-(--button-h-md) min-w-0 rounded-md border border-border bg-secondary px-2.5 text-data text-foreground transition-colors duration-(--duration-fast) hover:border-border-strong aria-invalid:border-negative max-sm:w-full";
const fixed = "rounded-md border border-border-subtle bg-background/40 px-2.5 py-1 font-medium text-foreground";
const chip = "inline-flex h-6 items-center gap-1 rounded-sm border px-2 text-label";

interface Props {
  /** A new rule on this product (the Product Page's Create alert). */
  product?: { id: string; name: string };
  /** Or an edit of this rule: its type and target are fixed (the API's PATCH takes neither). */
  rule?: Rule;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved?: (rule: Rule) => void;
}

/** The Product Page's Create alert: the builder opens on this product with a 5% supplier price change filled in, so a
 *  rule is two clicks. The new rule's name stays beside the button with a link to the Rules tab. */
export function CreateAlert({ product }: { product: { id: string; name: string } }) {
  const [open, setOpen] = useState(false);
  const [made, setMade] = useState<Rule | null>(null);
  return (
    <div className="flex flex-col items-start gap-1.5 sm:items-end">
      <Button onClick={() => setOpen(true)}>
        <BellPlus aria-hidden />
        Create alert
      </Button>
      <p role="status" className="max-w-xs text-label text-muted-foreground empty:hidden sm:text-right">
        {made && (
          <>
            <CircleCheck className="mr-1 inline size-3.5 align-[-2px] text-positive" aria-hidden />
            {made.name} is on.{" "}
            <Link href="/alerts?view=rules" className="link-inline rounded-sm font-medium text-foreground underline decoration-border-strong underline-offset-2 hover:decoration-current">
              View rules
            </Link>
          </>
        )}
      </p>
      <RuleBuilder product={product} open={open} onOpenChange={setOpen} onSaved={setMade} />
    </div>
  );
}

/** DialogContent props that give focus back to whatever had it when the dialog opened, Escape included: Radix only
 *  returns it to a Dialog.Trigger, and these dialogs open from state. */
export function useReturnFocus() {
  const opener = useRef<HTMLElement | null>(null);
  return {
    onOpenAutoFocus: () => void (opener.current = document.activeElement as HTMLElement | null),
    onCloseAutoFocus: (e: Event) => {
      e.preventDefault();
      opener.current?.focus();
    },
  };
}

/** WF-4c (DEC-339): the sentence-style rule builder. A dialog; on a phone, a full-height sheet with the fields stacked. */
export function RuleBuilder({ product, rule, open, onOpenChange, onSaved }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        {...useReturnFocus()}
        className="sm:w-[min(36rem,calc(100vw-2rem))] max-sm:inset-0 max-sm:h-dvh max-sm:w-full max-sm:translate-0 max-sm:rounded-none max-sm:border-0 max-sm:p-4"
      >
        {/* Mounted per opening, so each one starts from the rule or the product's defaults. */}
        <Form product={product} rule={rule} close={() => onOpenChange(false)} onSaved={onSaved} />
      </DialogContent>
    </Dialog>
  );
}

function Form({ product, rule, close, onSaved }: Omit<Props, "open" | "onOpenChange"> & { close: () => void }) {
  const [draft, setDraft] = useState<Draft>(() => (rule ? draftOf(rule) : { target: "product", type: "supplier_price_change", pct: "5", name: "" }));
  const set = (change: Partial<Draft>) => setDraft((d) => ({ ...d, ...change }));
  const writes = useRuleWrites();
  const save = rule ? writes.patch : writes.create;
  const errors = save.isError ? fieldErrors(save.error) : {};
  const suppliers = $api.useInfiniteQuery(
    "get",
    "/v1/products/{product_id}/suppliers",
    { params: { path: { product_id: product?.id ?? "" }, query: { country: "US" } } },
    // The Suppliers tab's own query, so its cache answers when it's been open.
    { enabled: useApiReady() && !!product, pageParamName: "cursor", initialPageParam: null, getNextPageParam: (page) => page.next_cursor },
  );
  const offers = suppliers.data?.pages[0].rows ?? [];
  const done = { onSuccess: (saved: Rule) => (onSaved?.(saved), close()) };
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (save.isPending) return;
    if (rule) writes.patch.mutate({ params: { path: { rule_id: rule.id } }, body: patchBody(draft, rule) }, done);
    else if (product) writes.create.mutate({ body: createBody(draft, product) }, done);
  };
  const target = rule && targetOf(rule);

  return (
    <form onSubmit={submit} noValidate className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="flex flex-col gap-1">
        <DialogTitle className="truncate">{rule ? "Edit alert rule" : `New alert rule on ${product?.name}`}</DialogTitle>
        <DialogDescription>Fires once each time it crosses, then waits until the change falls back.</DialogDescription>
      </div>
      <fieldset className="flex flex-wrap items-center gap-2 text-body text-muted-foreground max-sm:flex-col max-sm:items-stretch">
        <legend className="sr-only">Rule</legend>
        <span>When</span>
        {target ? (
          <span className={fixed}>
            {target.label} <span className="font-normal text-muted-foreground">· {target.detail}</span>
          </span>
        ) : (
          <select aria-label="Watch" className={field} value={draft.target} onChange={(e) => set({ target: e.target.value })}>
            <option value="product">any supplier</option>
            {offers.map((o) => (
              <option key={o.listing_id} value={String(o.listing_id)}>
                {o.supplier_name}
                {o.unit_cost_minor !== null && ` · ${money(o.unit_cost_minor, o.currency ?? "USD")}`}
              </option>
            ))}
          </select>
        )}
        {rule ? (
          <span className={fixed}>{VERBS[draft.type]}</span>
        ) : (
          <select aria-label="Event" className={field} value={draft.type} onChange={(e) => set({ type: e.target.value as RuleType })}>
            {Object.entries(VERBS).map(([type, verb]) => (
              <option key={type} value={type}>
                {verb}
              </option>
            ))}
          </select>
        )}
        {hasPct(draft.type) && (
          <span className="flex items-center gap-1.5">
            <input
              aria-label="Change, %"
              inputMode="decimal"
              value={draft.pct}
              onChange={(e) => set({ pct: e.target.value })}
              aria-invalid={!!errors.pct || undefined}
              aria-describedby={errors.pct ? "rule-pct-error" : undefined}
              className={cn(field, "w-20 text-right tabular-nums max-sm:w-24")}
            />
            %
          </span>
        )}
      </fieldset>
      {errors.pct && (
        <p id="rule-pct-error" role="alert" className="-mt-2 text-label text-negative">
          {errors.pct}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2 text-body text-muted-foreground">
        <span>Notify</span>
        <span className={cn(chip, "border-brand/40 bg-brand-muted text-foreground")}>
          <Check className="size-3.5 text-brand" aria-hidden />
          In-app
        </span>
        {["Discord", "Email"].map((channel) => (
          <span key={channel} title={`${channel} delivery arrives in Phase 7`} className={cn(chip, "border-border-subtle text-subtle-foreground")}>
            {channel} · Phase 7
          </span>
        ))}
      </div>
      <label className="flex flex-col gap-1.5 text-label text-muted-foreground">
        Name
        <input
          value={draft.name}
          onChange={(e) => set({ name: e.target.value })}
          placeholder={product ? autoName(draft, product.name) : undefined}
          maxLength={120}
          aria-invalid={!!errors.name || undefined}
          aria-describedby={errors.name ? "rule-name-error" : undefined}
          className={cn(field, "w-full text-body placeholder:text-subtle-foreground")}
        />
      </label>
      {errors.name && (
        <p id="rule-name-error" role="alert" className="-mt-2 text-label text-negative">
          {errors.name}
        </p>
      )}
      {errors.form && (
        <p role="alert" className="text-label text-negative">
          {errors.form}
        </p>
      )}
      <div className="mt-auto flex justify-end gap-2 max-sm:pb-[env(safe-area-inset-bottom)]">
        <DialogClose asChild>
          <Button type="button" variant="ghost">
            Cancel
          </Button>
        </DialogClose>
        <Button type="submit" variant="brand" aria-disabled={save.isPending}>
          {save.isPending ? (rule ? "Saving…" : "Creating…") : rule ? "Save rule" : "Create rule"}
        </Button>
      </div>
    </form>
  );
}
