"use client";

import Link from "next/link";
import { TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";

import { CopyButton, SelectableId } from "./copy-button";
import { EmptyState } from "./empty-state";

/** The server-side error id Next attaches to errors from Server Components (matches the logs). */
export function errorDigest(error: unknown): string | undefined {
  return error instanceof Error && "digest" in error && typeof error.digest === "string" ? error.digest : undefined;
}

// ErrorState (vault Design/UI States): cause, fix, Retry and the error id in mono. `page` replaces the
// route (its h1), `inline` sits inside one panel while the rest of the page keeps working.
export function ErrorState({
  title,
  error,
  retry,
  variant = "page",
}: {
  title: string;
  error: unknown;
  retry: () => void;
  variant?: "page" | "inline";
}) {
  const digest = errorDigest(error);
  return (
    <EmptyState
      icon={TriangleAlert}
      tone="error"
      title={title}
      headingLevel={variant === "page" ? "h1" : "h3"}
      action={
        <>
          <Button variant="primary" onClick={retry}>
            Retry
          </Button>
          {digest && <CopyButton value={digest} label="Copy error ID" />}
          {variant === "page" && (
            <Button asChild variant="ghost">
              <Link href="/">Go to Daily Pulse</Link>
            </Button>
          )}
        </>
      }
    >
      <p>Something failed while loading this. A retry usually fixes it; if it keeps failing, the error ID matches the server logs.</p>
      {digest && (
        <p className="mt-2 font-mono text-label text-subtle-foreground">
          Error ID <SelectableId value={digest} label="Error ID" />
        </p>
      )}
    </EmptyState>
  );
}
