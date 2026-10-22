"use client";

import { useState, useSyncExternalStore } from "react";

const subscribe = () => () => {};

/**
 * True when the component mounted fresh on the client (a client-side navigation), false when it was
 * server-rendered and hydrated. Enter animations run only on navigations, so the first paint is never
 * hidden behind an animation. useSyncExternalStore returns the server snapshot during hydration, which
 * also holds inside Suspense boundaries that hydrate late.
 */
export function useIsClientNavigation(): boolean {
  const mountedOnClient = useSyncExternalStore(subscribe, () => true, () => false);
  const [isNavigation] = useState(mountedOnClient);
  return isNavigation;
}
