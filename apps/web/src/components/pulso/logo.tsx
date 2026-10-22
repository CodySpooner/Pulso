"use client";

import * as m from "motion/react-m";
import { useReducedMotion } from "motion/react";

import { ease } from "@/lib/motion";
import { cn } from "@/lib/utils";

// The heartbeat-to-arrow mark on a 32-unit grid (vault Design/Logo & Brand). Stroke uses currentColor.
const BEAT = "M4 18H9L11.5 13.5L14 23L17 10L19.5 17.5L28 9";
const ARROW = "M22.5 9H28V14.5";

export function LogoMark({ className, draw = false }: { className?: string; draw?: boolean }) {
  // Draws once on sign-in and the first-run dashboard only (pattern 18). Under reduced motion the draw
  // is instant; only the timing changes, so server and client markup match.
  const instant = useReducedMotion() ?? false;
  const t = (d: number, delay: number) => (instant ? { duration: 0 } : { duration: d, ease: ease.out, delay });
  return (
    <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden className={cn("shrink-0", className)}>
      <m.path d={BEAT} initial={draw ? { pathLength: 0 } : false} animate={{ pathLength: 1 }} transition={t(0.6, 0.15)} />
      <m.path d={ARROW} initial={draw ? { pathLength: 0, opacity: 0 } : false} animate={{ pathLength: 1, opacity: 1 }} transition={t(0.2, 0.67)} />
    </svg>
  );
}

/** Sidebar lockup: mark 20px in --brand + "pulso" wordmark 17px/600 in --foreground. */
export function Logo({ className, wordmarkClassName }: { className?: string; wordmarkClassName?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <LogoMark className="size-5 text-brand" />
      <span className={cn("text-wordmark font-semibold text-foreground", wordmarkClassName)}>pulso</span>
    </span>
  );
}
