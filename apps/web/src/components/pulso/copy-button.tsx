"use client";

import { useEffect, useState } from "react";
import { Check, Copy, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/** Writes `value` to the clipboard. Resolves false, never rejects, when the browser denies the write or has
 * no clipboard API (an insecure origin). */
export async function copyText(value: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return false;
  }
}

// What each result says and how long it shows before the label returns. A failure stays longer so it can be
// read, and its hint says why and what to do next (vault Design/UI States). The why stays general because
// copyText can't tell the causes apart honestly: no clipboard API (an insecure origin) or a refused write
// (permission, focus or policy) all mean the clipboard isn't available.
// ponytail: the hint names "the ID" because every consumer copies an ID shown beside the button in a
// SelectableId; take the hint as a prop when one copies something else. The tooltip
// shows the why and the next step a line each (`\n`); the announcement reads it as one space.
export const results = {
  copied: { text: "Copied", ms: 1200 },
  failed: { text: "Couldn’t copy", hint: "The clipboard isn’t available here.\nSelect the ID to copy it.", ms: 5000 },
};

/** The ID a CopyButton copies, selectable without the clipboard API: one click (`select-all`) or keyboard focus
 * selects the whole ID, ready for Ctrl/⌘+C. Screen readers get a read-only textbox named `label`. */
// ponytail: a span, not a read-only <input>, so the ID stays in page text selection and keeps its inline styling.
export function SelectableId({ value, label, className, ...props }: React.ComponentProps<"span"> & { value: string; label: string }) {
  return (
    <span
      {...props}
      role="textbox"
      aria-readonly
      aria-label={label}
      tabIndex={0}
      onFocus={(e) => getSelection()?.selectAllChildren(e.currentTarget)}
      className={cn("relative hit-area rounded-sm select-all", className)}
    >
      {value}
    </span>
  );
}

export function CopyButton({ value, label }: { value: string; label: string }) {
  const [result, setResult] = useState<keyof typeof results | null>(null);
  useEffect(() => {
    if (!result) return;
    const timer = setTimeout(() => setResult(null), results[result].ms);
    return () => clearTimeout(timer);
  }, [result]);
  return (
    // The hint opens by itself while the failure shows (no hover needed) and closes with it; Esc dismisses both.
    <Tooltip open={result === "failed"}>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setResult(null); // so a retry that fails again is announced again and restarts the timer
            void copyText(value).then((ok) => setResult(ok ? "copied" : "failed"));
          }}
        >
          {result === "copied" ? (
            <Check className="text-positive" aria-hidden />
          ) : result === "failed" ? (
            <TriangleAlert className="text-negative" aria-hidden />
          ) : (
            <Copy aria-hidden />
          )}
          <span aria-live="polite">
            {result ? results[result].text : label}
            {result === "failed" && <span className="sr-only">. {results.failed.hint}</span>}
          </span>
        </Button>
      </TooltipTrigger>
      <TooltipContent
        side="bottom"
        sideOffset={8} // clears the button's 4px focus ring
        onEscapeKeyDown={() => setResult(null)}
        // Opened by state, not hover, so Radix marks it instant-open: give it the same fade and scale-in.
        className="whitespace-pre-line data-[state=instant-open]:animate-in data-[state=instant-open]:fade-in-0 data-[state=instant-open]:zoom-in-96"
      >
        {results.failed.hint}
      </TooltipContent>
    </Tooltip>
  );
}
