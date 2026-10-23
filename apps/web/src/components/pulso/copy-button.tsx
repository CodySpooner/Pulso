"use client";

import { useEffect, useState } from "react";
import { Check, Copy, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";

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

// How long each result shows before the label returns. A failure stays longer so it can be read.
const resultMs = { copied: 1200, failed: 4000 };

export function CopyButton({ value, label }: { value: string; label: string }) {
  const [result, setResult] = useState<keyof typeof resultMs | null>(null);
  useEffect(() => {
    if (!result) return;
    const timer = setTimeout(() => setResult(null), resultMs[result]);
    return () => clearTimeout(timer);
  }, [result]);
  return (
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
      <span aria-live="polite">{result === "copied" ? "Copied" : result === "failed" ? "Couldn’t copy" : label}</span>
    </Button>
  );
}
