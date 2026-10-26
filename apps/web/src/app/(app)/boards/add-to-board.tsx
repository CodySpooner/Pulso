"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { Command } from "cmdk";
import { BookmarkPlus, LoaderCircle, Plus } from "lucide-react";
import { Popover } from "radix-ui";

import { useApiReady } from "@/components/data-health/api";
import { PanelError } from "@/components/data-health/atoms";
import { isTyping } from "@/components/shell/app-shell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, fetchClient, isProblem } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { reasonOf } from "../testing/model";
import { boardsInit, type Board } from "./model";
import { Toast, useNote, type Note } from "./parts";

interface Product {
  id: string;
  title: string;
}

// The page's AddToBoardHost shows what a picker did; a picker closes before its add answers.
let say: (note: Note) => void = () => {};
const TAKEN = "You already have a board with that name. Archived boards count too.";
const item =
  "flex h-8 cursor-pointer items-center gap-2 rounded-md px-2 text-data text-muted-foreground outline-none select-none pointer-coarse:h-(--hit-target) data-[selected=true]:bg-accent data-[selected=true]:text-foreground";
const field =
  "h-9 w-full bg-transparent px-3 text-data text-foreground -outline-offset-2 placeholder:text-subtle-foreground max-md:text-base";
const NEW = "new board";
// Names only: cmdk's fuzzy default would also match a query's letters scattered through the ids. New board always
// stays; cmdk's forceMount would keep it too, but unregistered, so with no boards nothing would be selected.
const byName = (value: string, search: string, keywords?: string[]) => (value === NEW || (keywords?.[0] ?? "").toLowerCase().includes(search.trim().toLowerCase()) ? 1 : 0);
const plain = <T,>(request: Promise<T>) => request.catch((error: unknown) => ({ data: undefined, error }));

/** WF-3c (imp-455, DEC-350): Add to board, as an icon (a Discover card or row) or a labelled button (the Product
 *  Page). The page needs an AddToBoardHost for B and the toast. */
