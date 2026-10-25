"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as m from "motion/react-m";
import { Package, PackageX, SearchX, TriangleAlert } from "lucide-react";
import { Tabs } from "radix-ui";

import { CreateAlert } from "@/components/alerts/rule-builder";
import { useApiReady } from "@/components/data-health/api";
import { PanelError, StaleLine } from "@/components/data-health/atoms";
import { EmptyState } from "@/components/pulso/empty-state";
import { Metric, type Stat } from "@/components/pulso/metric";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, isProblem } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatAgo, formatUtc } from "@/lib/format";
import { duration, spring } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { StartTest } from "../../testing/start-test";
import { WatchControl } from "../../watchlists/star";

import { ContextRail } from "./context-rail";
import { Overview } from "./overview";
import { ProfitTab } from "./profit/profit-tab";
import { SellersTab } from "./sellers/sellers-tab";
import { SuppliersTab } from "./suppliers/suppliers-tab";
import { card, newest, StatCard } from "./stat-card";
import { resolveTab, TAB_FLAGS, TABS, type Tab } from "./tabs";
import { TrendsTab } from "./trends";

// The header stats as a response carries them (openapi-fetch retypes a NoSource, see Stat).
type Stats = Record<"store_count" | "supplier_count" | "price_min_minor" | "price_max_minor", Stat>;
type Sourced = components["schemas"]["Sourced"];

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const money = (minor: number) => usd.format(minor / 100);
const count = (n: number) => n.toLocaleString("en-US");
const day = new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeZone: "UTC" });

// UX-3 (vault Features/Product Page): header, stat strip and tab bar. States per vault Design/UI States: a skeleton
// while loading, not found, a panel error, a stale line when a refetch fails, stale data, and no source yet.
export function ProductPage({ id }: { id: string }) {
  const router = useRouter();
  const product = $api.useQuery(
    "get",
    "/v1/products/{product_id}",
    { params: { path: { product_id: id } } },
    // A 4xx won't change on a retry, so not found shows at once.
    { enabled: useApiReady(), retry: (failures, error) => !(isProblem(error) && error.status < 500) && failures < 1 },
  );
  const { data, error } = product;
  const failed = product.isError && !data;
  const notFound = failed && isProblem(error) && (error.status === 404 || error.status === 422);
  const emptied = notFound && isProblem(error) && error.code === "no_listings"; // an undo took its last listing (DEC-271)
  const retry = () => void product.refetch();

  // A merged id answers 308, which fetch follows: show the survivor's URL, query string kept (DEC-238).
  useEffect(() => {
    if (data && data.id !== id) router.replace(`/products/${data.id}${window.location.search}`);
  }, [data, id, router]);

  return (
    <div className="flex w-full flex-col gap-6">
      {data && product.isError && <StaleLine boxed what="Couldn't refresh this product" error={error} asOf={product.dataUpdatedAt} retry={retry} />}
      <header className="grid grid-cols-[auto_minmax(0,1fr)] items-start gap-4 sm:grid-cols-[auto_minmax(0,1fr)_auto]">
        {data ? <Thumb url={data.image_url} /> : !failed && <Skeleton className="size-12 shrink-0 rounded-lg sm:size-18" />}
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          {/* One h1 in every state, so the focus the route template gives it on a navigation survives the load. */}
          <h1
            tabIndex={-1}
            title={data?.title}
            className={cn("line-clamp-2 text-title-1 font-semibold break-words text-foreground outline-none", !data && !failed && "sr-only")}
          >
            {data?.title ?? (emptied ? "Product has no listings" : notFound ? "Product not found" : failed ? "Product" : "Loading product")}
          </h1>
          {data ? (
            <p className="text-label text-subtle-foreground">
              {data.category?.replaceAll(" > ", " › ") ?? "Uncategorised"} ·{" "}
              <span className="whitespace-nowrap">
                First seen{" "}
                <time dateTime={data.first_seen_at} title={formatUtc(data.first_seen_at)}>
                  {day.format(new Date(data.first_seen_at))}
                </time>
              </span>
            </p>
          ) : (
            !failed && (
              <>
                <Skeleton className="h-8 w-2/3" />
                <Skeleton className="h-4 w-56 max-w-full" />
              </>
            )
          )}
        </div>
        {data && (
          <div className="col-span-2 flex flex-wrap items-start gap-2 sm:col-span-1 sm:justify-end">
            <WatchControl product={data} />
            <CreateAlert product={{ id: data.id, name: data.title }} />
            <StartTest productId={data.id} />
          </div>
        )}
      </header>
      {data ? (
        <Loaded product={data} now={product.dataUpdatedAt} />
      ) : notFound ? (
        <section className={card}>
          <EmptyState
            icon={emptied ? PackageX : SearchX}
            headingLevel="h2"
            title={emptied ? "No listings left on this product" : "No product has this ID"}
            action={
              <Button asChild variant="secondary">
                <Link href="/">Go to Daily Pulse</Link>
              </Button>
            }
          >
            {emptied
              ? "An undo in the Matching Queue moved its last listing off it, so Discover and search no longer show it. Its notes, scores and forecasts are kept."
              : "Check the link. A product merged into another one redirects to it, so links Pulso gave you keep working."}
          </EmptyState>
        </section>
      ) : failed ? (
        <section className={card}>
          <PanelError headingLevel="h2" size="md" title="Couldn't load this product" error={error} retry={retry} />
        </section>
      ) : (
        <BodySkeleton />
      )}
    </div>
  );
}

