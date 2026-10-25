"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSortable } from "@dnd-kit/sortable";
import { ArrowDownToLine, ArrowUpToLine, ChevronDown, ChevronUp, GripVertical, ImageOff, MoreHorizontal, Trash2 } from "lucide-react";
import { DropdownMenu } from "radix-ui";

import { Ago } from "@/components/data-health/atoms";
import { Button } from "@/components/ui/button";
import { duration, ease } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { Thumb } from "../../admin/matching/compare";
import { autosave, type Item, type SaveState } from "../model";
import { Freshness, Lifecycle, Margin, Merged, Price, ScoreValue, StatList } from "./stats";

export interface CardProps {
  item: Item;
  index: number;
  count: number;
  now: number;
  selected: boolean;
  onSelect: (shift: boolean) => void;
  onMove: (to: number) => void;
  onRemove: () => void;
  saveNote: (note: string | null) => Promise<unknown>;
}

const translate = (t: { x: number; y: number } | null) => (t ? `translate3d(${t.x}px, ${t.y}px, 0)` : undefined);
// Neighbours shift with the standard ease at the base duration; the global reduced-motion rule clamps it.
const SHIFT = { duration: duration.base * 1000, easing: `cubic-bezier(${ease.standard.join(", ")})` };

function useCard(item: Item) {
  const { setNodeRef, transform, transition, isDragging, attributes, listeners, setActivatorNodeRef } = useSortable({ id: item.product_id, transition: SHIFT });
  return { setNodeRef, isDragging, style: { transform: translate(transform), transition }, handle: { attributes, listeners, setActivatorNodeRef } };
}

/** A grid card: image, product link, stats, note, added date and freshness. Select and reorder sit on the image, shown on hover, focus,
 *  selection and touch; every move is also in the … menu, so a drag is never required (vault Features/Boards). */
export function Card(props: CardProps) {
  const { item, now, selected, onSelect } = props;
  const { setNodeRef, style, isDragging, handle } = useCard(item);
  const note = useNote(item, props.saveNote);
  const shown = cn("opacity-0 transition-opacity duration-(--duration-fast) group-hover:opacity-100 group-focus-within:opacity-100 pointer-coarse:opacity-100", selected && "opacity-100");
  return (
    <li ref={setNodeRef} style={style} className={cn("relative", isDragging && "z-10")}>
      <article
        aria-label={item.name}
        className={cn(
          // Under 480px a card lies on its side (image left), so a phone shows about twice as many.
          "group flex h-full flex-col overflow-hidden rounded-xl border max-[479px]:flex-row bg-card shadow-card transition-[border-color,scale,box-shadow] duration-(--duration-fast)",
          selected ? "border-brand ring-1 ring-brand" : "border-border hover:border-border-strong",
          isDragging && "shadow-popover motion-safe:scale-[1.02]",
        )}
      >
        <div className="relative max-[479px]:w-32 max-[479px]:shrink-0">
          <Picture item={item} className="aspect-[4/3] w-full max-[479px]:aspect-auto max-[479px]:h-full max-[479px]:min-h-32" />
          <Select item={item} selected={selected} onSelect={onSelect} className={cn("absolute top-2 left-2 rounded-md bg-card/90 p-1.5 shadow-card", shown)} />
          <Handle item={item} {...handle} className={cn("absolute top-2 right-2 bg-card/90 shadow-card", shown)} />
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-2 p-3">
          <ProductLink item={item} className="line-clamp-2 text-body" />
          <Merged item={item} />
          <StatList item={item} now={now} />
          <NoteBox item={item} note={note} />
          <footer className="mt-auto flex min-h-7 items-center justify-between gap-2 text-micro text-subtle-foreground">
            <NoteStatus note={note} fallback={<>Added <Ago iso={item.added_at} now={now} source="When it was added to this board" /></>} />
            <span className="flex items-center gap-1">
              <Freshness item={item} now={now} />
              <CardMenu {...props} />
            </span>
          </footer>
        </div>
      </article>
    </li>
  );
}

/** A table row: the same fields and actions as a card, one product a line, numbers right-aligned (vault Design/Tables &
 *  Data Density). */
