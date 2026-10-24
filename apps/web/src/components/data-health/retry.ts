"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useIsFetching } from "@tanstack/react-query";

import { useOnline } from "@/components/shell/offline-banner";

// Where focus goes, and what is announced, when the control a keyboard user just pressed leaves the page.

/** Focuses `el`, but only when nothing has focus: the control the user just used left with its step. */
function takeLostFocus(el: HTMLElement | null) {
  if (document.activeElement === document.body) el?.focus();
}

/**
 * Focuses `ref` once `when` holds, but only when nothing has focus (aud-004 C2-02): the control a keyboard
 * user just used (Import, Retry) left with the step it belonged to. Never takes focus from another control.
 */
export function useTakeLostFocus(ref: React.RefObject<HTMLElement | null>, when: unknown = true) {
  useEffect(() => {
    if (when) takeLostFocus(ref.current);
  }, [ref, when]);
}

/** An error's Retry (a PanelError or StaleLine) as its scope sees it. */
interface Surface {
  button: React.RefObject<HTMLButtonElement | null>;
  fail: () => void;
}

interface Scope {
  /** Adds an error while it is shown; returns its removal. */
  show: (surface: Surface) => () => void;
  press: (surface: Surface) => void;
}

/** A panel, or the page's API-down error: where a Retry press is followed to its outcome (imp-135). */
export const RetryScope = createContext<Scope | null>(null);

/**
 * Follows a Retry the owner pressed in this scope until every query settles (imp-135, DEC-217). An error shown
 * then failed: its Retry takes the lost focus and it is announced once. With none, `restored` (the panel's
 * heading) takes the lost focus. Refetches nobody pressed Retry for never reach here, so they stay silent
 * (vault Design/Accessibility: data refetches are not announced).
 */
export function useRetryScope(restored: React.RefObject<HTMLElement | null>): Scope {
  const shown = useRef(new Set<Surface>());
  const pressed = useRef<{ surface: Surface; before: Set<Surface> } | null>(null);
  const [scope] = useState<Scope>(() => ({
    show: (surface) => {
      shown.current.add(surface);
      return () => void shown.current.delete(surface);
    },
    press: (surface) => {
      pressed.current = { surface, before: new Set(shown.current) };
    },
  }));
  // Counts fetches only while a press is followed, so other refetches re-render nothing. Offline, a pressed
  // retry is paused, not settled, until the browser reconnects.
  const online = useOnline();
  const busy = useIsFetching({ predicate: () => pressed.current != null }) > 0 || !online;
  useEffect(() => {
    if (!pressed.current || busy) return;
    const failed = retryOutcome(pressed.current.surface, shown.current, pressed.current.before);
    pressed.current = null;
    if (failed) failed.fail();
    else takeLostFocus(restored.current);
  });
  return scope;
}

/**
 * A Retry button that reports to its scope. `failed` holds from a failure its scope reports until the next press.
 * Offline it is locked like Refresh (imp-157, DEC-220): a press only shows why, and the reconnect refetch is TanStack's.
 */
export function useRetry(retry: () => void) {
  const scope = useContext(RetryScope);
  const online = useOnline();
  const [failed, setFailed] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const [surface] = useState<Surface>(() => ({ button, fail: () => setFailed(true) }));
  // Outside a scope (the run drawer) nothing is followed: the dialog keeps focus (aud-014 A14-04).
  useEffect(() => scope?.show(surface), [scope, surface]);
  useTakeLostFocus(button, failed); // a Retry that failed again comes back focused
  const press = () => {
    if (!online) return;
    setFailed(false); // so a repeat failure is announced again
    scope?.press(surface);
    retry();
  };
  return { button, failed, online, press };
}

/**
 * The error a pressed Retry left on screen once every query settled: the pressed one while it is still shown (a
 * stale line), else one shown since the press (a panel error that left while refreshing), else null: the retry
 * restored its panel. An error shown before the press belongs to another call.
 */
export function retryOutcome<T>(pressed: T, shown: ReadonlySet<T>, before: ReadonlySet<T>): T | null {
  if (shown.has(pressed)) return pressed;
  return [...shown].find((s) => !before.has(s)) ?? null;
}