function Thumb({ url }: { url: string | null }) {
  const [broken, setBroken] = useState(false);
  const box = "size-12 shrink-0 rounded-lg border border-border bg-secondary sm:size-18";
  if (!url || broken)
    return (
      <div className={cn(box, "grid place-items-center text-subtle-foreground")}>
        <Package className="size-5" strokeWidth={1.5} aria-hidden />
      </div>
    );
  // eslint-disable-next-line @next/next/no-img-element -- listing images come from any store or supplier CDN; next/image would need each host allow-listed
  return <img src={url} alt="" width={72} height={72} onError={() => setBroken(true)} className={cn(box, "object-cover")} />;
}

function Loaded({ product, now }: { product: Stats & { id: string }; now: number }) {
  const prices = [product.price_min_minor, product.price_max_minor];
  const stats = [product.store_count, product.supplier_count, ...prices];
  const stale = [...new Map(stats.filter((s): s is Sourced => !("reason" in s) && s.stale).map((s) => [s.source, s])).values()];
  return (
    <>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard label="Stores" stat={product.store_count} now={now}>
          <Metric stat={product.store_count} label="Stores selling it" format={count} now={now} />
        </StatCard>
        <StatCard label="Suppliers" stat={product.supplier_count} now={now}>
          <Metric stat={product.supplier_count} label="Matched suppliers" format={count} now={now} />
        </StatCard>
        <StatCard label="Retail price" stat={newest(prices) ?? product.price_min_minor} now={now} className="col-span-2 sm:col-span-1">
          {"reason" in product.price_min_minor ? (
            <Metric stat={product.price_min_minor} label="Retail price" format={money} now={now} />
          ) : (
            <>
              <Metric stat={product.price_min_minor} label="Lowest retail price" format={money} now={now} />
              <span aria-hidden className="mx-1.5 text-subtle-foreground">–</span>
              <Metric stat={product.price_max_minor} label="Highest retail price" format={money} now={now} />
            </>
          )}
        </StatCard>
      </dl>
      {stale.length > 0 && (
        <p className="rounded-lg border border-warning/40 bg-warning-muted px-4 py-2.5 text-data text-foreground">
          <TriangleAlert className="mr-1.5 inline size-3.5 align-[-2px] text-warning" aria-hidden />
          <span className="font-medium">Some numbers are older than expected.</span>{" "}
          {stale.map((s) => `${s.source_name} last captured ${formatUtc(s.as_of)} (${formatAgo(s.as_of, now)})`).join("; ")}. The
          collector host may be off or the source paused.{" "}
          <Link href="/admin/data-health" className="link-inline rounded-sm whitespace-nowrap underline decoration-border-strong underline-offset-2 hover:decoration-current">
            Open Data Health
          </Link>
        </p>
      )}
      <ProductTabs id={product.id} />
    </>
  );
}

