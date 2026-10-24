"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider, type QueryClientConfig } from "@tanstack/react-query";
import { LazyMotion, MotionConfig } from "motion/react";
import { ThemeProvider } from "next-themes";

import { TooltipProvider } from "@/components/ui/tooltip";
import { duration, ease } from "@/lib/motion";

const motionFeatures = () => import("./motion-features").then((m) => m.default);

// Theme: dark by default, light and system available (DEC-024). Motion: `m` components only (`strict`),
// and `reducedMotion="user"` drops transform and layout animations when the OS asks (vault Design/Motion System).
// Queries: data changes at most daily, so 5 minutes is fresh enough (vault Platform/API & Typed Client); one
// retry, so a stopped API shows its state within seconds instead of after three backoffs. Mutations never pause
// offline: TanStack resumes a paused one on reconnect, after its dialog may have been cancelled (imp-134, DEC-206).
export const queryClientConfig: QueryClientConfig = { defaultOptions: { queries: { staleTime: 5 * 60_000, retry: 1 }, mutations: { networkMode: "always" } } };

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient(queryClientConfig));
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="dark" themes={["dark", "light"]} enableSystem disableTransitionOnChange>
        <LazyMotion features={motionFeatures} strict>
          <MotionConfig reducedMotion="user" transition={{ duration: duration.base, ease: ease.out }}>
            <TooltipProvider>{children}</TooltipProvider>
          </MotionConfig>
        </LazyMotion>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
