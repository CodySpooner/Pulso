"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

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

function seen(key: string): boolean {
  try {
    return sessionStorage.getItem(key) !== null;
  } catch {
    return false; // storage blocked: treat as unseen, the animation is cosmetic
  }
}

/** True the first time per browser session that `key` mounts on a client navigation (Motion System 16, 18). */
export function useOncePerSession(key: string): boolean {
  const isNavigation = useIsClientNavigation();
  const [first] = useState(() => isNavigation && !seen(key));
  useEffect(() => {
    if (!first) return;
    try {
      sessionStorage.setItem(key, "1");
    } catch {
      // storage blocked
    }
  }, [first, key]);
  return first;
}
