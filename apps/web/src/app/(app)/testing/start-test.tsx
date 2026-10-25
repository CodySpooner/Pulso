"use client";

import { useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { CircleCheck, FlaskConical } from "lucide-react";

import { Button } from "@/components/ui/button";
import { fetchClient, isProblem } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { reasonOf } from "./model";

const link = "link-inline rounded-sm font-medium underline decoration-border-strong underline-offset-2 hover:decoration-current";

/** The Product Page's "Start a test": one press puts the product in Idea, then links to it on the board. A product
 *  with an open test already (409 `conflict`) says so and links to the board too. */
export function StartTest({ productId, className }: { productId: string; className?: string }) {
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<{ text: string; href: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const start = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    const { data, error } = await fetchClient.POST("/v1/tests", { body: { product_id: productId } }).catch((e: unknown) => ({ data: undefined, error: e }));
    setBusy(false);
    if (data) setDone({ text: "Added to Idea.", href: `/testing?test=${data.id}` });
    else if (isProblem(error) && error.code === "conflict") setDone({ text: "Already on the board.", href: "/testing" });
    else return setError(`Couldn't start a test: ${reasonOf(error)}`);
    void client.invalidateQueries({ queryKey: ["get", "/v1/tests"] });
  };
  return (
    <div className={cn("flex flex-col items-start gap-1.5 sm:items-end", className)}>
      {done ? (
        <p role="status" className="flex h-(--button-h-md) items-center gap-1.5 text-data text-foreground">
          <CircleCheck className="size-4 text-positive" aria-hidden />
          {done.text}
          <Link href={done.href} className={link}>
            Open the board
          </Link>
        </p>
      ) : (
        <Button onClick={start} aria-disabled={busy}>
          <FlaskConical aria-hidden />
          {busy ? "Starting…" : "Start a test"}
        </Button>
      )}
      <p role="alert" className="max-w-xs text-label text-negative empty:hidden sm:text-right">
        {error}
      </p>
    </div>
  );
}
