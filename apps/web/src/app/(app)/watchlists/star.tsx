"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import * as m from "motion/react-m";
import { Check, ChevronDown, Star } from "lucide-react";
import { DropdownMenu } from "radix-ui";

import { useApiReady } from "@/components/data-health/api";
import { Button } from "@/components/ui/button";
import { $api, fetchClient } from "@/lib/api/client";
import { spring } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { applyWatch, listed, refreshWatchlists, type Watch } from "./model";

interface Product extends Watch {
  id: string;
  title: string;
}

async function send({ id, on }: { id: string; on: boolean }): Promise<string | null> {
  const path = { params: { path: { product_id: id } } };
  const { data, error } = on ? await fetchClient.PUT("/v1/products/{product_id}/watch", path) : await fetchClient.DELETE("/v1/products/{product_id}/watch", path);
  if (error !== undefined) throw error;
  return data?.watchlist_id ?? null; // Main's id, or null when Main didn't hold it
}

/** ★ on or off: every cached read of the product flips at once and flips back on an error (DEC-322). The answer names
 *  Main, so its id joins or leaves watchlist_ids; the lists refetch for their counts. */
function useStar() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: send,
    onMutate: ({ id, on }) => applyWatch(client, id, (w) => ({ ...w, watched: on })),
    onError: (_error, { id, on }) => applyWatch(client, id, (w) => ({ ...w, watched: !on })),
    onSuccess: (main, { id, on }) => applyWatch(client, id, (w) => (main ? listed(main, on, true)(w) : { ...w, watched: on })),
    onSettled: () => refreshWatchlists(client),
  });
}

/** The ★ glyph. It springs from 0.8 only after a press here, so a row mounting as a table scrolls never animates. */
function Glyph({ on, pressed, className }: { on: boolean; pressed: boolean; className?: string }) {
  return (
    <m.span key={String(on)} initial={pressed ? { scale: 0.8 } : false} animate={{ scale: 1 }} transition={spring.snappy} className="grid place-items-center">
      <Star className={cn("size-4", on ? "fill-brand text-brand" : "text-muted-foreground", className)} aria-hidden />
    </m.span>
  );
}

/** The ★ on a Discover card or row: adds the product to Main, or takes it off. */
export function StarButton({ product, className }: { product: Product; className?: string }) {
  const star = useStar();
  const [pressed, setPressed] = useState(false);
  const others = product.watchlist_ids.length - (product.watched ? 1 : 0);
  return (
    <Button
      size="icon-sm"
      variant="ghost"
      aria-pressed={product.watched}
      aria-label={`Watch ${product.title}`}
      title={(product.watched ? "On Main. Press to remove" : "Add to Main") + (others > 0 ? ` · on ${others} other ${others === 1 ? "list" : "lists"}` : "")}
      className={className}
      onClick={() => {
        if (star.isPending) return;
        setPressed(true);
        star.mutate({ id: product.id, on: !product.watched });
      }}
    >
      <Glyph on={product.watched} pressed={pressed} />
    </Button>
  );
}

const item = "flex h-8 cursor-pointer items-center gap-2 rounded-md px-2 text-data outline-none select-none pointer-coarse:h-(--hit-target) data-highlighted:bg-accent";

/** The Product Page's Watch button, and beside it a menu of every list with the ones holding the product checked. */
export function WatchControl({ product }: { product: Product }) {
  const client = useQueryClient();
  const star = useStar();
  const [pressed, setPressed] = useState(false);
  const lists = $api.useQuery("get", "/v1/watchlists", {}, { enabled: useApiReady() });
  const toggle = useMutation({
    mutationFn: async ({ list, on }: { list: string; on: boolean; main: boolean }) => {
      const path = { watchlist_id: list };
      const { error } = on
        ? await fetchClient.POST("/v1/watchlists/{watchlist_id}/items", { params: { path }, body: { product_ids: [product.id] } })
        : await fetchClient.DELETE("/v1/watchlists/{watchlist_id}/items/{product_id}", { params: { path: { ...path, product_id: product.id } } });
      if (error !== undefined) throw error;
    },
    onMutate: ({ list, on, main }) => applyWatch(client, product.id, listed(list, on, main)),
    onError: (_error, { list, on, main }) => applyWatch(client, product.id, listed(list, !on, main)),
    onSettled: () => refreshWatchlists(client),
  });
  return (
    <div className="flex" role="group" aria-label="Watchlists">
      <Button
        aria-pressed={product.watched}
        className={cn("rounded-r-none", product.watched && "border-brand/40 text-foreground")}
        onClick={() => {
          if (star.isPending) return;
          setPressed(true);
          star.mutate({ id: product.id, on: !product.watched });
        }}
      >
        <Glyph on={product.watched} pressed={pressed} />
        {product.watched ? "Watching" : "Watch"}
      </Button>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <Button size="icon" aria-label="Lists for this product" className="-ml-px rounded-l-none">
            <ChevronDown aria-hidden />
          </Button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            sideOffset={4}
            className="z-50 max-h-80 min-w-52 overflow-y-auto rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-popover data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-96 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 duration-(--duration-fast)"
          >
            <DropdownMenu.Label className="px-2 pt-1 pb-1.5 text-micro font-medium text-subtle-foreground uppercase">On lists</DropdownMenu.Label>
            {lists.data?.length === 0 && <p className="px-2 pb-1.5 text-label text-muted-foreground">No lists yet. Watch adds it to Main.</p>}
            {lists.isError && <p className="px-2 pb-1.5 text-label text-muted-foreground">Couldn&apos;t load your lists.</p>}
            {lists.data?.map((l) => {
              const on = product.watchlist_ids.includes(l.id);
              return (
                <DropdownMenu.CheckboxItem
                  key={l.id}
                  checked={on}
                  onSelect={(e) => e.preventDefault()} // stays open, so several lists can change
                  onCheckedChange={(next) => toggle.mutate({ list: l.id, on: next, main: l.name === "Main" })}
                  className={item}
                >
                  <span className="grid size-4 place-items-center">
                    <DropdownMenu.ItemIndicator>
                      <Check className="size-4 text-brand" aria-hidden />
                    </DropdownMenu.ItemIndicator>
                  </span>
                  <span className="min-w-0 flex-1 truncate">{l.name}</span>
                  <span className="font-mono text-label text-subtle-foreground tabular-nums">{l.item_count}</span>
                </DropdownMenu.CheckboxItem>
              );
            })}
            <DropdownMenu.Separator className="my-1 h-px bg-border" />
            <DropdownMenu.Item asChild className={item}>
              <Link href="/watchlists">Open Watchlists</Link>
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </div>
  );
}