export function Row(props: CardProps) {
  const { item, index, now, selected, onSelect } = props;
  const { setNodeRef, style, isDragging, handle } = useCard(item);
  const note = useNote(item, props.saveNote);
  return (
    <tr ref={setNodeRef} style={style} className={cn("group relative border-b border-border-subtle hover:bg-(--table-row-hover)", selected ? "bg-selected shadow-[inset_2px_0_0_var(--brand)]" : "bg-card", isDragging && "z-10 shadow-popover")}>
      <td className="w-px py-2 pl-3">
        <Select item={item} selected={selected} onSelect={onSelect} />
      </td>
      <td className="w-px py-2">
        <Handle item={item} {...handle} />
      </td>
      <td className="w-px py-2 pr-2 text-right font-mono text-label text-subtle-foreground tabular-nums">{index + 1}</td>
      <th scope="row" className="py-2 pr-4 text-left font-normal">
        <div className="flex min-w-48 items-center gap-2.5">
          <Picture item={item} className="size-9 shrink-0 rounded-md border border-border" compact />
          <ProductLink item={item} className="line-clamp-2 text-data" />
        </div>
      </th>
      <td className="py-2 pr-3 text-right">
        <Price item={item} now={now} />
      </td>
      <td className="py-2 pr-3 text-right">
        <Margin item={item} now={now} />
      </td>
      <td className="py-2 pr-3 text-right">
        <ScoreValue score={item.trend} label="Trend Score" now={now} />
      </td>
      <td className="py-2 pr-3">
        <Lifecycle item={item} now={now} />
      </td>
      <td className="py-2 pr-3 text-right">
        <ScoreValue score={item.saturation} label="Saturation" now={now} />
      </td>
      <td className="min-w-40 py-1.5 pr-4">
        <Merged item={item} />
        <NoteBox item={item} note={note} rows={1} />
        <NoteStatus note={note} className="px-2 text-micro" />
      </td>
      <td className="py-2 pr-3 text-label">
        <Freshness item={item} now={now} />
      </td>
      <td className="py-2 pr-2 text-right text-label whitespace-nowrap text-subtle-foreground">
        <Ago iso={item.added_at} now={now} source="When it was added to this board" />
      </td>
      <td className="w-px py-2 pr-3">
        <CardMenu {...props} />
      </td>
    </tr>
  );
}

/** The product image; a product without one says so, which is its "no source yet" (DEC-040). */
function Picture({ item, className, compact }: { item: Item; className?: string; compact?: boolean }) {
  if (item.image_url) return <Thumb url={item.image_url} className={cn("object-cover", className)} />;
  return (
    <div title="No image yet: no listing of this product has one" className={cn("grid place-items-center bg-secondary text-subtle-foreground", className)}>
      <span className="flex flex-col items-center gap-1 text-label">
        <ImageOff className="size-5" strokeWidth={1.5} aria-hidden />
        {!compact && "No image yet"}
      </span>
    </div>
  );
}

function ProductLink({ item, className }: { item: Item; className?: string }) {
  return (
    <Link href={`/products/${item.product_id}`} className={cn("rounded-sm font-medium break-words text-foreground underline-offset-2 outline-none hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring", className)}>
      {item.name}
    </Link>
  );
}

/** Shift-click selects every card from the last one picked (vault Features/Boards, Multi-select). */
function Select({ item, selected, onSelect, className }: { item: Item; selected: boolean; onSelect: (shift: boolean) => void; className?: string }) {
  return (
    <label className={cn("relative hit-area flex cursor-pointer", className)}>
      <input type="checkbox" checked={selected} onChange={() => {}} onClick={(e) => onSelect(e.shiftKey)} aria-label={`Select ${item.name}`} className="relative z-10 size-4 cursor-pointer accent-(--brand)" />
    </label>
  );
}

type Sortable = Pick<ReturnType<typeof useSortable>, "attributes" | "listeners" | "setActivatorNodeRef">;

/** The reorder handle: drag it, or focus it and press Space, the arrow keys, then Space (dnd-kit's keyboard sensor). */
function Handle({ item, attributes, listeners, setActivatorNodeRef, className }: Sortable & { item: Item; className?: string }) {
  return (
    <Button ref={setActivatorNodeRef} size="icon-sm" variant="ghost" {...attributes} {...listeners} aria-label={`Reorder ${item.name}`} className={cn("cursor-grab touch-none active:cursor-grabbing", className)}>
      <GripVertical aria-hidden />
    </Button>
  );
}

