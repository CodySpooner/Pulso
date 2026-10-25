"use client";

import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Check, ChevronRight, PenLine, Search, X } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { PanelError, StaleLine } from "@/components/data-health/atoms";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { $api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { Failed } from "./context-rail";
import { checkKeyword, decide, MAX_KEYWORD_LENGTH, tracking, type Decision, type Keyword, type TrendsBudget } from "./keywords-model";

type KeywordList = components["schemas"]["KeywordList"];

const field =
  "h-(--button-h-md) w-full min-w-0 rounded-md border border-border bg-secondary px-2.5 text-data text-foreground transition-colors duration-(--duration-fast) placeholder:text-subtle-foreground hover:border-border-strong";
const shortDay = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

/** Where a keyword's relevance comes from, for its hover (every number names its source and as of). */
const provenance = (k: Keyword) =>
  k.relevance === null
    ? `Added by you · no listing title holds it${k.decided_at ? ` · confirmed ${formatUtc(k.decided_at)}` : ""}`
    : `Relevance ${k.relevance.toFixed(2)} from listing titles as of ${formatUtc(k.as_of)}`;

// KW-1 (vault Features/Product Page - Trends, DEC-281): the owner confirms the search keywords for this product.
// Candidates are phrases from its listing titles, never a link until confirmed (DEC-245 d). One click confirms or
// rejects; saves are optimistic and roll back on error, as the context rail's tags do. No Trends fetch happens here:
// KW-2 (DEC-292) shows what confirming costs and whether each confirmed keyword is in the weekly Trends set.
export function KeywordsSection({ id }: { id: string }) {
  const init = { params: { path: { product_id: id } } };
  const queryClient = useQueryClient();
  const query = $api.useQuery("get", "/v1/products/{product_id}/keywords", init, { enabled: useApiReady() });
  const { queryKey } = $api.queryOptions("get", "/v1/products/{product_id}/keywords", init);
  const post = $api.useMutation("post", "/v1/products/{product_id}/keywords");
  const [draft, setDraft] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const latest = useRef(0);
  const section = useRef<HTMLElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const all = query.data?.keywords ?? [];
  const confirmed = all.filter((k) => k.status === "confirmed");
  const candidates = all.filter((k) => k.status === "candidate");
  const rejected = all.filter((k) => k.status === "rejected");

  const save = (keyword: string, status: Decision) => {
    // Build on the cache, not this render: a second quick click must not undo the first (imp-278).
    const previous = queryClient.getQueryData<KeywordList>(queryKey);
    const n = ++latest.current;
    void queryClient.cancelQueries({ queryKey });
    queryClient.setQueryData<KeywordList>(queryKey, (old) => old && { ...old, keywords: decide(old.keywords, keyword, status, new Date().toISOString()) });
    setFailure(null);
    // mutateAsync settles every call (mutate's own callbacks fire for the latest call only). Only the newest answer
    // replaces the list, so an older one never drops a newer optimistic decision.
    post.mutateAsync({ ...init, body: { keyword, status } }).then(
      (data) => {
        if (n === latest.current) queryClient.setQueryData(queryKey, data);
      },
      (error: unknown) => {
        if (n === latest.current) queryClient.setQueryData(queryKey, previous);
        setFailure(error);
        void queryClient.invalidateQueries({ queryKey });
      },
    );
  };
  /** Decide, then keep focus in the same list: the row that moved up into this place, the one before, else the field. */
  const decideAt = (list: string, index: number, keyword: string, status: Decision) => {
    save(keyword, status);
    requestAnimationFrame(() => {
      const rows = section.current?.querySelectorAll<HTMLElement>(`[data-list="${list}"] > li`) ?? [];
      const row = rows[Math.min(index, rows.length - 1)];
      (row?.querySelector<HTMLElement>("button") ?? input.current)?.focus();
    });
  };
  const add = () => {
    const problem = checkKeyword(all, draft);
    if (problem) return setMessage(problem);
    save(draft, "confirmed");
    setDraft("");
    setMessage(null);
  };

  return (
    <section ref={section} aria-labelledby="keywords-title" className="flex flex-col gap-4 border-t border-border-subtle p-4">
      <header className="flex flex-col gap-1">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 id="keywords-title" className="text-title-3 font-semibold text-foreground">
            Search keywords
          </h2>
          <span className="text-label text-subtle-foreground">Only your workspace sees these</span>
        </div>
        <p className="max-w-[72ch] text-data text-muted-foreground">
          The words a shopper types to find this product. Suggestions come from its listing titles and count only once you confirm them.
        </p>
      </header>

      {query.data && query.isError && <StaleLine boxed what="Couldn't refresh keywords" error={query.error} asOf={query.dataUpdatedAt} retry={() => void query.refetch()} />}
      {!query.data && query.isError ? (
        <PanelError title="Couldn't load keywords" error={query.error} retry={() => void query.refetch()} className="rounded-lg border border-border-subtle" />
      ) : !query.data ? (
        <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading keywords">
          <div className="flex gap-1.5">
            <Skeleton className="h-6 w-28" />
            <Skeleton className="h-6 w-20" />
          </div>
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-2">
            <h3 className="flex flex-wrap items-center gap-x-1.5 text-label font-medium text-foreground">
              Confirmed <span className="font-normal text-subtle-foreground">· {confirmed.length}</span>{" "}
              {/* The chips' marker, explained once: a filled dot is in the weekly Trends set. */}
              {confirmed.length > 0 && (
                <span className="inline-flex items-center gap-1 font-normal text-subtle-foreground">
                  · <Marker tracked /> {confirmed.filter((k) => k.tracked).length} tracked
                </span>
              )}
            </h3>
            {confirmed.length === 0 ? (
              <p className="text-data text-muted-foreground">{candidates.length > 0 ? "None yet. Confirm a suggestion below, or add your own." : "None yet."}</p>
            ) : (
              <ul data-list="confirmed" aria-label="Confirmed keywords" className="flex flex-wrap gap-1.5">
                {confirmed.map((k, i) => {
                  const track = tracking(k, query.data.trends);
                  return (
                  <li key={k.keyword} title={track ? `${track.reason}\n${provenance(k)}` : provenance(k)} className="inline-flex h-6 max-w-full items-center gap-1 rounded-sm border border-border-strong bg-secondary pr-0.5 pl-2 text-label text-foreground">
                    {track && <Marker tracked={k.tracked === true} label={track.label} />}
                    {/* Only the minority carries a mark: a keyword typed in rather than taken from a title. */}
                    {k.source === "manual" && (
                      <>
                        <PenLine className="size-3 shrink-0 text-subtle-foreground" aria-hidden />
                        <span className="sr-only">Added by you: </span>
                      </>
                    )}
                    <span className="truncate">{k.keyword}</span>
                    {/* Rejecting keeps the decision on record; nothing is deleted (DEC-281). */}
                    <button
                      type="button"
                      aria-label={`Reject ${k.keyword}`}
                      onClick={() => decideAt("confirmed", i, k.keyword, "rejected")}
                      className="relative hit-area grid size-5 shrink-0 place-items-center rounded-sm text-muted-foreground transition-colors duration-(--duration-fast) hover:bg-accent hover:text-foreground"
                    >
                      <X className="size-3" aria-hidden />
                    </button>
                  </li>
                  );
                })}
              </ul>
            )}
            <form
              className="flex max-w-md gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                add();
              }}
            >
              <input
                ref={input}
                value={draft}
                onChange={(e) => {
                  setDraft(e.target.value);
                  setMessage(null);
                }}
                maxLength={MAX_KEYWORD_LENGTH}
                enterKeyHint="done"
                placeholder="Add a keyword"
                aria-label="Add a keyword"
                aria-describedby="keyword-hint keyword-cost"
                className={field}
              />
              <Button type="submit" size="md" variant="secondary">
                Add
              </Button>
            </form>
            <div className="flex flex-col gap-1">
              <p id="keyword-hint" aria-live="polite" className={cn("text-micro", message ? "text-foreground" : "text-subtle-foreground")}>
                {message ?? "Press Enter to add. A keyword you add is confirmed."}
              </p>
              <TrendsCost budget={query.data.trends} />
            </div>
            {failure != null && <Failed what="Couldn't save the keyword. Your change was undone" error={failure} />}
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <h3 className="text-label font-medium text-foreground">Suggested from listing titles</h3>
              {all[0] && (
                <span className="text-micro text-subtle-foreground">
                  Relevance: how many titles use the phrase and its words · titles as of <time dateTime={all[0].as_of}>{formatUtc(all[0].as_of)}</time>
                </span>
              )}
            </div>
            {candidates.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border px-3 py-3 text-data text-muted-foreground">
                {all.length === 0 ? "No usable phrase in this product's titles yet. Add the words a shopper would search." : "No suggestions left. Add any keyword the titles miss."}
              </p>
            ) : (
              <ul data-list="candidates" aria-label="Suggested keywords" className="flex flex-col">
                {candidates.map((k, i) => (
                  <li key={k.keyword} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border-subtle py-2 last:border-b-0">
                    <span className="min-w-0 flex-1 basis-40 text-data break-words text-foreground">{k.keyword}</span>
                    <Relevance k={k} />
                    <span className="ml-auto flex gap-1.5">
                      <Button size="sm" variant="secondary" aria-label={`Confirm ${k.keyword}`} aria-describedby="keyword-cost" onClick={() => decideAt("candidates", i, k.keyword, "confirmed")}>
                        <Check aria-hidden className="size-3.5" />
                        Confirm
                      </Button>
                      <Button size="sm" variant="ghost" aria-label={`Reject ${k.keyword}`} onClick={() => decideAt("candidates", i, k.keyword, "rejected")}>
                        <X aria-hidden className="size-3.5" />
                        Reject
                      </Button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {rejected.length > 0 && (
            <details className="group rounded-lg border border-border-subtle">
              <summary className="flex min-h-11 cursor-pointer list-none items-center gap-1.5 rounded-lg px-3 text-label font-medium text-muted-foreground hover:text-foreground">
                <ChevronRight className="size-4 group-open:rotate-90" aria-hidden />
                Rejected ({rejected.length})
              </summary>
              <ul data-list="rejected" aria-label="Rejected keywords" className="flex flex-col px-3 pb-1">
                {rejected.map((k, i) => (
                  <li key={k.keyword} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-t border-border-subtle py-2">
                    <span className="min-w-0 flex-1 basis-40 text-data break-words text-muted-foreground">{k.keyword}</span>
                    <Relevance k={k} />
                    <Button size="sm" variant="ghost" className="ml-auto" aria-label={`Confirm ${k.keyword} instead`} aria-describedby="keyword-cost" onClick={() => decideAt("rejected", i, k.keyword, "confirmed")}>
                      <Check aria-hidden className="size-3.5" />
                      Confirm instead
                    </Button>
                  </li>
                ))}
              </ul>
            </details>
          )}

          {/* The no-source state for per-keyword interest: one line, since the Search interest pane above says it too. */}
          <p className="flex items-start gap-1.5 text-micro text-subtle-foreground">
            <Search className="mt-px size-3 shrink-0" aria-hidden />
            <span className="font-medium text-muted-foreground">Search interest per keyword · No source yet.</span>
          </p>
        </>
      )}
    </section>
  );
}

/** In the weekly Trends set or not: a filled or a hollow neutral dot. Shape carries it, and tracked is the normal state,
 *  so neither takes a status colour. */
function Marker({ tracked, label }: { tracked: boolean; label?: string }) {
  return (
    <span
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn("size-2 shrink-0 rounded-full border border-muted-foreground", tracked && "bg-muted-foreground")}
    />
  );
}

/** What confirming costs, before the click: one SerpApi search a week per tracked keyword, from the count the Monday
 *  Trends job plans with (KW-2, DEC-292). Off, nothing is fetched for confirmed keywords, so no slots show. */
function TrendsCost({ budget }: { budget: TrendsBudget }) {
  const { weekly_used: used, weekly_cap: cap } = budget;
  const line = "flex items-start gap-2 text-micro text-muted-foreground";
  if (!budget.enabled)
    return (
      <p id="keyword-cost" className={line} title="TRENDS_CONFIRMED_KEYWORDS is off: the Monday Google Trends fetch takes only the approved seed keywords.">
        <span>
          <span className="font-medium text-foreground">Trends tracking is off.</span> Confirmed keywords are saved, but nothing is fetched for them.
        </span>
      </p>
    );
  const full = used >= cap;
  const slots = <span className="font-medium text-foreground">{`${used} of ${cap} weekly slots used.`}</span>;
  return (
    <p
      id="keyword-cost"
      className={line}
      title={`Counted ${formatUtc(budget.as_of)} from the approved seed keywords and every workspace's confirmed keywords. The fetch runs Mondays at 05:00 UTC, within ${budget.monthly_limit} SerpApi searches a month.`}
    >
      <span aria-hidden className="mt-1.5 h-1 w-14 shrink-0 overflow-hidden rounded-full bg-secondary">
        <span className={cn("block h-full rounded-full", full ? "bg-warning" : "bg-muted-foreground")} style={{ width: `${cap ? Math.min(used / cap, 1) * 100 : 100}%` }} />
      </span>
      {full ? (
        <span>{slots} A keyword you confirm now is saved but not tracked until a slot frees.</span>
      ) : (
        <span>
          Each tracked keyword is 1 SerpApi search a week, about 4–5 of the {budget.monthly_limit} a month. {slots}
        </span>
      )}
    </p>
  );
}

/** The relevance as a short bar and a number; a typed-in keyword no title holds reads "typed in", never 0. */
function Relevance({ k }: { k: Keyword }) {
  if (k.relevance === null)
    return (
      <span className="text-label text-subtle-foreground" title={provenance(k)}>
        Typed in{k.decided_at && ` · ${shortDay.format(new Date(k.decided_at))}`}
      </span>
    );
  return (
    <span className="flex items-center gap-2" title={provenance(k)}>
      <span aria-hidden className="hidden h-1 w-14 overflow-hidden rounded-full bg-secondary sm:block">
        <span className="block h-full rounded-full bg-muted-foreground" style={{ width: `${k.relevance * 100}%` }} />
      </span>
      <span className="font-mono text-data text-foreground" data-numeric>
        <span className="sr-only">Relevance </span>
        {k.relevance.toFixed(2)}
      </span>
    </span>
  );
}
