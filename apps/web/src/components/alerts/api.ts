"use client";

import { useQueryClient } from "@tanstack/react-query";

import { useApiReady } from "@/components/data-health/api";
import { $api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type RulePage = components["schemas"]["RulePage"];
type RulePatch = components["schemas"]["RulePatch"];

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

// ponytail: the newest 100 rules, one page; the Rules tab says so if there are more. Load more when a workspace has that many.
const RULES = { params: { query: { limit: 100 } } };

/** The workspace's rules, for their status (no source yet, skipped for a gap) and the last evaluation. */
export function useAlertRules() {
  return $api.useQuery("get", "/v1/alert-rules", RULES, { enabled: useApiReady() });
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

/** WF-4c (DEC-339): create, edit and delete rules. An edit (enabled, mute) shows at once and rolls back on an error;
 *  every write then refetches the list, so the server's rule wins. */
export function useRuleWrites() {
  const client = useQueryClient();
  const { queryKey } = $api.queryOptions("get", "/v1/alert-rules", RULES);
  const onSettled = () => client.invalidateQueries({ queryKey: ["get", "/v1/alert-rules"] });
  return {
    create: $api.useMutation("post", "/v1/alert-rules", { onSettled }),
    remove: $api.useMutation("delete", "/v1/alert-rules/{rule_id}", { onSettled }),
    patch: $api.useMutation("patch", "/v1/alert-rules/{rule_id}", {
      onMutate: async ({ params, body }: { params: { path: { rule_id: string } }; body: RulePatch }) => {
        await client.cancelQueries({ queryKey });
        const before = client.getQueryData<RulePage>(queryKey);
        const change = Object.fromEntries(Object.entries(body).filter(([name]) => name !== "name" && name !== "params"));
        client.setQueryData<RulePage>(queryKey, (page) => page && { ...page, items: page.items.map((r) => (r.id === params.path.rule_id ? { ...r, ...change } : r)) });
        return before;
      },
      onError: (_error, _vars, before) => void (before && client.setQueryData(queryKey, before)),
      onSettled,
    }),
  };
}
