"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Archive, Bookmark, Plus } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { Ago, PanelError, StaleLine } from "@/components/data-health/atoms";
import { EmptyState } from "@/components/pulso/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, isProblem } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { Thumb } from "../admin/matching/compare";
import { reasonOf } from "../testing/model";
import { boardsInit, boardsKey, itemsInit, type Board } from "./model";
import { Segmented } from "./parts";

const GRID = "grid gap-3 min-[480px]:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4";
const plural = (n: number, one: string) => `${n.toLocaleString("en-US")} ${one}${n === 1 ? "" : "s"}`;

// WF-3b (DEC-329): every board as a tile, newest activity first (the API's order), active or archived (?archived=1).
// "New board" opens a name field in a new first tile; the board lands there, focused, so Enter opens it.
export function BoardsIndex() {
  const archived = useSearchParams().get("archived") === "1";
  const list = $api.useQuery("get", "/v1/boards", boardsInit(archived), { enabled: useApiReady() });
  const [creating, setCreating] = useState(false);
  const created = useRef<string | null>(null); // a new board's tile takes focus once the list has it
  const filter = (next: "active" | "archived") => {
    setCreating(false);
    window.history.replaceState(null, "", next === "archived" ? "?archived=1" : window.location.pathname);
  };

  useEffect(() => {
    if (created.current && list.data?.some((b) => b.id === created.current)) {
      document.getElementById(`board-${created.current}`)?.focus();
      created.current = null;
    }
  }, [list.data]);

  const toolbar = (
    <div className="flex items-center justify-between gap-3">
      <Segmented
        id="boards-filter"
        label="Show boards"
        value={archived ? "archived" : "active"}
        options={[
          { value: "active", label: "Active" },
          { value: "archived", label: "Archived", icon: Archive },
        ]}
        onChange={filter}
      />
      {!archived && list.data && list.data.length > 0 && (
        <Button variant="primary" onClick={() => setCreating(true)} disabled={creating}>
          <Plus aria-hidden />
          New board
        </Button>
      )}
    </div>
  );

  if (!list.data)
    return (
      <div className="flex flex-col gap-4">
        {toolbar}
        {list.isError ? (
          <section aria-label="Boards" className="rounded-xl border border-border bg-card shadow-card">
            <PanelError title="Couldn't load your boards" headingLevel="h2" size="md" error={list.error} retry={() => void list.refetch()} />
          </section>
        ) : (
          <TilesSkeleton />
        )}
      </div>
    );

  const boards = list.data;
  const done = (board: Board) => {
    created.current = board.id;
    setCreating(false);
  };
  return (
    <div className="flex flex-col gap-4">
      {toolbar}
      {list.isRefetchError && <StaleLine boxed what="Couldn't refresh your boards" error={list.error} asOf={list.dataUpdatedAt} retry={() => void list.refetch()} />}
      {boards.length === 0 && !creating ? (
        <section aria-label="Boards" className="rounded-xl border border-border bg-card shadow-card">
          {archived ? (
            <EmptyState icon={Archive} headingLevel="h2" title="No archived boards" action={<Button onClick={() => filter("active")}>Show active boards</Button>}>
              Archive a board from its page to put it here. Its cards and notes stay with it.
            </EmptyState>
          ) : (
            <EmptyState icon={Bookmark} headingLevel="h2" title="Create a board to collect ideas" action={<NewBoard onDone={done} className="w-full max-w-sm" />}>
              A board holds products for a niche, a season or a batch to test, in your order and with your notes.
            </EmptyState>
          )}
        </section>
      ) : (
        <ul aria-label={archived ? "Archived boards" : "Boards"} className={GRID}>
          {creating && (
            <li className="flex flex-col justify-center rounded-xl border border-dashed border-border-strong bg-card p-4">
              <NewBoard onDone={done} onCancel={() => setCreating(false)} />
            </li>
          )}
          {boards.map((board) => (
            <Tile key={board.id} board={board} now={list.dataUpdatedAt} />
          ))}
        </ul>
      )}
    </div>
  );
}

/** The board name field: Enter creates, Escape (or leaving it empty) cancels. A taken name keeps the text and says
 *  why; archived boards count, since names are unique per workspace (DEC-319 a). */