export function AddToBoard({ product, labelled, className }: { product: Product; labelled?: boolean; className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Button
          data-add-to-board
          size={labelled ? "md" : "icon-sm"}
          variant={labelled ? "secondary" : "ghost"}
          aria-label={labelled ? undefined : `Add ${product.title} to a board`}
          aria-keyshortcuts="B"
          title="Add to board · B"
          className={className}
        >
          <BookmarkPlus aria-hidden />
          {labelled && "Add to board"}
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={4}
          collisionPadding={16}
          aria-label={`Add ${product.title} to a board`}
          onClick={(e) => e.stopPropagation()} // portalled, yet React bubbles it to a Discover row, which opens the product
          className="z-50 w-72 max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border border-border bg-popover text-popover-foreground shadow-popover duration-(--duration-fast) data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-96"
        >
          <Picker product={product} close={() => setOpen(false)} />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

/** The board search: active boards, most recently active first (the API's order, and every add bumps it), then
 *  New board. Typing a name that's free offers New board “name”, so a new board is one Enter. */
function Picker({ product, close }: { product: Product; close: () => void }) {
  const client = useQueryClient();
  const boards = $api.useQuery("get", "/v1/boards", boardsInit(false), { enabled: useApiReady() });
  const [query, setQuery] = useState("");
  const [naming, setNaming] = useState<{ name: string; error: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const search = useRef<HTMLInputElement>(null);
  const name = query.trim();
  const offer = name && !boards.data?.some((b) => b.name === name) ? name : null;

  const add = async (board: Pick<Board, "id" | "name">) => {
    close();
    const { data, error } = await plain(fetchClient.POST("/v1/boards/{board_id}/items", { params: { path: { board_id: board.id } }, body: { product_ids: [product.id] } }));
    void client.invalidateQueries({ queryKey: ["get", "/v1/boards"], refetchType: "all" }); // the board moves to the top
    void client.invalidateQueries({ queryKey: ["get", "/v1/boards/{board_id}/items"] });
    if (!data)
      return say({
        tone: "error",
        text: `Couldn't add to ${board.name}: ${reasonOf(error)}`,
        action: (
          <Button size="sm" variant="ghost" onClick={() => void add(board)}>
            Retry
          </Button>
        ),
      });
    say({
      tone: "done",
      text: data.added.length ? `Added to ${board.name}` : `Already on ${board.name}`,
      action: (
        <Button asChild size="sm" variant="ghost">
          <Link href={`/boards/${board.id}`}>Open board</Link>
        </Button>
      ),
    });
  };
  const create = async (text: string) => {
    if (busy) return;
    setBusy(true);
    const { data, error } = await plain(fetchClient.POST("/v1/boards", { body: { name: text } }));
    setBusy(false);
    if (data) return void add(data);
    setNaming({ name: text, error: isProblem(error) && error.status === 409 ? TAKEN : `Couldn't create the board: ${reasonOf(error)}` });
  };

  if (naming)
    return (
      <form
        className="flex flex-col"
        onSubmit={(e) => {
          e.preventDefault();
          if (naming.name.trim()) void create(naming.name.trim());
        }}
      >
        <input
          autoFocus
          aria-label="New board name"
          placeholder="New board name"
          value={naming.name}
          maxLength={80}
          aria-invalid={!!naming.error}
          aria-describedby="new-board-hint"
          onChange={(e) => setNaming({ name: e.target.value, error: null })}
          className={cn(field, "border-b border-border-subtle")}
        />
        <p id="new-board-hint" role={naming.error ? "alert" : undefined} className={cn("flex items-center gap-1.5 px-3 py-2 text-label", naming.error ? "text-negative" : "text-subtle-foreground")}>
          {busy && <LoaderCircle className="size-3.5 motion-safe:animate-spin" aria-hidden />}
          {busy ? "Creating…" : (naming.error ?? `Enter creates it and adds ${product.title}. Esc cancels.`)}
        </p>
      </form>
    );

  return (
    <Command label="Boards" filter={byName} loop>
      <Command.Input ref={search} autoFocus value={query} onValueChange={setQuery} maxLength={80} placeholder="Find or name a board…" className={cn(field, "border-b border-border-subtle")} />
      <Command.List className="max-h-72 scroll-py-1 overflow-y-auto overscroll-contain p-1">
        {boards.isPending ? (
          <Command.Loading label="Loading your boards…">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="m-1 h-6" />
            ))}
          </Command.Loading>
        ) : boards.isError && !boards.data ? (
          <PanelError title="Couldn't load your boards" error={boards.error} retry={() => void boards.refetch().then(() => search.current?.focus())} />
        ) : boards.data?.length ? (
          <Command.Group heading="Recent boards" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-1 [&_[cmdk-group-heading]]:pb-1.5 [&_[cmdk-group-heading]]:text-micro [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-subtle-foreground [&_[cmdk-group-heading]]:uppercase">
            {boards.data.map((b) => (
              <Command.Item key={b.id} value={b.id} keywords={[b.name]} onSelect={() => void add(b)} className={item}>
                <span className="min-w-0 flex-1 truncate">{b.name}</span>
                <span className="font-mono text-label text-subtle-foreground tabular-nums">{b.item_count}</span>
              </Command.Item>
            ))}
          </Command.Group>
        ) : (
          <p className="px-2 py-1.5 text-label text-muted-foreground">No boards yet. Name your first one above.</p>
        )}
        {boards.isRefetchError && <p className="px-2 py-1.5 text-label text-warning">Couldn&apos;t refresh your boards. This list may be out of date.</p>}
        {/* After the list answers, so cmdk highlights the most recent board rather than this. */}
        {!boards.isPending && (
          <>
            <Command.Separator alwaysRender className="my-1 h-px bg-border-subtle" />
            <Command.Item value={NEW} onSelect={() => (offer ? void create(offer) : setNaming({ name, error: null }))} className={item}>
              {busy ? <LoaderCircle className="size-4 motion-safe:animate-spin" aria-hidden /> : <Plus className="size-4" aria-hidden />}
              <span className="min-w-0 truncate">{offer ? <>New board “{offer}”</> : "New board…"}</span>
            </Command.Item>
          </>
        )}
      </Command.List>
    </Command>
  );
}

/** A page's Add to board keys and toast. B opens the focused product's picker (the product a card, row or focused
 *  element sits in, marked data-product); on a `page` that is one product, B opens its one picker from anywhere. */
export function AddToBoardHost({ page }: { page?: boolean }) {
  const [note, setNote] = useNote();
  useEffect(() => {
    say = setNote;
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== "b" || e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return;
      const scope = page ? document : e.target instanceof Element ? e.target.closest("[data-product]") : null;
      const trigger = scope?.querySelector<HTMLElement>("[data-add-to-board]");
      if (!trigger) return;
      e.preventDefault();
      trigger.click();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      say = () => {};
    };
  }, [page, setNote]);
  return <Toast note={note} />;
}
