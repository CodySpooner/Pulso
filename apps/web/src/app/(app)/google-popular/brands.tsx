"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence } from "motion/react";
import * as m from "motion/react-m";
import { useQueryClient, type InfiniteData, type QueryKey } from "@tanstack/react-query";
import { Popover } from "radix-ui";
import { ListFilter } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { PanelError, StaleLine } from "@/components/data-health/atoms";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, isProblem } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { duration, ease } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { patchPages, type Action } from "./model";

type Page = components["schemas"]["PopularPage"];
type Rules = components["schemas"]["BrandRulePage"];
interface Note {
  id: number;
  text: string;
  undo?: () => void;
  error?: boolean;
}

const POPULAR: QueryKey = ["get", "/v1/popular-products"];
const RULES: QueryKey = ["get", "/v1/popular-products/brands"];
const LIST = { params: { query: { limit: 500 } } }; // ponytail: one page of 500 rules; Load more past that
const said = { hide: "hidden", show: "always shown" } as const;

/** The workspace brand list (DEC-277): set or clear a rule optimistically, then refetch; every change can be undone. */
export function useBrandRules() {
  const queryClient = useQueryClient();
  const put = $api.useMutation("put", "/v1/popular-products/brands");
  const remove = $api.useMutation("delete", "/v1/popular-products/brands");
  const [note, setNote] = useState<Note | null>(null);
  const seq = useRef(0); // each note a new key, so the toast re-enters

  const apply = (brand: string, next: Action | null, previous: Action | null, undoable = true) => {
    const saved = [...queryClient.getQueriesData({ queryKey: POPULAR }), ...queryClient.getQueriesData({ queryKey: RULES })];
    void queryClient.cancelQueries({ queryKey: POPULAR });
    void queryClient.cancelQueries({ queryKey: RULES });
    for (const [key, data] of queryClient.getQueriesData<InfiniteData<Page>>({ queryKey: POPULAR })) {
      const all = (key[2] as { params?: { query?: { include_major_brands?: boolean } } } | undefined)?.params?.query?.include_major_brands === true;
      if (data) queryClient.setQueryData(key, patchPages(data, brand, next, all));
    }
    queryClient.setQueriesData<Rules>({ queryKey: RULES }, (data) => {
      if (!data) return data;
      const items = data.items.filter((rule) => rule.brand.toLowerCase() !== brand.toLowerCase());
      if (next) items.push({ brand, action: next, created_at: new Date().toISOString() });
      return { ...data, items: items.sort((a, b) => (a.brand.toLowerCase() < b.brand.toLowerCase() ? -1 : 1)) };
    });
    const text = next ? `${brand} ${said[next]}` : previous === "show" ? `${brand} follows the major-brand rule again` : `${brand} unhidden`;
    setNote({ id: ++seq.current, text, undo: undoable ? () => apply(brand, previous, next, false) : undefined });
    const done = next ? put.mutateAsync({ body: { brand, action: next } }) : remove.mutateAsync({ params: { query: { brand } } });
    done.then(
      () => {
        void queryClient.invalidateQueries({ queryKey: POPULAR });
        void queryClient.invalidateQueries({ queryKey: RULES });
      },
      (error: unknown) => {
        for (const [key, data] of saved) queryClient.setQueryData(key, data);
        const reason = isProblem(error) ? error.detail : "Check your connection and try again.";
        setNote({ id: ++seq.current, text: `Couldn't change ${brand}: ${reason}`, error: true });
      },
    );
  };
  return { apply, note, dismiss: useCallback(() => setNote(null), []) };
}

