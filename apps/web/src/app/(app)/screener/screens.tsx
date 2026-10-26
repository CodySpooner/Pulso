"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { DropdownMenu } from "radix-ui";
import { Check, ChevronDown, Ellipsis } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Kbd } from "@/components/ui/kbd";
import { useModKey } from "@/components/pulso/mod-key";
import { $api, isProblem } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

import type { Note } from "../boards/parts";
import { menu, menuItem } from "./conditions";
import { clean, decode, DEFAULT, same, type Definition } from "./definition";

export type Saved = components["schemas"]["SavedScreen"];
export type Go = (screen: string | null, definition: Definition | null, push?: boolean) => void;

const why = (error: unknown, name: string) =>
  isProblem(error) ? (error.status === 409 ? `You already have a screen named “${name}”.` : error.detail) : "The Pulso API didn't answer. Check that it is running, then try again.";
const body = ({ filters, sort, order, columns }: Definition) => ({ filters, sort, order, columns });

// Saved screens (vault Features/Product Screener, Saved screens): open, Save (Ctrl+S), Save as, Rename, Duplicate,
// Revert and Delete with Undo. A save replaces the screen's definition with PATCH (imp-525); an undone delete saves it
// again under its name.
export function ScreensBar({ screenId, stored, definition, dirty, go, setNote }: { screenId: string | null; stored: Saved | undefined; definition: Definition; dirty: boolean; go: Go; setNote: (note: Note) => void }) {
  const client = useQueryClient();
  const screens = $api.useQuery("get", "/v1/screens", { params: { query: { limit: 100 } } }, { enabled: useApiReady() });
  const [naming, setNaming] = useState<"create" | "rename" | null>(null);
  const more = useRef<HTMLButtonElement>(null);
  const opener = useRef<Element | null>(null);
  // Focus goes back where it was (Ctrl+S), or to ⋯ when one of its items, gone by then, opened the dialog.
  const ask = (mode: "create" | "rename") => {
    opener.current = document.activeElement?.closest('[role="menu"]') ? more.current : document.activeElement;
    setNaming(mode);
  };
  const done = (screen: Saved) => {
    client.setQueryData($api.queryOptions("get", "/v1/screens/{screen_id}", { params: { path: { screen_id: screen.id } } }).queryKey, screen);
    void client.invalidateQueries({ queryKey: ["get", "/v1/screens"] });
  };
  const create = $api.useMutation("post", "/v1/screens", { onSuccess: done });
  const patch = $api.useMutation("patch", "/v1/screens/{screen_id}", { onSuccess: done });
  const remove = $api.useMutation("delete", "/v1/screens/{screen_id}");
  const failed = (name: string) => (error: unknown) => setNote({ text: why(error, name), tone: "error" });

  const saveAs = (name: string) =>
    create.mutate({ body: { name, ...body(definition) } }, { onSuccess: (s) => (setNaming(null), go(s.id, null, true), setNote({ text: `Saved “${s.name}”`, tone: "done" })) });
  const save = () => {
    if (!stored) return ask("create");
    if (!dirty) return;
    patch.mutate({ params: { path: { screen_id: stored.id } }, body: body(definition) }, { onSuccess: (s) => (go(s.id, null), setNote({ text: `Saved “${s.name}”`, tone: "done" })), onError: failed(stored.name) });
  };
  const rename = (name: string) => stored && patch.mutate({ params: { path: { screen_id: stored.id } }, body: { name } }, { onSuccess: (s) => (setNaming(null), setNote({ text: `Renamed to “${s.name}”`, tone: "done" })) });
  const duplicate = () => {
    if (!stored) return;
    const name = `${stored.name} copy`.slice(0, 80);
    create.mutate({ body: { name, ...body(clean(stored)) } }, { onSuccess: (s) => (go(s.id, null, true), setNote({ text: `Duplicated as “${s.name}”`, tone: "done" })), onError: failed(name) });
  };
  const restore = (gone: Saved) =>
    create.mutate(
      { body: { name: gone.name, ...body(clean(gone)) } },
      {
        onSuccess: (s) => {
          const shown = decode(new URLSearchParams(window.location.search).get("q")) ?? DEFAULT;
          go(s.id, same(shown, clean(s)) ? null : shown);
        },
        onError: failed(gone.name),
      },
    );
  const del = () =>
    stored &&
    remove.mutate(
      { params: { path: { screen_id: stored.id } } },
      {
        onSuccess: (gone) => {
          void client.invalidateQueries({ queryKey: ["get", "/v1/screens"] });
          go(null, definition); // the results stay; only the name goes
          setNote({ text: `Deleted “${gone.name}”`, tone: "done", action: <Button size="sm" variant="ghost" onClick={() => restore(gone)}>Undo</Button> });
        },
        onError: failed(stored.name),
      },
    );

  // Ctrl+S (⌘S) saves, from anywhere on the page (vault UX spec, Keyboard).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== "s" || !(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey || naming) return;
      e.preventDefault();
      save();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const mod = useModKey();
  const name = stored?.name ?? (screenId ? "Saved screen" : "Unsaved screen");
  return (
    <div className="flex flex-wrap items-center gap-2">
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <Button variant="secondary" className="max-w-full min-w-0">
            <span className="text-muted-foreground max-sm:sr-only">Screen</span>
            <span className="truncate font-medium">{name}</span>
            {dirty && (
              <>
                <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-warning" />
                <span className="sr-only">, unsaved changes</span>
              </>
            )}
            <ChevronDown aria-hidden />
          </Button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content align="start" sideOffset={4} className={`${menu} max-h-80 overflow-y-auto`}>
            <DropdownMenu.Label className="px-2 py-1.5 text-micro font-medium text-subtle-foreground">Saved screens</DropdownMenu.Label>
            {screens.data?.items.length === 0 && <p className="px-2 py-1.5 text-label text-muted-foreground">None yet. Save this one with Ctrl+S.</p>}
            {screens.isError && <p className="px-2 py-1.5 text-label text-negative">Couldn&apos;t load your screens.</p>}
            {screens.data?.items.map((s) => (
              <DropdownMenu.Item key={s.id} className={menuItem} onSelect={() => go(s.id, null, true)}>
                <Check aria-hidden className={s.id === screenId ? "size-3.5" : "invisible size-3.5"} />
                <span className="truncate">{s.name}</span>
              </DropdownMenu.Item>
            ))}
            <DropdownMenu.Separator className="my-1 h-px bg-border" />
            <DropdownMenu.Item className={menuItem} onSelect={() => go(null, null, true)}>
              New screen
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      <Button variant={dirty || !stored ? "primary" : "secondary"} aria-keyshortcuts="Control+S" disabled={!!stored && !dirty} onClick={save}>
        {patch.isPending ? "Saving…" : stored && !dirty ? "Saved" : "Save"}
        <Kbd className="max-md:hidden">{mod} S</Kbd>
      </Button>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <Button ref={more} size="icon" variant="ghost" aria-label="More screen actions">
            <Ellipsis aria-hidden />
          </Button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content align="start" sideOffset={4} className={menu}>
            <DropdownMenu.Item className={menuItem} onSelect={() => ask("create")}>
              Save as new…
            </DropdownMenu.Item>
            <DropdownMenu.Item className={menuItem} disabled={!stored} onSelect={() => ask("rename")}>
              Rename…
            </DropdownMenu.Item>
            <DropdownMenu.Item className={menuItem} disabled={!stored} onSelect={duplicate}>
              Duplicate
            </DropdownMenu.Item>
            <DropdownMenu.Item className={menuItem} disabled={!dirty} onSelect={() => go(screenId, null)}>
              Revert changes
            </DropdownMenu.Item>
            <DropdownMenu.Separator className="my-1 h-px bg-border" />
            <DropdownMenu.Item className={`${menuItem} text-negative`} disabled={!stored} onSelect={del}>
              Delete
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      {naming && (
        <NameDialog
          key={naming}
          rename={naming === "rename"}
          initial={naming === "rename" ? (stored?.name ?? "") : ""}
          pending={create.isPending || patch.isPending}
          error={naming === "rename" ? patch.error : create.error}
          onSubmit={naming === "rename" ? rename : saveAs}
          onClose={() => (setNaming(null), create.reset(), patch.reset())}
          opener={opener}
        />
      )}
    </div>
  );
}

