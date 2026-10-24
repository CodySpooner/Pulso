"use client";

import { useSyncExternalStore } from "react";
import { onlineManager, useQueryClient } from "@tanstack/react-query";
import { WifiOff } from "lucide-react";

import { formatUtc } from "@/lib/format";

/** Why a control that sends a request is unavailable while the browser is offline (imp-134). */
export const OFFLINE_HINT = "You're offline. Reconnect to use this.";

/** TanStack's own online state (the window's online/offline events), so the UI agrees with its paused queries. */
export function useOnline(): boolean {
  return useSyncExternalStore(onlineManager.subscribe, () => onlineManager.isOnline(), () => true);
}

// Offline (browser), vault Design/UI States: one top banner. Queries pause and refetch on reconnect; mutations
// never wait (networkMode "always"), and each control that sends one says why it is unavailable. Below lg it
// sticks under the top bar, so a phone scrolled down to a control still sees it; the tint is layered over the
// page background so nothing shows through it there.
export function OfflineBanner() {
  const online = useOnline();
  const queryClient = useQueryClient();
  // The oldest data on screen: nothing lands while offline, so the active queries' last fetch is what's shown.
  const fetched = online ? [] : queryClient.getQueryCache().findAll({ type: "active" }).map((q) => q.state.dataUpdatedAt).filter(Boolean);
  const asOf = fetched.length > 0 ? new Date(Math.min(...fetched)).toISOString() : null;
  return (
    <p role="status" className="border-b border-warning/30 bg-background bg-[linear-gradient(var(--warning-muted),var(--warning-muted))] px-4 py-2.5 text-data text-foreground empty:hidden max-lg:sticky max-lg:top-14 max-lg:z-20 md:px-6">
      {!online && (
        <>
          <WifiOff className="mr-1.5 inline size-3.5 align-[-2px] text-warning" aria-hidden />
          <span className="font-medium">You&apos;re offline.</span>{" "}
          {asOf && (
            <>
              Showing data as of{" "}
              <time dateTime={asOf} className="whitespace-nowrap">
                {formatUtc(asOf)}
              </time>
              .{" "}
            </>
          )}
          Refresh and actions are off until you reconnect.
        </>
      )}
    </p>
  );
}