/** Hidden and always-shown brands, each one click from undone. Loading, empty, error and stale states inside. */
export function ManageBrands({ apply }: { apply: ReturnType<typeof useBrandRules>["apply"] }) {
  const [open, setOpen] = useState(false);
  const ready = useApiReady();
  const query = $api.useQuery("get", "/v1/popular-products/brands", LIST, { enabled: ready && open });
  const list = useRef<HTMLDivElement>(null);
  const rules = query.data?.items ?? [];
  const groups = [
    { action: "hide" as const, title: "Hidden", verb: "Unhide", items: rules.filter((r) => r.action === "hide") },
    { action: "show" as const, title: "Always shown", verb: "Stop showing", items: rules.filter((r) => r.action === "show") },
  ].filter((g) => g.items.length > 0);
  const clear = (brand: string, action: Action, index: number) => {
    apply(brand, null, action);
    // Focus stays in the list: the next brand's button, else the previous one, else the panel.
    requestAnimationFrame(() => {
      const buttons = list.current?.querySelectorAll("button") ?? [];
      (buttons[Math.min(index, buttons.length - 1)] ?? list.current)?.focus();
    });
  };
  let index = 0;
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Button>
          <ListFilter aria-hidden />
          Manage brands
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={6}
          collisionPadding={16}
          aria-label="Your brands"
          className="z-40 flex max-h-(--radix-popover-content-available-height) w-[min(22rem,calc(100vw-2rem))] origin-(--radix-popover-content-transform-origin) flex-col overflow-hidden rounded-lg border border-border bg-popover text-popover-foreground shadow-popover outline-none data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-96 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 duration-(--duration-fast)"
        >
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-data font-medium text-foreground">Your brands</h2>
            <p className="mt-0.5 text-label text-muted-foreground">For your workspace only. A shown brand stays even with 10 or more products in a report.</p>
          </div>
          {query.data && query.isError && <StaleLine what="Couldn't refresh your brands" error={query.error} asOf={query.dataUpdatedAt} retry={() => void query.refetch()} />}
          {!query.data ? (
            query.isError ? (
              <PanelError title="Couldn't load your brands" error={query.error} retry={() => void query.refetch()} />
            ) : (
              <div aria-busy className="flex flex-col gap-2.5 px-4 py-3">
                <span className="sr-only" role="status">
                  Loading your brands…
                </span>
                {["w-28", "w-20", "w-24"].map((w) => (
                  <div key={w} aria-hidden className="flex items-center justify-between">
                    <Skeleton className={cn("h-3.5", w)} />
                    <Skeleton className="h-(--button-h-sm) w-16" />
                  </div>
                ))}
              </div>
            )
          ) : groups.length === 0 ? (
            <div className="px-4 py-5 text-center">
              <p className="text-data font-medium text-foreground">No hidden brands yet</p>
              <p className="mt-1 text-label text-muted-foreground">Press the eye-off button beside a brand to leave its products out of Google popular.</p>
            </div>
          ) : (
            <div ref={list} tabIndex={-1} className="overflow-y-auto overscroll-contain py-1.5 outline-none">
              {groups.map((group) => (
                <section key={group.action} aria-label={`${group.title} brands`} className="px-2 py-1">
                  <h3 className="px-2 pb-1 text-micro font-medium tracking-wide text-subtle-foreground uppercase">
                    {group.title} <span className="tabular-nums">· {group.items.length}</span>
                  </h3>
                  <ul>
                    {group.items.map((rule) => {
                      const i = index++;
                      return (
                        <li key={rule.brand} className="flex min-h-9 items-center gap-2 rounded-md pl-2 hover:bg-accent">
                          <span className="min-w-0 flex-1 truncate text-data text-foreground" title={rule.brand}>
                            {rule.brand}
                          </span>
                          <Button size="sm" variant="ghost" aria-label={`${group.verb} ${rule.brand}`} onClick={() => clear(rule.brand, rule.action, i)}>
                            {group.verb}
                          </Button>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              ))}
              {query.data.next_cursor && <p className="px-4 py-2 text-label text-subtle-foreground">Showing the first 500 brands.</p>}
            </div>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

/** The change just made, with Undo; it slides up (transform) and leaves after 8 s unless hovered or focused. */
export function BrandToast({ note, dismiss }: { note: Note | null; dismiss: () => void }) {
  const [held, setHeld] = useState(false);
  useEffect(() => {
    if (!note || held) return;
    const timer = setTimeout(dismiss, 8000);
    return () => clearTimeout(timer);
  }, [note, held, dismiss]);
  return (
    <div role="status" aria-live="polite" className="pointer-events-none fixed inset-x-4 bottom-20 z-40 flex justify-center lg:bottom-6">
      <AnimatePresence>
        {note && (
          <m.div
            key={note.id}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, transition: { duration: duration.fast } }}
            transition={{ duration: duration.slow, ease: ease.out }}
            onPointerEnter={() => setHeld(true)}
            onPointerLeave={() => setHeld(false)}
            onFocus={() => setHeld(true)}
            onBlur={() => setHeld(false)}
            className={cn(
              "pointer-events-auto flex max-w-xl items-center gap-3 rounded-lg border bg-popover py-2 pr-2 pl-4 text-data text-popover-foreground shadow-popover",
              note.error ? "border-negative/40" : "border-border",
            )}
          >
            <span>{note.text}</span>
            {note.undo && (
              <Button size="sm" variant="ghost" onClick={note.undo}>
                Undo
              </Button>
            )}
          </m.div>
        )}
      </AnimatePresence>
    </div>
  );
}
