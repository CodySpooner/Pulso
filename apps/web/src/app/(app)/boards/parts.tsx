"use client";

import { useEffect, useState } from "react";
import { AnimatePresence } from "motion/react";
import * as m from "motion/react-m";
import type { LucideIcon } from "lucide-react";

import { duration, ease, spring } from "@/lib/motion";
import { cn } from "@/lib/utils";

/** A two-or-more option switch with a sliding thumb, like Discover's view toggle; `id` keeps each thumb its own. */
export function Segmented<T extends string>({ id, label, value, options, onChange }: { id: string; label: string; value: T; options: { value: T; label: string; icon?: LucideIcon }[]; onChange: (value: T) => void }) {
  return (
    <div role="group" aria-label={label} className="relative flex h-(--button-h-md) w-fit shrink-0 rounded-md border border-border bg-secondary p-0.5">
      {options.map(({ value: v, label: text, icon: Icon }) => (
        <button
          key={v}
          type="button"
          aria-pressed={value === v}
          onClick={() => onChange(v)}
          className={cn(
            "relative hit-area flex items-center gap-1.5 rounded-sm px-2.5 text-label font-medium transition-colors duration-(--duration-fast)",
            value === v ? "text-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {value === v && <m.span layoutId={id} transition={spring.snappy} className="absolute inset-0 rounded-sm segment-thumb" />}
          {Icon && <Icon className="relative size-3.5" aria-hidden />}
          <span className="relative">{text}</span>
        </button>
      ))}
    </div>
  );
}

export interface Note {
  text: string;
  tone: "done" | "error";
  action?: React.ReactNode;
}

/** The toast's note, which goes after 6 s (10 s for an error). */
export function useNote() {
  const [note, setNote] = useState<Note | null>(null);
  useEffect(() => {
    if (!note) return;
    const timer = setTimeout(() => setNote(null), note.tone === "error" ? 10_000 : 6_000);
    return () => clearTimeout(timer);
  }, [note]);
  return [note, setNote] as const;
}

/** A write's result with its one action (Undo, Retry, a link); polite, so it never takes focus (vault Design/UI
 *  States, Success / undo). The Testing Board's toast, with any action. */
export function Toast({ note }: { note: Note | null }) {
  return (
    <div role="status" aria-live="polite" className="pointer-events-none fixed inset-x-4 bottom-20 z-40 flex justify-center lg:bottom-6">
      <AnimatePresence>
        {note && (
          <m.div
            key={note.text}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, transition: { duration: duration.fast } }}
            transition={{ duration: duration.slow, ease: ease.out }}
            className={cn("pointer-events-auto flex max-w-xl items-center gap-3 rounded-lg border bg-popover px-4 py-2.5 text-data text-popover-foreground shadow-dialog", note.tone === "error" ? "border-negative/40" : "border-border")}
          >
            <span>{note.text}</span>
            {note.action}
          </m.div>
        )}
      </AnimatePresence>
    </div>
  );
}
