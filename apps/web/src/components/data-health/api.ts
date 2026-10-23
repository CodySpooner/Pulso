"use client";

import { useAuth } from "@clerk/nextjs";
import { useQueryClient } from "@tanstack/react-query";

import { $api } from "@/lib/api/client";
import { authBypass } from "@/lib/auth";

// DH-1 queries (DEC-068). The nav badge and the page share these keys, so they share one cache entry.

function useSignedIn(): boolean {
  return useAuth().isSignedIn === true;
}

/** A call carries the Clerk session token, so it waits for the session; the E2E bypass has none to wait for. */
const useApiReady: () => boolean = authBypass ? () => true : useSignedIn;

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
    { enabled: useApiReady(), pageParamName: "cursor", initialPageParam: undefined, getNextPageParam: (page) => page.next_cursor ?? undefined },
  );
}

export function useRunDetail(runId: number) {
  return $api.useQuery("get", "/v1/admin/runs/{run_id}", { params: { path: { run_id: runId } } }, { enabled: useApiReady() });
}

/** Refetches every admin query after a toggle or a Run now. */
export function useRefreshAdmin(): () => Promise<void> {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ predicate: (q) => String(q.queryKey[1]).startsWith("/v1/admin/") });
}