function ProductTabs({ id }: { id: string }) {
  const tab = resolveTab(useSearchParams().get("tab"));
  const list = useRef<HTMLDivElement>(null);
  const tabs = TABS.filter((t) => TAB_FLAGS[t.value]);
  // A deep-linked tab past the edge of a phone's scrolling bar scrolls into view, without scrolling the page.
  useEffect(() => {
    const active = list.current?.querySelector<HTMLElement>('[data-state="active"]');
    if (list.current && active) list.current.scrollLeft = Math.max(0, active.offsetLeft + active.offsetWidth + 16 - list.current.clientWidth);
  }, [tab]);

  const select = (value: string) => {
    const params = new URLSearchParams(window.location.search);
    if (value === "overview") params.delete("tab");
    else params.set("tab", value);
    const query = params.toString();
    // Native history keeps Back for the previous page and skips a server round trip; Next syncs useSearchParams.
    window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
  };
  // A link inside a panel: switch, and focus lands on the tab it opened rather than falling back to the page.
  const goTo = (value: Tab) => {
    select(value);
    list.current?.querySelector<HTMLElement>(`[data-tab="${value}"]`)?.focus();
  };

  return (
    <Tabs.Root value={tab} onValueChange={select} activationMode="manual" className="flex flex-col gap-4">
      <Tabs.List
        ref={list}
        aria-label="Product sections"
        className="relative -mx-4 flex snap-x overflow-x-auto border-b border-border px-4 [scrollbar-width:none] md:mx-0 md:px-0"
      >
        {tabs.map((t) => (
          <Tabs.Trigger
            key={t.value}
            value={t.value}
            data-tab={t.value}
            className="relative h-11 shrink-0 snap-start px-3 text-body font-medium text-muted-foreground transition-colors duration-(--duration-fast) ease-standard -outline-offset-2 hover:text-foreground data-[state=active]:text-foreground"
          >
            {t.label}
            {t.value === tab && <m.span layoutId="product-tab" transition={spring.snappy} className="absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-brand" />}
          </Tabs.Trigger>
        ))}
      </Tabs.List>
      {/* The context rail sits beside every tab from 1280px and under it below (DEC-243). */}
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
        {tabs.map((t) => (
          <Tabs.Content key={t.value} value={t.value} className={cn("min-w-0", t.value !== "overview" && card)}>
            <m.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: duration.fast }}>
              {t.value === "overview" ? (
                <Overview id={id} goTo={goTo} />
              ) : t.value === "suppliers" ? (
                <SuppliersTab id={id} goTo={goTo} />
              ) : t.value === "sellers" ? (
                <SellersTab id={id} />
              ) : t.value === "trends" ? (
                <TrendsTab id={id} />
              ) : (
                <ProfitTab id={id} />
              )}
            </m.div>
          </Tabs.Content>
        ))}
        <ContextRail id={id} />
      </div>
    </Tabs.Root>
  );
}

function BodySkeleton() {
  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className={cn("flex flex-col gap-1 px-4 py-3", card, i === 2 && "col-span-2 sm:col-span-1")}>
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-7 w-24" />
            <Skeleton className="h-3.5 w-32" />
          </div>
        ))}
      </div>
      <div className="flex h-11 items-center gap-6 overflow-hidden border-b border-border">
        {TABS.map((t) => (
          <Skeleton key={t.value} className="h-4 w-16 shrink-0" />
        ))}
      </div>
      <Skeleton className="h-60 w-full rounded-xl" />
    </>
  );
}
