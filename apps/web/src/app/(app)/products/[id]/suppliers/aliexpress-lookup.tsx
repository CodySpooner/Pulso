"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { CircleOff, Hourglass, Search, TriangleAlert } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { PanelError, StaleLine } from "@/components/data-health/atoms";
import { EmptyState } from "@/components/pulso/empty-state";
import { Metric } from "@/components/pulso/metric";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, isProblem } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatAgo, formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { money } from "../profit/model";
import { count, days } from "./model";

type Lookup = components["schemas"]["AliExpressLookup"];
const PATH = "/v1/products/{product_id}/aliexpress";
/** Every AliExpress number carries this label (DEC-037, DEC-289): looked up on request, cached 24 h, never stored. */
export const LIVE = "AliExpress · live · not stored";
const OWNER_TODO = "Start the AliExpress applications"; // the vault Owner To-Dos item, by its text
const field =
  "h-8 w-full min-w-0 rounded-md border border-border bg-secondary px-2.5 text-data text-foreground transition-colors duration-(--duration-fast) placeholder:text-subtle-foreground hover:border-border-strong";
const cell = "border-b border-border-subtle px-3 whitespace-nowrap";
const link = "link-inline rounded-sm underline decoration-border-strong underline-offset-2 hover:decoration-current";

function Badge() {
  return <span className="inline-flex h-5 shrink-0 items-center rounded-sm bg-secondary px-1.5 text-micro font-medium whitespace-nowrap text-muted-foreground">{LIVE}</span>;
}

/** A number from the answer: its value, and on hover, focus or tap the badge, the as-of time and "Not stored". */
function Live({ value, label, format, asOf, now }: { value: number; label: string; format: (v: number) => string; asOf: string; now: number }) {
  const stat = { value, source: "aliexpress", source_name: LIVE, as_of: asOf, stale: false, method: null, raw_payload_id: null };
  return <Metric stat={stat} label={`${label} · ${LIVE}`} format={format} now={now} />;
}

