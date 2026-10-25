"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient, type InfiniteData } from "@tanstack/react-query";
import { TriangleAlert, X } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { Panel, PanelError, StaleLine } from "@/components/data-health/atoms";
import { LoadMore } from "@/components/data-health/load-more";
import { useModKey } from "@/components/pulso/mod-key";
import { isTyping } from "@/components/shell/app-shell";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, isProblem } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { addTag, MAX_TAG_LENGTH } from "./tags";

type Note = components["schemas"]["Note"];
type Notes = InfiniteData<components["schemas"]["NotePage"]>;

const field =
  "w-full min-w-0 rounded-md border border-border bg-secondary px-2.5 text-data text-foreground transition-colors duration-(--duration-fast) placeholder:text-subtle-foreground hover:border-border-strong";
const PENDING = "pending-";

/** A save that failed and was undone: what, why, and the error ID. Spoken once. */
function Failed({ what, error }: { what: string; error: unknown }) {
  const problem = isProblem(error) ? error : null;
  return (
    <p role="alert" className="text-label text-foreground">
      <TriangleAlert className="mr-1 inline size-3.5 align-[-2px] text-negative" aria-hidden />
      <span className="font-medium text-negative">{what}.</span>{" "}
      {problem ? (
        <>
          {problem.detail} <span className="font-mono text-subtle-foreground">Error ID {problem.request_id}</span>
        </>
      ) : (
        "The Pulso API didn't answer."
      )}
    </p>
  );
}

// The page's context rail (vault Features/Product Page): this workspace's tags and notes, the same on every tab.
// Saves are optimistic and roll back on error (DEC-243).
export function ContextRail({ id }: { id: string }) {
  return (
    <aside aria-label="Your tags and notes" className="flex min-w-0 flex-col gap-4">
      <TagsPanel id={id} />
      <NotesPanel id={id} />
    </aside>
  );
}