function NameDialog({ rename, initial, pending, error, onSubmit, onClose, opener }: { rename: boolean; initial: string; pending: boolean; error: unknown; onSubmit: (name: string) => void; onClose: () => void; opener: React.RefObject<Element | null> }) {
  const [name, setName] = useState(initial);
  const problem = error ? why(error, name.trim()) : null;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        onCloseAutoFocus={(e) => {
          e.preventDefault();
          if (opener.current instanceof HTMLElement) opener.current.focus();
        }}
      >
        <DialogTitle>{rename ? "Rename screen" : "Save screen"}</DialogTitle>
        <DialogDescription>{rename ? "Names are unique in your workspace." : "Its conditions, sort and columns, under a name you can reopen from Screens."}</DialogDescription>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) onSubmit(name.trim());
          }}
        >
          <input
            autoFocus
            aria-label="Screen name"
            value={name}
            maxLength={80}
            placeholder="Early & profitable"
            aria-invalid={!!problem}
            aria-describedby={problem ? "screen-name-error" : undefined}
            onChange={(e) => setName(e.target.value)}
            className="h-(--input-h) rounded-md border border-input bg-background px-2.5 text-body text-foreground placeholder:text-subtle-foreground aria-invalid:border-negative"
          />
          {problem && (
            <p id="screen-name-error" role="alert" className="text-label text-negative">
              {problem}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="ghost">Cancel</Button>
            </DialogClose>
            <Button type="submit" variant="primary" disabled={pending || !name.trim()}>
              {pending ? "Saving…" : rename ? "Rename" : "Save"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
