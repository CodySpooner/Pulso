"use client";

import { useEffect, useRef } from "react";
import * as m from "motion/react-m";

import { duration, ease } from "@/lib/motion";
import { useIsClientNavigation } from "@/lib/navigation";

// Route enter (Motion System pattern 1): opacity 0→1 and y 4→0 at `base`, enter only. The shell never
// animates. Under reduced motion MotionConfig keeps the fade and drops the movement. After a client
// navigation, focus moves to the page h1 (vault Design/Accessibility).
export default function Template({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const isNavigation = useIsClientNavigation();

  useEffect(() => {
    if (isNavigation) ref.current?.querySelector("h1")?.focus({ preventScroll: true });
  }, [isNavigation]);

  return (
    <m.div
      ref={ref}
      initial={isNavigation ? { opacity: 0, y: 4 } : false}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: duration.base, ease: ease.out }}
    >
      {children}
    </m.div>
  );
}
