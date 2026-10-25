"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useQueryClient, type InfiniteData, type UseInfiniteQueryResult } from "@tanstack/react-query";

import { $api } from "@/lib/api/client";
import { authBypass } from "@/lib/auth";

// DH-1 queries (DEC-068). The nav badge and the page share these keys, so they share one cache entry.

function useSignedIn(): boolean {
  return useAuth().isSignedIn === true;
}

/** A call carries the Clerk session token, so it waits for the session; the E2E bypass has none to wait for. */
export const useApiReady: () => boolean = authBypass ? () => true : useSignedIn;

// Collection runs at most hourly; a 5-minute refetch keeps the badge and "as of" honest without polling hard.
const live = { refetchInterval: 5 * 60_000 };

export const BACKUP_RUNS = 14;

export function useSources() {
  return $api.useQuery("get", "/v1/admin/sources", {}, { ...live, enabled: useApiReady() });
}

export function useHost() {
  return $api.useQuery("get", "/v1/admin/host", {}, { ...live, enabled: useApiReady() });
}

export function useCoverage(days: number) {
  return $api.useQuery("get", "/v1/admin/coverage", { params: { query: { days } } }, { ...live, enabled: useApiReady() });
}

export function useBackupRuns() {
  return $api.useQuery("get", "/v1/admin/runs", { params: { query: { source: "backup", limit: BACKUP_RUNS } } }, { ...live, enabled: useApiReady() });
}

export function useSourceRuns(key: string) {
  return $api.useInfiniteQuery(
    "get",
    "/v1/admin/runs",
    { params: { query: { source: key, limit: 20 } } },
    // null, not undefined: openapi-react-query sends an undefined page param as cursor=0, which the API rejects.
    { enabled: useApiReady(), pageParamName: "cursor", initialPageParam: null, getNextPageParam: (page) => page.next_cursor },
  );
}

export function useRunDetail(runId: number) {
  return $api.useQuery("get", "/v1/admin/runs/{run_id}", { params: { path: { run_id: runId } } }, { enabled: useApiReady() });
}

/** A Load more page is the API's largest, so older rows take the fewest presses (DEC-166). */
export const MORE_LIMIT = 200;

/** Open-gap pages older than the host's first page, which ended at `cursor` (DEC-166). */
export function useOlderGaps(cursor: string | null) {
  const [asked, setAsked] = useState<string | null>();
  const query = $api.useInfiniteQuery(
    "get",
    "/v1/admin/host",
    { params: { query: { cursor: cursor ?? undefined, limit: MORE_LIMIT } } },
    { enabled: useApiReady() && asked === cursor && cursor != null, pageParamName: "cursor", initialPageParam: cursor, getNextPageParam: (page) => page.next_cursor },
  );
  return loadMore(query, cursor, asked === cursor, () => setAsked(cursor));
}

/** A run's target pages after its first page, which ended at `cursor` (DEC-166). */
export function useMoreTargets(runId: number, cursor: string | null) {
  const [asked, setAsked] = useState<string | null>();
  const query = $api.useInfiniteQuery(
    "get",
    "/v1/admin/runs/{run_id}",
    { params: { path: { run_id: runId }, query: { cursor: cursor ?? undefined, limit: MORE_LIMIT } } },
    { enabled: useApiReady() && asked === cursor && cursor != null, pageParamName: "cursor", initialPageParam: cursor, getNextPageParam: (page) => page.next_cursor },
  );
  return loadMore(query, cursor, asked === cursor, () => setAsked(cursor));
}

/**
 * Load more after a first page the caller already holds (DEC-166): nothing loads until `load()`, then one page
 * per call. The query key carries the cursor that first page ended on, so when a refetch moves it the extra
 * pages drop away (`on` turns false) instead of skipping or repeating rows, and nothing older loads unasked.
 */
function loadMore<P extends { next_cursor: string | null }>(
  query: UseInfiniteQueryResult<InfiniteData<P>, unknown>,
  cursor: string | null,
  on: boolean,
  ask: () => void,
) {
  const pages = on ? (query.data?.pages ?? []) : [];
  return {
    on,
    pages,
    hasMore: pages.length > 0 ? query.hasNextPage : cursor != null,
    pending: on && query.isFetching,
    error: on && query.isError ? query.error : null,
    load: () => {
      if (!on) ask();
      else if (query.isError && !query.isFetchNextPageError) void query.refetch();
      else void query.fetchNextPage();
    },
  };
}

/** Both core calls failed: one page-level line speaks for every panel's failed refetch (imp-132). */
export function useCoreDown(): boolean {
  const sources = useSources();
  const host = useHost();
  return sources.isError && host.isError;
}

/**
 * Neither core call has data and one is still in flight, so the page may yet become "Can't reach the API": a panel
 * keeps its skeleton rather than flash its own load error and Retry first (imp-372, DEC-305).
 */
export function useCoreSettling(): boolean {
  const sources = useSources();
  const host = useHost();
  return !sources.data && !host.data && (sources.isFetching || host.isFetching);
}

/** Refetches every admin query after a toggle or a Run now. */
export function useRefreshAdmin(): () => Promise<void> {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ predicate: (q) => String(q.queryKey[1]).startsWith("/v1/admin/") });
}

/**
 * An import request carrying the file's raw bytes (DEC-068: no multipart). The schema types a binary body as
 * a string, so the serializer hands fetch the File itself.
 */
export function fileUpload(key: string, file: File) {
  return { params: { path: { key } }, body: "", bodySerializer: () => file, headers: { "Content-Type": "application/octet-stream" } };
}