function CardMenu({ item, index, count, onMove, onRemove }: CardProps) {
  const moves = [
    { label: "Move to top", icon: ArrowUpToLine, to: 0, off: index === 0 },
    { label: "Move up", icon: ChevronUp, to: index - 1, off: index === 0 },
    { label: "Move down", icon: ChevronDown, to: index + 1, off: index === count - 1 },
    { label: "Move to bottom", icon: ArrowDownToLine, to: count - 1, off: index === count - 1 },
  ];
  const itemClass = "flex h-8 cursor-pointer items-center gap-2 rounded-md px-2 text-data outline-none select-none pointer-coarse:h-(--hit-target) data-disabled:pointer-events-none data-disabled:opacity-50 data-highlighted:bg-accent [&_svg]:size-4 [&_svg]:text-muted-foreground";
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button size="icon-sm" variant="ghost" aria-label={`More for ${item.name}`} className="-mr-1.5">
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={4}
          className="z-50 min-w-44 rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-popover duration-(--duration-fast) data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-96"
        >
          {moves.map(({ label, icon: Icon, to, off }) => (
            <DropdownMenu.Item key={label} disabled={off} onSelect={() => onMove(to)} className={itemClass}>
              <Icon aria-hidden />
              {label}
            </DropdownMenu.Item>
          ))}
          <DropdownMenu.Separator className="-mx-1 my-1 h-px bg-border-subtle" />
          <DropdownMenu.Item onSelect={onRemove} className={cn(itemClass, "text-negative [&_svg]:text-negative")}>
            <Trash2 aria-hidden />
            Remove from board
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

type Note = ReturnType<typeof useNote>;

/** The card's note and its autosave (model.ts). The text is the field's own once loaded, so a refetch never
 *  overwrites typing; a pending edit saves when the card unmounts (a view switch, leaving the page). */
function useNote(item: Item, save: (note: string | null) => Promise<unknown>) {
  const [text, setText] = useState(item.note ?? "");
  const [state, setState] = useState<SaveState | null>(null);
  const [saver] = useState(() => autosave((t) => save(t.trim() || null), setState));
  useEffect(() => () => void saver.flush(), [saver]);
  useEffect(() => {
    if (state !== "saved") return;
    const timer = setTimeout(() => setState(null), 2_000); // "Note saved", then the added date again
    return () => clearTimeout(timer);
  }, [state]);
  return { text, state, retry: () => void saver.flush(), change: (t: string) => (setText(t), saver.change(t)), blur: () => void saver.flush() };
}

function NoteBox({ item, note, rows = 2 }: { item: Item; note: Note; rows?: 1 | 2 }) {
  return (
    <textarea
      value={note.text}
      onChange={(e) => note.change(e.target.value)}
      onBlur={note.blur}
      rows={rows}
      maxLength={10_000}
      placeholder="Add a note…"
      aria-label={`Note on ${item.name}`}
      aria-invalid={note.state === "error"}
      className={cn(
        "-mx-2 block field-sizing-content max-h-[calc(8lh+0.5rem)] w-[calc(100%+1rem)] resize-none rounded-md border border-transparent bg-transparent px-2 py-1 text-data text-muted-foreground outline-none focus:text-foreground placeholder:text-subtle-foreground hover:border-border focus:border-input focus:bg-background focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring aria-invalid:border-negative/60",
        rows === 2 ? "min-h-[calc(2lh+0.5rem)]" : "min-h-[calc(1lh+0.5rem)]",
      )}
    />
  );
}

/** Saving, saved, or the failure with Retry; the text stays in the field either way. Polite, so it never moves focus. */
function NoteStatus({ note, fallback, className }: { note: Note; fallback?: React.ReactNode; className?: string }) {
  const { state } = note;
  return (
    <p aria-live="polite" className={cn("min-w-0", className)}>
      {state === "error" ? (
        <span className="text-negative">
          Couldn&apos;t save the note.{" "}
          <button type="button" onClick={note.retry} className="relative hit-area rounded-sm font-medium underline underline-offset-2 outline-none focus-visible:outline-2 focus-visible:outline-ring">
            Retry
          </button>
        </span>
      ) : state === "pending" || state === "saving" ? (
        <span className="text-subtle-foreground">Saving…</span>
      ) : state === "saved" ? (
        <span className="text-subtle-foreground">Note saved</span>
      ) : (
        fallback
      )}
    </p>
  );
}
