"use client";

import { useEffect, useRef } from "react";
import { LoaderCircle, TriangleAlert } from "lucide-react";

import { CopyButton } from "@/components/pulso/copy-button";
import { Button } from "@/components/ui/button";
import { isProblem } from "@/lib/api/client";

/**
 * The footer under a bounded list (DEC-166): what is shown, and one button that loads the next page or retries
 * a failed one. The button keeps focus while it loads; once nothing is left it goes, and focus moves to the
 * note rather than falling back to the page.
 */
export function LoadMore({
  note,
  label,
  more,
  pending,
  error,
  errorTitle,
  onLoad,
}: {
  note: string;
  label: string;
  more: boolean;
  pending: boolean;
  error: unknown;
  errorTitle: string;
  onLoad: () => void;
}) {
  const noteRef = useRef<HTMLParagraphElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const focused = useRef(false);
  useEffect(() => {
    if (!more && focused.current) {
      focused.current = false;
      noteRef.current?.focus();
    }
  }, [more]);
  // The error line lands above the focused button and pushes it down, out of a scroll box's view: bring it back (imp-136).
  useEffect(() => {
    if (error != null && focused.current) button.current?.scrollIntoView({ block: "nearest" });
  }, [error]);
  const problem = isProblem(error) ? error : null;

  return (
    <div className="flex flex-col gap-2">
      {error != null && (
        <p role="alert" className="text-label text-foreground">
          <TriangleAlert className="mr-1 inline size-3.5 align-[-2px] text-negative" aria-hidden />
          <span className="font-medium text-negative">{errorTitle}.</span>{" "}
          {problem ? (
            <>
              {problem.detail} <span className="font-mono text-subtle-foreground">Error ID {problem.request_id}</span>
            </>
          ) : (
            "The Pulso API didn't answer. When it runs on your PC, this also means the PC is off."
          )}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <p ref={noteRef} tabIndex={-1} aria-live="polite" className="mr-auto rounded-sm text-label text-subtle-foreground">
          {note}
        </p>
        {problem && <CopyButton value={problem.request_id} label="Copy error ID" />}
        {more && (
          <Button
            ref={button}
            size="sm"
            // Room below for the focus ring and the scroll box's padding when focus or the effect above scrolls to it.
            className="scroll-mb-4"
            aria-disabled={pending}
            onFocus={() => (focused.current = true)}
            onBlur={() => (focused.current = false)}
            onClick={() => !pending && onLoad()}
          >
            {pending && <LoaderCircle className="motion-safe:animate-spin" aria-hidden />}
            {pending ? "Loading…" : error != null ? "Retry" : label}
          </Button>
        )}
      </div>
    </div>
  );
}
