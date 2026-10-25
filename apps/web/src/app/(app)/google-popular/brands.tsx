"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence } from "motion/react";
import * as m from "motion/react-m";
import { useQueryClient, type InfiniteData, type QueryKey } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { $api, isProblem } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { duration, ease } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { patchPages, type Action } from "./model";

type Page = components["schemas"]["PopularPage"];
interface Note {
  id: number;
  text: string;
  undo?: () => void;
  error?: boolean;
}

const POPULAR: QueryKey = ["get", "/v1/popular-products"];
const said = { hide: "hidden", show: "always shown" } as const;

/** The workspace brand list (DEC-277): set or clear a rule optimistically, then refetch; every change can be undone. */
export function useBrandRules() {
  const queryClient = useQueryClient();
  const put = $api.useMutation("put", "/v1/popular-products/brands");
  const remove = $api.useMutation("delete", "/v1/popular-products/brands");
  const [note, setNote] = useState<Note | null>(null);
  const seq = useRef(0); // each note a new key, so the toast re-enters

  const apply = (brand: string, next: Action | null, previous: Action | null, undoable = true) => {
    const saved = queryClient.getQueriesData<InfiniteData<Page>>({ queryKey: POPULAR });
    void queryClient.cancelQueries({ queryKey: POPULAR });
    for (const [key, data] of saved) {
      const all = (key[2] as { params?: { query?: { include_major_brands?: boolean } } } | undefined)?.params?.query?.include_major_brands === true;
      if (data) queryClient.setQueryData(key, patchPages(data, brand, next, all));
    }
    const text = next ? `${brand} ${said[next]}` : previous === "show" ? `${brand} no longer always shown` : `${brand} shown again`;
    setNote({ id: ++seq.current, text, undo: undoable ? () => apply(brand, previous, next, false) : undefined });
    const done = next ? put.mutateAsync({ body: { brand, action: next } }) : remove.mutateAsync({ params: { query: { brand } } });
    done.then(
      () => void queryClient.invalidateQueries({ queryKey: POPULAR }),
      (error: unknown) => {
        for (const [key, data] of saved) queryClient.setQueryData(key, data);
        const reason = isProblem(error) ? error.detail : "Check your connection and try again.";
        setNote({ id: ++seq.current, text: `Couldn't change ${brand}: ${reason}`, error: true });
      },
    );
  };
  return { apply, note, dismiss: useCallback(() => setNote(null), []) };
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