// AE-3 (vault Features/Product Page - Suppliers): paste the product's AliExpress link and its SKUs and US shipping
// show here until their 24 h cache ends. Pulso keeps no AliExpress id, so nothing comes back after that (DEC-289).
export function AliExpressLookup({ id }: { id: string }) {
  const init = { params: { path: { product_id: id } } };
  const query = $api.useQuery("get", PATH, init, {
    enabled: useApiReady(),
    retry: (failures, error) => !(isProblem(error) && error.status < 500) && failures < 1,
  });
  const { queryKey } = $api.queryOptions("get", PATH, init);
  const queryClient = useQueryClient();
  const post = $api.useMutation("post", PATH);
  const [draft, setDraft] = useState("");
  const [refused, setRefused] = useState<{ answer: Lookup; at: number } | null>(null); // a lookup without an answer
  const [failure, setFailure] = useState<unknown>(null);
  const { data, refetch } = query;
  const now = query.dataUpdatedAt;

  // The rows go when their 24 h end, without a reload, even if the API can't be reached: then ask what's left.
  const expires = data?.expires_at;
  useEffect(() => {
    if (!expires) return;
    const timer = setTimeout(
      () => {
        queryClient.setQueryData(queryKey, { status: "empty" });
        void refetch();
      },
      Math.max(0, Date.parse(expires) - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [expires, refetch, queryClient, queryKey]);

  const submit = () => {
    setRefused(null);
    setFailure(null);
    post.mutate(
      { ...init, body: { link: draft.trim() } },
      {
        onSuccess: (answer) => {
          if (!answer.as_of) {
            setRefused({ answer, at: Date.now() });
            return void queryClient.invalidateQueries({ queryKey });
          }
          queryClient.setQueryData(queryKey, answer);
          setDraft("");
        },
        onError: setFailure,
      },
    );
  };

  let body: React.ReactNode;
  if (!data && query.isError) body = <PanelError title="Couldn't load the AliExpress lookup" error={query.error} retry={() => void refetch()} />;
  else if (!data)
    body = (
      <div className="flex flex-col gap-2">
        <span className="sr-only" role="status">
          Loading the AliExpress lookup…
        </span>
        <Skeleton className="h-8 w-full max-w-xl" />
        <Skeleton className="h-3.5 w-64" />
      </div>
    );
  else if (data.status === "disabled" || data.status === "not_configured") body = <Off status={data.status} />;
  else if (data.status === "throttled") body = <Paused retryAt={data.retry_at ?? null} now={now} />;
  else
    body = (
      <>
        <form
          className="flex flex-col gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <label htmlFor="aliexpress-link" className="text-label text-muted-foreground">
            AliExpress product link or number
          </label>
          <div className="flex max-w-xl gap-2">
            <input
              id="aliexpress-link"
              value={draft}
              maxLength={2048}
              onChange={(e) => setDraft(e.target.value)}
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
              placeholder="https://www.aliexpress.com/item/1005….html"
              className={field}
            />
            <Button type="submit" size="sm" variant="primary" disabled={!draft.trim() || post.isPending} className="h-8 shrink-0">
              <Search aria-hidden />
              {post.isPending ? "Looking up…" : "Look up"}
            </Button>
          </div>
        </form>
        {refused && <Refused answer={refused.answer} now={refused.at} />}
        {failure != null && <Failed error={failure} />}
        {data.status === "ok" && data.product && data.as_of && data.expires_at ? (
          <Answer data={{ ...data, product: data.product, as_of: data.as_of, expires_at: data.expires_at }} now={now} />
        ) : (
          <p className="text-data text-muted-foreground">
            {data.status === "not_found" && data.as_of
              ? `AliExpress found no product for the last link, as of ${formatUtc(data.as_of)}. Check the link and look it up again.`
              : "No lookup yet. Paste this product's AliExpress link to see each variant's unit cost and stock, and US shipping when the link names a variant (skuId)."}
          </p>
        )}
      </>
    );

  return (
    <section aria-labelledby="aliexpress-title" className="flex flex-col rounded-lg border border-border">
      <header className="flex flex-col gap-1 border-b border-border-subtle px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 id="aliexpress-title" className="text-body font-medium text-foreground">
            AliExpress
          </h3>
          <Badge />
        </div>
        <p className="text-micro text-subtle-foreground">Looked up only when you ask. Kept 24 h in cache, never stored in Pulso.</p>
      </header>
      <div className="flex flex-col gap-3 p-4">
        {data && query.isRefetchError && <StaleLine boxed what="Couldn't refresh the AliExpress lookup" error={query.error} asOf={now} retry={() => void refetch()} />}
        {body}
      </div>
    </section>
  );
}

function Off({ status }: { status: "disabled" | "not_configured" }) {
  return (
    <EmptyState size="sm" icon={CircleOff} title="AliExpress is off: needs the owner's app approval" className="py-6">
      {status === "disabled"
        ? "No source yet: lookups start on the collector host once the owner's AliExpress app is approved and the source is on. "
        : "No source yet: the source is on, but this host has no AliExpress app keys. "}
      Owner To-Dos: <q className="text-foreground">{OWNER_TODO}</q>. Until then,{" "}
      <Link href="/admin/data-health" className={link}>
        Data Health
      </Link>{" "}
      lists the source as off.
    </EmptyState>
  );
}

function Paused({ retryAt, now }: { retryAt: string | null; now: number }) {
  return (
    <EmptyState size="sm" icon={Hourglass} title="AliExpress lookups are paused" className="py-6">
      AliExpress asked Pulso to slow down, or today&apos;s 500 lookups are used.{" "}
      {retryAt ? (
        <>
          Lookups resume at <time dateTime={retryAt}>{formatUtc(retryAt)}</time> ({formatAgo(retryAt, now)}).
        </>
      ) : (
        "Try again in a minute."
      )}
    </EmptyState>
  );
}

/** A lookup that ran but brought no answer: why, in words. Earlier rows stay until their own 24 h end. */
function Refused({ answer, now }: { answer: Lookup; now: number }) {
  const text =
    answer.status === "throttled"
      ? `AliExpress lookups are paused${answer.retry_at ? ` until ${formatUtc(answer.retry_at)} (${formatAgo(answer.retry_at, now)})` : ""}.`
      : answer.status === "error"
        ? "AliExpress didn't answer, so nothing was kept. Try again."
        : "AliExpress is off: needs the owner's app approval.";
  return (
    <p role="status" className="text-label text-foreground">
      <TriangleAlert className="mr-1 inline size-3.5 align-[-2px] text-warning" aria-hidden />
      {text}
    </p>
  );
}

function Failed({ error }: { error: unknown }) {
  const problem = isProblem(error) ? error : null;
  return (
    <p role="alert" className="text-label text-foreground">
      <TriangleAlert className="mr-1 inline size-3.5 align-[-2px] text-negative" aria-hidden />
      {problem?.code === "invalid_link" ? (
        <>
          <span className="font-medium text-negative">That isn&apos;t an AliExpress product link.</span> Paste a link like
          aliexpress.com/item/1005….html, or the product number.
        </>
      ) : (
        <>
          <span className="font-medium text-negative">Couldn&apos;t run the lookup.</span>{" "}
          {problem ? (
            <>
              {problem.detail} <span className="font-mono text-subtle-foreground">Error ID {problem.request_id}</span>
            </>
          ) : (
            "The Pulso API didn't answer."
          )}
        </>
      )}
    </p>
  );
}

type Found = Lookup & { product: NonNullable<Lookup["product"]>; as_of: string; expires_at: string };

function Answer({ data, now }: { data: Found; now: number }) {
  const { product, as_of: asOf } = data;
  const n = (v: number) => String(v);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-0.5">
        <p className="truncate text-body font-medium text-foreground" title={product.title}>
          {product.title}
        </p>
        <p className="flex flex-wrap items-center gap-x-2 text-label text-muted-foreground">
          {product.store_name && <span>{product.store_name}</span>}
          {product.rating !== null && (
            <span>
              <Live value={Number(product.rating)} label="Rating out of 5" format={(v) => v.toFixed(1)} asOf={asOf} now={now} />
              {product.review_count !== null && (
                <>
                  {" "}
                  (<Live value={product.review_count} label="Reviews" format={count} asOf={asOf} now={now} />)
                </>
              )}
            </span>
          )}
          {product.sales && <span title="AliExpress's own sales label; its window isn't documented">{product.sales} sold</span>}
        </p>
      </div>
      <Table caption="Variants" heads={["Variant (SKU)", "Unit cost", "List price", "Stock", "Source"]}>
        {product.skus.map((sku) => (
          <tr key={sku.sku_id} className="row-h">
            <th scope="row" className={cn(cell, "text-left font-mono font-normal text-muted-foreground")}>
              {sku.sku_id}
            </th>
            <td className={cn(cell, "num font-medium text-foreground")}>
              <Live value={sku.sale_price_minor} label="Unit cost" format={(v) => money(v)} asOf={asOf} now={now} />
            </td>
            <td className={cn(cell, "num text-muted-foreground")}>
              <Live value={sku.price_minor} label="List price" format={(v) => money(v)} asOf={asOf} now={now} />
            </td>
            <td className={cn(cell, "num")}>
              {sku.stock === null ? (
                <span className="text-subtle-foreground" title="AliExpress didn't give this variant's stock">
                  —
                </span>
              ) : (
                <Live value={sku.stock} label="Stock" format={n} asOf={asOf} now={now} />
              )}
            </td>
            <td className={cell}>
              <Badge />
            </td>
          </tr>
        ))}
      </Table>
      {data.shipping && (
        <Table caption="Shipping to the US, 1 unit" heads={["Method", "Ship to US", "Days", "From", "Source"]}>
          {data.shipping.length === 0 ? (
            <tr>
              <td colSpan={5} className={cn(cell, "py-2 text-muted-foreground")}>
                AliExpress offers no shipping to the US for this variant.
              </td>
            </tr>
          ) : (
            data.shipping.map((option) => (
              <tr key={option.code} className="row-h">
                <th scope="row" className={cn(cell, "text-left font-normal text-foreground")}>
                  {option.company}
                </th>
                <td className={cn(cell, "num")}>
                  <Live value={option.fee_minor} label={`Shipping, ${option.company}`} format={(v) => (option.free ? "Free" : money(v))} asOf={asOf} now={now} />
                </td>
                <td className={cn(cell, "num")}>
                  {option.max_days === null && option.min_days === null ? (
                    <span className="text-subtle-foreground">—</span>
                  ) : (
                    <Live value={option.max_days ?? option.min_days!} label={`Days, ${option.company}`} format={() => days(option.min_days, option.max_days)!} asOf={asOf} now={now} />
                  )}
                </td>
                <td className={cn(cell, "text-muted-foreground")}>{option.ship_from ?? "—"}</td>
                <td className={cell}>
                  <Badge />
                </td>
              </tr>
            ))
          )}
        </Table>
      )}
      <p className="text-micro text-subtle-foreground">
        As of <time dateTime={asOf}>{formatUtc(asOf)}</time> · gone at <time dateTime={data.expires_at}>{formatUtc(data.expires_at)}</time>. Not in landed cost
        or picks: Pulso keeps no AliExpress history.
      </p>
    </div>
  );
}

function Table({ caption, heads, children }: { caption: string; heads: string[]; children: React.ReactNode }) {
  return (
    <div role="region" aria-label={`AliExpress ${caption[0].toLowerCase()}${caption.slice(1)}`} tabIndex={0} className="overflow-x-auto overscroll-x-contain rounded-lg border border-border">
      <table className="w-full border-separate border-spacing-0 zone-data">
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-card">
          <tr className="row-h text-label text-muted-foreground">
            {heads.map((head, i) => (
              <th key={head} scope="col" className={cn(cell, "border-border font-medium", i === 0 || i === heads.length - 1 || head === "From" ? "text-left" : "text-right")}>
                {head}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
