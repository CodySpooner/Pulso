"use client";

import { LazyMotion, MotionConfig } from "motion/react";
import { ThemeProvider } from "next-themes";

import { TooltipProvider } from "@/components/ui/tooltip";
import { duration, ease } from "@/lib/motion";

const motionFeatures = () => import("./motion-features").then((m) => m.default);

// Theme: dark by default, light and system available (DEC-024). Motion: `m` components only (`strict`),
// and `reducedMotion="user"` drops transform and layout animations when the OS asks (vault Design/Motion System).
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="dark" themes={["dark", "light"]} enableSystem disableTransitionOnChange>
      <LazyMotion features={motionFeatures} strict>
        <MotionConfig reducedMotion="user" transition={{ duration: duration.base, ease: ease.out }}>
          <TooltipProvider>{children}</TooltipProvider>
        </MotionConfig>
      </LazyMotion>
    </ThemeProvider>
  );
}
