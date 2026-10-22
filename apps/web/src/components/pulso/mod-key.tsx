"use client";

import { useSyncExternalStore } from "react";

import { Kbd } from "@/components/ui/kbd";

const noop = () => () => {};

/** "⌘" on macOS, "Ctrl" elsewhere. The server renders "Ctrl". */
export function useModKey(): string {
  return useSyncExternalStore(noop, () => (/Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl"), () => "Ctrl");
}

/** The palette shortcut as a key cap: "Ctrl K" or "⌘ K". */
export function ModKey({ className }: { className?: string }) {
  return <Kbd className={className}>{useModKey()} K</Kbd>;
}