function NewBoard({ onDone, onCancel, className }: { onDone: (board: Board) => void; onCancel?: () => void; className?: string }) {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const create = $api.useMutation("post", "/v1/boards", {
    onSuccess: (board) => {
      client.setQueryData<Board[]>(boardsKey(false), (list) => list && [board, ...list]);
      void client.invalidateQueries({ queryKey: boardsKey(false) });
      onDone(board);
    },
  });
  const taken = isProblem(create.error) && create.error.status === 409;
  const error = create.isError && (taken ? `You already have a board named “${name.trim()}”. Archived boards count too.` : `Couldn't create the board: ${reasonOf(create.error)}`);
  return (
    <form
      className={cn("flex flex-col gap-2 text-left", className)}
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim()) create.mutate({ body: { name: name.trim() } });
        else onCancel?.();
      }}
    >
      <label htmlFor="new-board" className="text-label font-medium text-muted-foreground">
        Board name
      </label>
      <div className="flex gap-2">
        <input
          id="new-board"
          autoFocus
          value={name}
          maxLength={80}
          placeholder="Q4 gift ideas"
          aria-invalid={!!error}
          aria-describedby={error ? "new-board-error" : undefined}
          onChange={(e) => {
            setName(e.target.value);
            create.reset();
          }}
          onKeyDown={(e) => e.key === "Escape" && onCancel?.()}
          className="h-(--input-h) min-w-0 flex-1 rounded-md border border-input bg-background px-2.5 text-body text-foreground placeholder:text-subtle-foreground aria-invalid:border-negative"
        />
        <Button type="submit" variant="primary" disabled={create.isPending}>
          {create.isPending ? "Creating…" : "Create"}
        </Button>
      </div>
      {error ? (
        <p id="new-board-error" role="alert" className="text-label text-negative">
          {error}
        </p>
      ) : (
        onCancel && <p className="text-label text-subtle-foreground max-sm:hidden">Enter to create · Esc to cancel</p>
      )}
    </form>
  );
}

function Tile({ board, now }: { board: Board; now: number }) {
  return (
    <li>
      <Link
        id={`board-${board.id}`}
        href={`/boards/${board.id}`}
        className="group flex h-full flex-col overflow-hidden rounded-xl border border-border bg-card shadow-card outline-none transition-[translate,border-color] duration-(--duration-fast) ease-out hover:-translate-y-0.5 hover:border-border-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring motion-reduce:hover:translate-y-0"
      >
        <Mosaic board={board} />
        <div className="flex min-w-0 flex-col gap-0.5 border-t border-border-subtle px-3 py-2.5">
          <h2 className="truncate text-body font-medium text-foreground">{board.name}</h2>
          {board.description && <p className="truncate text-label text-muted-foreground">{board.description}</p>}
          <p className="text-label text-subtle-foreground">
            <span className="font-mono tabular-nums">{plural(board.item_count, "product")}</span> ·{" "}
            {board.archived_at ? (
              <>
                Archived <Ago iso={board.archived_at} now={now} source="Your board" />
              </>
            ) : (
              <>
                Updated <Ago iso={board.updated_at} now={now} source="Your board's last change" />
              </>
            )}
          </p>
        </div>
      </Link>
    </li>
  );
}

const COVER = ["", "grid-cols-1", "grid-cols-2", "grid-cols-2 grid-rows-2 [&>:first-child]:row-span-2", "grid-cols-2 grid-rows-2"];

/** The first four cards' images. An empty board, a failed read or a card without an image shows a placeholder;
 *  the mosaic itself never animates (vault Features/Boards, Motion). */
function Mosaic({ board }: { board: Board }) {
  // ponytail: one 4-card read per tile, as many as there are boards; a `cover_images` field on the board list
  // replaces it if the index ever feels slow.
  const items = $api.useQuery("get", "/v1/boards/{board_id}/items", itemsInit(board.id, 4), { enabled: useApiReady() && board.item_count > 0 });
  const cards = items.data?.items ?? [];
  const box = "aspect-[4/3] w-full bg-secondary";
  if (board.item_count === 0)
    return (
      <div className={cn(box, "grid place-items-center text-subtle-foreground")}>
        <span className="flex flex-col items-center gap-1 text-label">
          <Bookmark className="size-5" strokeWidth={1.5} aria-hidden />
          No products yet
        </span>
      </div>
    );
  if (!items.data) return items.isError ? <div className={box} /> : <Skeleton className={cn(box, "rounded-none")} />;
  return (
    <div className={cn(box, "grid gap-px bg-border-subtle", COVER[Math.min(cards.length, 4)])}>
      {cards.map((card) => (
        <Thumb key={card.product_id} url={card.image_url} className="size-full min-h-0 object-cover" />
      ))}
    </div>
  );
}

export function TilesSkeleton() {
  return (
    <div role="status" aria-label="Loading your boards" className={GRID}>
      {[0, 1, 2].map((i) => (
        <div key={i} className="overflow-hidden rounded-xl border border-border bg-card">
          <Skeleton className="aspect-[4/3] w-full rounded-none" />
          <div className="flex flex-col gap-2 px-3 py-3">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
      ))}
    </div>
  );
}
