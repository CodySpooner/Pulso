"use client";

import { useId, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { Package } from "lucide-react";

import { Missing } from "@/components/data-health/atoms";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { fetchClient } from "@/lib/api/client";
import { formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { money, parseMinor, toInput } from "../products/[id]/profit/model";
import { breakEven, KILL_REASONS, listKey, reasonOf, stageLabel, type Test } from "./model";

const field = "h-(--input-h) w-full min-w-0 rounded-md border border-input bg-background px-2.5 text-body text-foreground aria-invalid:border-negative";
const link = "link-inline rounded-sm underline decoration-border-strong underline-offset-2 hover:decoration-current";
const day = new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeZone: "UTC" });

/** The test drawer (click or Enter on a card): metrics, dates and notes, and the economics it started with (R-21). */
export function TestDrawer({ test, onClose }: { test: Test | undefined; onClose: () => void }) {
  const [shown, setShown] = useState(test);
  if (test && test !== shown) setShown(test); // keeps the last test on screen while the sheet slides out
  return (
    <Sheet open={test != null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" closeLabel="Close test" className="overflow-y-auto">
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
            {test.roas == null ? <Missing reason="No source yet: no ad spend recorded" /> : `${test.roas.toFixed(2)}×`}
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
            {saving ? "Saving…" : "Save"}
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
                {economics.roas == null ? <Missing reason="No break-even: the margin before ads is not positive" /> : `${economics.roas.toFixed(2)}×`}
              </Figure>
            </dl>
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
    </div>
  );
}

function Figure({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-lg border border-border-subtle bg-secondary/60 px-3 py-2" title={hint}>
      <dt className="text-label text-muted-foreground">{label}</dt>
      <dd className="font-mono text-stat-lg font-medium text-foreground tabular-nums">{children}</dd>
    </div>
  );
}

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

export function Thumb({ url, className }: { url: string | null; className?: string }) {
  const [broken, setBroken] = useState(false);
  const box = cn("size-9 shrink-0 rounded-md border border-border bg-secondary", className);
  if (!url || broken)
    return (
      <div className={cn(box, "grid place-items-center text-subtle-foreground")}>
        <Package className="size-4" aria-hidden />
      </div>
    );
  // eslint-disable-next-line @next/next/no-img-element -- listing images come from any store or supplier CDN; next/image would need each host allow-listed
  return <img src={url} alt="" width={36} height={36} onError={() => setBroken(true)} className={cn(box, "object-cover")} />;
}
