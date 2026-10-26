"use client";

import { useId, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";

import { Ago, Missing, PanelError, StaleLine } from "@/components/data-health/atoms";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, fetchClient } from "@/lib/api/client";
import { formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { Thumb as ListingThumb } from "../admin/matching/compare";
import { money, parseMinor, toInput } from "../products/[id]/profit/model";
import { breakEven, describeChange, KILL_REASONS, listKey, reasonOf, stageLabel, type Test } from "./model";

const field = "h-(--input-h) w-full min-w-0 rounded-md border border-input bg-background px-2.5 text-body text-foreground aria-invalid:border-negative";
const link = "link-inline relative hit-area rounded-sm underline decoration-border-strong underline-offset-2 hover:decoration-current";
const day = new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeZone: "UTC" });

/** The test drawer (click or Enter on a card): metrics, dates and notes, and the economics it started with (R-21). */
export function TestDrawer({ test, onClose }: { test: Test | undefined; onClose: () => void }) {
  const [shown, setShown] = useState(test);
  if (test && test !== shown) setShown(test); // keeps the last test on screen while the sheet slides out
  return (
    <Sheet open={test != null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        closeLabel="Close test"
        className="overflow-y-auto"
        // The sheet itself takes focus, so a phone doesn't open its keypad on the first field; Tab goes on from there.
        onOpenAutoFocus={(e) => (e.preventDefault(), (e.currentTarget as HTMLElement).focus())}
        // It opens from state, not a trigger, so closing hands focus back to the test's card by hand.
        onCloseAutoFocus={(e) => (e.preventDefault(), document.getElementById(`test-${shown?.id}`)?.focus())}
      >
        {shown && <Body key={shown.id} test={shown} />}
      </SheetContent>
    </Sheet>
  );
}

function Body({ test }: { test: Test }) {
  const client = useQueryClient();
  const [form, setForm] = useState({
    ad_spend: toInput(test.ad_spend_minor),
    revenue: toInput(test.revenue_minor),
    orders: String(test.orders),
    started_on: test.started_on ?? "",
    ended_on: test.ended_on ?? "",
    notes: test.notes ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<{ tone: "done" | "error"; text: string } | null>(null);
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => (setForm({ ...form, [key]: e.target.value }), setResult(null));
  const spend = parseMinor(form.ad_spend);
  const revenue = parseMinor(form.revenue);
  const orders = /^\d+$/.test(form.orders.trim()) ? Number(form.orders) : null;
  const invalid = spend == null || revenue == null || orders == null;

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (invalid || saving) return;
    setSaving(true);
    const body = { ad_spend_minor: spend, revenue_minor: revenue, orders, started_on: form.started_on || null, ended_on: form.ended_on || null, notes: form.notes.trim() || null };
    const answer = await fetchClient.PATCH("/v1/tests/{test_id}", { params: { path: { test_id: test.id } }, body }).catch((error: unknown) => ({ data: undefined, error }));
    if (answer.data) await client.invalidateQueries({ queryKey: listKey });
    setSaving(false);
    setResult(answer.data ? { tone: "done", text: "Saved." } : { tone: "error", text: `Couldn't save: ${reasonOf(answer.error)}` });
  };

  const economics = breakEven(test);
  return (
    <div className="flex flex-col gap-6 p-5 pt-4">
      <header className="flex items-start gap-3 pr-8">
        <Thumb url={test.product_image_url} className="size-12 rounded-lg" />
        <div className="flex min-w-0 flex-col gap-1">
          <SheetTitle className="text-title-3 font-semibold break-words text-foreground">{test.product_title}</SheetTitle>
          <SheetDescription className="text-label text-muted-foreground">
            {stageLabel(test.stage)}
            {test.kill_reason && ` · ${KILL_REASONS[test.kill_reason].split(":")[0]}`} ·{" "}
            <Link href={`/products/${test.product_id}?tab=profit`} className={link}>
              Open product
            </Link>
          </SheetDescription>
        </div>
      </header>

      <section aria-labelledby="results" className="flex flex-col gap-2">
        <h3 id="results" className="text-label font-semibold text-muted-foreground uppercase">
          Results
        </h3>
        <dl className="grid grid-cols-2 gap-3">
          <Figure label="CPA" hint="Ad spend ÷ orders, from the API">
            {test.cpa_minor == null ? <Missing reason="No source yet: no orders recorded" /> : money(test.cpa_minor)}
          </Figure>
          <Figure label="ROAS" hint="Revenue ÷ ad spend, from the API">
            {test.roas == null ? <Missing reason="No source yet: no ad spend recorded" /> : <Times value={test.roas} />}
          </Figure>
        </dl>
      </section>

      <form onSubmit={save} className="flex flex-col gap-4" aria-labelledby="metrics">
        <h3 id="metrics" className="text-label font-semibold text-muted-foreground uppercase">
          Metrics
        </h3>
        <div className="grid grid-cols-3 gap-3">
          <Input label="Ad spend" value={form.ad_spend} onChange={set("ad_spend")} invalid={spend == null} money />
          <Input label="Revenue" value={form.revenue} onChange={set("revenue")} invalid={revenue == null} money />
          <Input label="Orders" value={form.orders} onChange={set("orders")} invalid={orders == null} inputMode="numeric" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Started on" type="date" value={form.started_on} onChange={set("started_on")} />
          <Input label="Ended on" type="date" value={form.ended_on} onChange={set("ended_on")} />
        </div>
        <label className="flex flex-col gap-1.5 text-label text-muted-foreground">
          Notes
          <textarea value={form.notes} onChange={set("notes")} rows={4} className={cn(field, "h-auto py-2")} />
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" variant="primary" aria-disabled={invalid || saving}>
            {saving ? "Saving…" : "Save metrics"}
          </Button>
          <p role="status" className={cn("text-data", result?.tone === "error" ? "text-negative" : "text-muted-foreground")}>
            {invalid ? "Enter amounts like 120.50 and a whole number of orders." : result?.text}
          </p>
        </div>
      </form>

      <section aria-labelledby="economics" className="flex flex-col gap-2">
        <h3 id="economics" className="text-label font-semibold text-muted-foreground uppercase">
          Economics at start
        </h3>
        {economics == null ? (
          <p className="text-data text-muted-foreground">Pulso records the price, landed cost and break-even when this test first enters Testing.</p>
        ) : economics === "incomplete" ? (
          <p className="rounded-lg border border-border bg-secondary px-3 py-2.5 text-data text-foreground">
            Set price and supplier to compute break-even.{" "}
            <Link href={`/products/${test.product_id}?tab=profit`} className={link}>
              Open the Profit tab
            </Link>
          </p>
        ) : (
          <>
            <dl className="grid grid-cols-2 gap-3">
              <Figure label="Price">{money(economics.price)}</Figure>
              <Figure label="Landed cost">{money(economics.landed)}</Figure>
              <Figure label="Break-even CPA" hint="Price − landed cost − fees: the most an order can cost in ads">
                {money(economics.cpa)}
              </Figure>
              <Figure label="Break-even ROAS" hint="Price ÷ break-even CPA">
                {economics.roas == null ? <Missing reason="No break-even: the margin before ads is not positive" /> : <Times value={economics.roas} />}
              </Figure>
            </dl>
            {test.stop_loss_minor != null && (
              <p className="text-data text-muted-foreground">
                Suggested test budget <span className="font-mono text-foreground tabular-nums">{money(test.stop_loss_minor)}</span>: 2 × break-even CPA. With no
                orders by then, or a CPA above break-even after 5 orders, the card says Over stop-loss.
              </p>
            )}
            <p className="text-label text-subtle-foreground">
              Captured{" "}
              <time dateTime={economics.capturedAt} title={formatUtc(economics.capturedAt)}>
                {day.format(new Date(economics.capturedAt))}
              </time>{" "}
              from the Profit calc. Later price or supplier changes leave it as it was.
            </p>
          </>
        )}
      </section>

      {test.start_snapshot != null && <SinceStart test={test} />}
    </div>
  );
}

const tone = { positive: "text-positive", negative: "text-negative" } as const;

/** R-21's "changed since start": the API compares the start snapshot with a fresh Profit calc of the same scenario
 *  (DEC-340). The snapshot itself never changes; this only says what moved since. */
function SinceStart({ test }: { test: Test }) {
  const detail = $api.useQuery("get", "/v1/tests/{test_id}", { params: { path: { test_id: test.id } } });
  const since = detail.data?.since_start;
  const retry = () => void detail.refetch();
  return (
    <section aria-labelledby="since-start" className="flex flex-col gap-2">
      <h3 id="since-start" className="text-label font-semibold text-muted-foreground uppercase">
        Changed since start
      </h3>
      {detail.isRefetchError && <StaleLine what="Couldn't refresh the comparison" error={detail.error} asOf={detail.dataUpdatedAt} retry={retry} />}
      {!detail.data ? (
        detail.isError ? (
          <PanelError title="Couldn't compare with today's numbers" headingLevel="h3" error={detail.error} retry={retry} />
        ) : (
          <div role="status" aria-label="Comparing with today's Profit calc" className="flex flex-col gap-2">
            <Skeleton className="h-9" />
            <Skeleton className="h-9" />
          </div>
        )
      ) : since?.reason ? (
        <p className="rounded-lg border border-border bg-secondary px-3 py-2.5 text-data text-foreground">
          Can&apos;t compare with today&apos;s numbers: {since.reason}{" "}
          <Link href={`/products/${test.product_id}?tab=profit`} className={link}>
            Check the Profit tab
          </Link>
        </p>
      ) : !since?.changes.length ? (
        <p className="text-data text-muted-foreground">No changes since start.</p>
      ) : (
        <ul aria-label="Changed inputs" className="flex flex-col divide-y divide-border-subtle rounded-lg border border-border-subtle">
          {since.changes.map((change) => {
            const row = describeChange(change);
            return (
              <li key={change.input} className="grid grid-cols-[1fr_auto] items-baseline gap-x-3 gap-y-0.5 px-3 py-2 text-data">
                <span className="text-muted-foreground">{row.label}</span>
                <span className="justify-self-end font-mono tabular-nums">
                  {row.delta ? (
                    <span className={cn("inline-flex items-center gap-1", tone[row.delta.tone])}>
                      <span aria-hidden className="text-micro">
                        {row.delta.glyph}
                      </span>
                      {row.delta.text}
                    </span>
                  ) : (
                    <span className="font-sans text-label text-subtle-foreground">{row.new == null ? "No source yet" : row.old == null ? "New since start" : "Re-quoted"}</span>
                  )}
                </span>
                <span className="col-span-2 font-mono text-foreground tabular-nums">
                  {row.old ?? <Missing reason="None at start" />}
                  <span aria-hidden className="px-1.5 text-subtle-foreground">
                    →
                  </span>
                  <span className="sr-only"> changed to </span>
                  {row.new ?? <Missing reason="No source yet: none today" />}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {since && !since.reason && (
        <p className="text-label text-subtle-foreground">
          Against today&apos;s Profit calc for the same supplier, price and estimates
          {since.as_of ? (
            <>
              , data as of <Ago iso={since.as_of} now={detail.dataUpdatedAt} source="The oldest observation in today's calc" />
            </>
          ) : (
            ", from settings only"
          )}
          .
        </p>
      )}
    </section>
  );
}

export const Thumb = ({ url, className }: { url: string | null; className?: string }) => (
  <ListingThumb url={url} className={cn("size-9 shrink-0 rounded-md border border-border object-cover", className)} />
);

function Figure({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-lg border border-border-subtle bg-secondary/60 px-3 py-2" title={hint}>
      <dt className="text-label text-muted-foreground">{label}</dt>
      <dd className="font-mono text-stat-lg font-medium text-foreground tabular-nums">{children}</dd>
    </div>
  );
}

/** A ROAS with its unit a step down, so the number leads. */
const Times = ({ value }: { value: number }) => (
  <>
    {value.toFixed(2)}
    <span className="ml-0.5 text-body text-muted-foreground">×</span>
  </>
);

function Input({ label, invalid, money: isMoney, className, ...props }: React.ComponentProps<"input"> & { label: string; invalid?: boolean; money?: boolean }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-label text-muted-foreground">
        {label}
      </label>
      <div className="relative">
        {isMoney && (
          <span aria-hidden className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-body text-subtle-foreground">
            $
          </span>
        )}
        <input
          id={id}
          aria-invalid={invalid}
          autoComplete="off"
          inputMode={isMoney ? "decimal" : undefined}
          className={cn(field, "font-mono tabular-nums", isMoney && "pl-6", className)}
          {...props}
        />
      </div>
    </div>
  );
}