function TagsPanel({ id }: { id: string }) {
  const init = { params: { path: { product_id: id } } };
  const queryClient = useQueryClient();
  const query = $api.useQuery("get", "/v1/products/{product_id}/tags", init, { enabled: useApiReady() });
  const { queryKey } = $api.queryOptions("get", "/v1/products/{product_id}/tags", init);
  const put = $api.useMutation("put", "/v1/products/{product_id}/tags");
  const [draft, setDraft] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const tags = query.data?.tags ?? [];

  const save = (next: string[]) => {
    const previous = query.data;
    void queryClient.cancelQueries({ queryKey });
    queryClient.setQueryData(queryKey, { tags: next });
    setFailure(null);
    put.mutate(
      { ...init, body: { tags: next } },
      {
        onSuccess: (data) => queryClient.setQueryData(queryKey, data),
        onError: (error) => {
          queryClient.setQueryData(queryKey, previous);
          setFailure(error);
          void queryClient.invalidateQueries({ queryKey });
        },
      },
    );
  };
  const add = () => {
    const result = addTag(tags, draft);
    if ("error" in result) return setMessage(result.error);
    if (result.tags !== tags) save(result.tags);
    setDraft("");
  };
  const remove = (tag: string, index: number) => {
    save(tags.filter((t) => t !== tag));
    // Focus stays in the list: the next chip's remove button, else the previous one, else the input.
    requestAnimationFrame(() => {
      const buttons = list.current?.querySelectorAll("button") ?? [];
      (buttons[Math.min(index, buttons.length - 1)] ?? input.current)?.focus();
    });
  };

  return (
    <Panel id="tags" title="Tags">
      {query.data && query.isError && <StaleLine what="Couldn't refresh tags" error={query.error} asOf={query.dataUpdatedAt} retry={() => void query.refetch()} />}
      {!query.data && query.isError ? (
        <PanelError title="Couldn't load tags" error={query.error} retry={() => void query.refetch()} />
      ) : (
        <div className="flex flex-col gap-2.5 p-4">
          {!query.data ? (
            <div className="flex gap-1.5">
              <Skeleton className="h-6 w-16" />
              <Skeleton className="h-6 w-20" />
            </div>
          ) : tags.length === 0 ? (
            <p className="text-data text-muted-foreground">No tags yet.</p>
          ) : (
            <ul ref={list} aria-label="Tags on this product" className="flex flex-wrap gap-1.5">
              {tags.map((tag, i) => (
                <li key={tag} className="inline-flex h-6 max-w-full items-center gap-0.5 rounded-sm border border-border bg-secondary pr-0.5 pl-2 text-label text-foreground">
                  <span className="truncate">{tag}</span>
                  <button
                    type="button"
                    aria-label={`Remove tag ${tag}`}
                    onClick={() => remove(tag, i)}
                    className="relative hit-area grid size-5 shrink-0 place-items-center rounded-sm text-muted-foreground transition-colors duration-(--duration-fast) hover:bg-accent hover:text-foreground"
                  >
                    <X className="size-3" aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <input
            ref={input}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              setMessage(null);
            }}
            onKeyDown={(e) => {
              if (e.key !== "Enter") return;
              e.preventDefault();
              add();
            }}
            disabled={!query.data}
            maxLength={MAX_TAG_LENGTH}
            enterKeyHint="done"
            placeholder="Add a tag"
            aria-label="Add a tag"
            aria-describedby="tag-hint"
            className={cn(field, "h-(--button-h-md)")}
          />
          <p id="tag-hint" aria-live="polite" className={cn("text-micro", message ? "text-foreground" : "text-subtle-foreground")}>
            {message ?? "Press Enter to add."}
          </p>
          {failure != null && <Failed what="Couldn't save tags. Your change was undone" error={failure} />}
        </div>
      )}
    </Panel>
  );
}

function NotesPanel({ id }: { id: string }) {
  const init = { params: { path: { product_id: id }, query: { limit: 20 } } };
  const queryClient = useQueryClient();
  const notes = $api.useInfiniteQuery(
    "get",
    "/v1/products/{product_id}/notes",
    init,
    // null, not undefined: openapi-react-query sends an undefined page param as cursor=0.
    { enabled: useApiReady(), pageParamName: "cursor", initialPageParam: null, getNextPageParam: (page) => page.next_cursor },
  );
  const { queryKey } = $api.queryOptions("get", "/v1/products/{product_id}/notes", init);
  const post = $api.useMutation("post", "/v1/products/{product_id}/notes");
  const [draft, setDraft] = useState("");
  const [failure, setFailure] = useState<unknown>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const mod = useModKey();
  const items = notes.data?.pages.flatMap((page) => page.items) ?? [];

  // N focuses the note box from anywhere on the page, unless focus is in a field (vault Product Page, Keyboard).
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== "n" || e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return;
      e.preventDefault();
      box.current?.focus();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const edit = (change: (items: Note[]) => Note[]) =>
    queryClient.setQueryData<Notes>(queryKey, (data) => data && { ...data, pages: data.pages.map((page, i) => (i === 0 ? { ...page, items: change(page.items) } : page)) });
  const add = () => {
    const body = draft.trim();
    if (!body) return;
    const temp: Note = { id: `${PENDING}${Date.now()}`, body, created_at: new Date().toISOString() };
    void queryClient.cancelQueries({ queryKey });
    edit((list) => [temp, ...list]);
    setDraft("");
    setFailure(null);
    post.mutate(
      { params: { path: { product_id: id } }, body: { body } },
      {
        onSuccess: (note) => edit((list) => list.map((n) => (n.id === temp.id ? note : n))),
        onError: (error) => {
          edit((list) => list.filter((n) => n.id !== temp.id));
          setDraft((current) => current || body); // the text comes back, so nothing typed is lost
          setFailure(error);
        },
      },
    );
  };

  return (
    <Panel id="notes" title="Notes" note="Only your workspace sees these">
      {notes.data && notes.isError && !notes.isFetchNextPageError && (
        <StaleLine what="Couldn't refresh notes" error={notes.error} asOf={notes.dataUpdatedAt} retry={() => void notes.refetch()} />
      )}
      <form
        className="flex flex-col gap-2 border-b border-border-subtle p-4"
        onSubmit={(e) => {
          e.preventDefault();
          add();
        }}
      >
        <label htmlFor="note-box" className="text-label text-muted-foreground">
          Add a note
        </label>
        <textarea
          id="note-box"
          ref={box}
          rows={3}
          value={draft}
          maxLength={10_000}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key !== "Enter" || !(e.ctrlKey || e.metaKey)) return;
            e.preventDefault();
            add();
          }}
          placeholder="What stands out about this product?"
          className={cn(field, "min-h-20 resize-y py-2 text-body")}
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="flex items-center gap-1 text-micro text-subtle-foreground max-sm:hidden">
            <Kbd>{mod}</Kbd>
            <Kbd>Enter</Kbd> to add · <Kbd>N</Kbd> to write
          </p>
          <Button type="submit" size="sm" variant="primary" disabled={!draft.trim()} className="ml-auto">
            Add note
          </Button>
        </div>
        {failure != null && <Failed what="Couldn't add the note. Your text is back in the box" error={failure} />}
      </form>
      {!notes.data && notes.isError ? (
        <PanelError title="Couldn't load notes" error={notes.error} retry={() => void notes.refetch()} />
      ) : !notes.data ? (
        <div className="flex flex-col gap-2 p-4">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-3.5 w-24" />
        </div>
      ) : items.length === 0 ? (
        <p className="p-4 text-data text-muted-foreground">No notes yet. Write what you notice, and it stays with this product.</p>
      ) : (
        <>
          <ol aria-label="Notes, newest first">
            {items.map((note) => {
              const pending = note.id.startsWith(PENDING);
              return (
                <li key={note.id} className={cn("flex flex-col gap-1 border-b border-border-subtle px-4 py-3 last:border-b-0", pending && "opacity-60")}>
                  <p className="text-body break-words whitespace-pre-wrap text-foreground">{note.body}</p>
                  <p className="text-micro text-subtle-foreground">
                    {pending ? "Saving…" : <time dateTime={note.created_at}>{formatUtc(note.created_at)}</time>}
                  </p>
                </li>
              );
            })}
          </ol>
          {(notes.hasNextPage || notes.data.pages.length > 1) && (
            <div className="border-t border-border-subtle px-4 py-3">
              <LoadMore
                note={`${items.length} notes`}
                label="Show older notes"
                more={notes.hasNextPage}
                pending={notes.isFetchingNextPage}
                error={notes.isFetchNextPageError ? notes.error : null}
                errorTitle="Couldn't load older notes"
                onLoad={() => void notes.fetchNextPage()}
              />
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
