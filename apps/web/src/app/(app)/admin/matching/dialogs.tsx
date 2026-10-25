"use client";

import { useState } from "react";
import { ArrowDownUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

import { Thumb } from "./compare";
import { mergeDirection, sourceLabel, type Cluster } from "./model";

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function Failure({ message }: { message: string | null }) {
  return message ? (
    <p role="alert" className="rounded-md bg-negative-muted px-3 py-2 text-data text-negative">
      {message}
    </p>
  ) : null;
}

/** Merge B into A (DEC-263): listings move; notes, tags and history stay on B and read through A. */
export function MergeDialog({
  clusters,
  open,
  onOpenChange,
  onConfirm,
}: {
  clusters: Cluster[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (from: Cluster, into: Cluster) => Promise<string | null>;
}) {
  const [swapped, setSwapped] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const direction = mergeDirection(clusters);
  if (!direction) return null;
  const { from, into } = swapped ? { from: direction.into, into: direction.from } : direction;
  const confirm = async () => {
    setBusy(true);
    setFailure(await onConfirm(from, into));
    setBusy(false);
  };
  return (
    <Dialog open={open} onOpenChange={(next) => (onOpenChange(next), setFailure(null), setSwapped(false))}>
      <DialogContent className="w-[min(32rem,calc(100vw-2rem))]">
        <DialogTitle>Merge two products</DialogTitle>
        <DialogDescription>
          <strong className="font-medium text-foreground">{from.name}</strong> merges into <strong className="font-medium text-foreground">{into.name}</strong>. Its page
          redirects there, and nothing is deleted.
        </DialogDescription>
        <dl className="grid gap-3 text-data">
          <div className="rounded-md border border-border p-3">
            <dt className="font-medium text-foreground">Moves to {into.name}</dt>
            <dd className="mt-1 text-muted-foreground">
              <span className="font-mono tabular-nums text-foreground">{from.listings}</span> {from.listings === 1 ? "listing" : "listings"}, one logged decision each
            </dd>
          </div>
          <div className="rounded-md border border-border p-3">
            <dt className="font-medium text-foreground">Stays on {from.name}, read through {into.name}</dt>
            <dd className="mt-1 text-muted-foreground">
              Your <span className="font-mono tabular-nums text-foreground">{from.notes}</span> {from.notes === 1 ? "note" : "notes"} and{" "}
              <span className="font-mono tabular-nums text-foreground">{from.tags}</span> {from.tags === 1 ? "tag" : "tags"}, plus forecasts, scores and daily features: history
              keeps its product id.
            </dd>
          </div>
        </dl>
        <Failure message={failure} />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Button variant="ghost" onClick={() => setSwapped((s) => !s)} disabled={busy}>
            <ArrowDownUp aria-hidden /> Swap direction
          </Button>
          <div className="flex gap-2">
            <DialogClose asChild>
              <Button variant="secondary">Cancel</Button>
            </DialogClose>
            <Button variant="primary" onClick={() => void confirm()} aria-disabled={busy}>
              {busy ? "Merging…" : `Merge ${plural(from.listings, "listing")}`}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Split ticked listings onto a new product (a cannot-link against the old one), or unlink them (no product). */
export function SplitDialog({
  clusters,
  open,
  onOpenChange,
  onConfirm,
}: {
  clusters: Cluster[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (action: "split" | "unlink", cluster: Cluster, listingIds: number[]) => Promise<string | null>;
}) {
  const splittable = clusters.filter((c) => c.listings > 1);
  const [chosen, setChosen] = useState(0);
  const [ticked, setTicked] = useState<ReadonlySet<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const cluster = splittable[Math.min(chosen, splittable.length - 1)];
  if (!cluster) return null;
  const stay = cluster.listings - ticked.size;
  const ready = ticked.size > 0 && stay > 0 && !busy;
  const reset = () => (setTicked(new Set()), setFailure(null));
  const confirm = async (action: "split" | "unlink") => {
    if (!ready) return;
    setBusy(true);
    setFailure(await onConfirm(action, cluster, [...ticked]));
    setBusy(false);
  };
  return (
    <Dialog open={open} onOpenChange={(next) => (onOpenChange(next), reset())}>
      <DialogContent className="w-[min(36rem,calc(100vw-2rem))]">
        <DialogTitle>Split a product</DialogTitle>
        <DialogDescription>Tick the listings that aren&apos;t this product. The matcher never pairs them with it again.</DialogDescription>
        {splittable.length > 1 && (
          <div role="group" aria-label="Product" className="flex gap-1 rounded-md bg-secondary p-1">
            {splittable.map((c, i) => (
              <button
                key={c.product_id}
                type="button"
                aria-pressed={c === cluster}
                onClick={() => (setChosen(i), reset())}
                className={cn("min-w-0 flex-1 truncate rounded-sm px-2 py-1 text-label", c === cluster ? "bg-card text-foreground shadow-card" : "text-muted-foreground")}
              >
                {c.name}
              </button>
            ))}
          </div>
        )}
        <fieldset className="flex max-h-72 flex-col gap-1 overflow-y-auto">
          <legend className="sr-only">Listings on {cluster.name}</legend>
          {cluster.members.map((member) => (
            <label key={member.listing_id} className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-1.5 hover:bg-accent has-[:checked]:bg-selected">
              <input
                type="checkbox"
                className="size-4 shrink-0 accent-brand"
                checked={ticked.has(member.listing_id)}
                onChange={(e) =>
                  setTicked((s) => {
                    const next = new Set(s);
                    if (e.target.checked) next.add(member.listing_id);
                    else next.delete(member.listing_id);
                    return next;
                  })
                }
              />
              <Thumb url={member.image_url} className="size-9 shrink-0 rounded-sm border border-border" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-data text-foreground">{member.title}</span>
                <span className="block truncate text-label text-subtle-foreground">
                  {sourceLabel(member.source)}
                  {member.vendor && ` · ${member.vendor}`}
                </span>
              </span>
            </label>
          ))}
        </fieldset>
        {cluster.listings > cluster.members.length && (
          <p className="text-label text-subtle-foreground">Showing the first {cluster.members.length} of {cluster.listings} listings.</p>
        )}
        <p role="status" className="text-data text-muted-foreground">
          <span className="font-mono tabular-nums text-foreground">{ticked.size}</span> move ·{" "}
          <span className="font-mono tabular-nums text-foreground">{stay}</span> stay on {cluster.name}
          {stay === 0 && <span className="text-warning"> · one listing must stay; merge moves a whole product</span>}
        </p>
        <Failure message={failure} />
        <div className="flex flex-wrap justify-end gap-2">
          <DialogClose asChild>
            <Button variant="ghost">Cancel</Button>
          </DialogClose>
          <Button variant="secondary" onClick={() => void confirm("unlink")} aria-disabled={!ready}>
            {ticked.size ? `Unlink ${plural(ticked.size, "listing")}` : "Unlink"}
          </Button>
          <Button variant="primary" onClick={() => void confirm("split")} aria-disabled={!ready}>
            {busy ? "Splitting…" : ticked.size ? `Split ${plural(ticked.size, "listing")} off` : "Split off"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
