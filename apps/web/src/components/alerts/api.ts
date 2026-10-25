"use client";

import { useQueryClient } from "@tanstack/react-query";

import { useApiReady } from "@/components/data-health/api";
import { $api } from "@/lib/api/client";

// WF-4b queries (DEC-333). The bell, the Alerts nav badge and /alerts share each cache entry.

/** Every 60 s while the tab is visible: TanStack pauses `refetchInterval` in a hidden tab. ponytail: polling, no
 *  websocket; alerts fire at most hourly. */
export function useUnreadCount() {
  return $api.useQuery("get", "/v1/alerts/unread-count", {}, { refetchInterval: 60_000, enabled: useApiReady() });
}

/** The popover's latest 20, refetched each time it opens. */
export function useLatestAlerts() {
  return $api.useQuery("get", "/v1/alerts", { params: { query: { limit: 20 } } }, { enabled: useApiReady(), staleTime: 0 });
}

/** The workspace's rules, for their status (no source yet, skipped for a gap) and the last evaluation. */
export function useAlertRules() {
  return $api.useQuery("get", "/v1/alert-rules", { params: { query: { limit: 100 } } }, { enabled: useApiReady() });
}

/** Read, archive and unarchive. Each refetches the count and the lists; mounted outside anything that closes. */
export function useAlertWrites() {
  const client = useQueryClient();
  const onSuccess = () => client.invalidateQueries({ predicate: (q) => String(q.queryKey[1]).startsWith("/v1/alerts") });
  return {
    read: $api.useMutation("post", "/v1/alerts/read", { onSuccess }),
    archive: $api.useMutation("post", "/v1/alerts/archive", { onSuccess }),
    unarchive: $api.useMutation("post", "/v1/alerts/unarchive", { onSuccess }),
  };
}
