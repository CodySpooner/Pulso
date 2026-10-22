"use client";

import { useState } from "react";
import * as m from "motion/react-m";
import { Bell, Sprout, Star, Store, TrendingUp, type LucideIcon } from "lucide-react";

import { EmptyState } from "@/components/pulso/empty-state";
import { duration, ease, stagger } from "@/lib/motion";
import { useIsClientNavigation } from "@/lib/navigation";
import { cn } from "@/lib/utils";

interface Card {
  id: string;
  title: string;
  beta?: boolean;
  icon: LucideIcon;
  empty: string;
  body: string;
  span: string;
}

const cards: Card[] = [
  {
    id: "emerging",
    title: "Top emerging",
    beta: true,
    icon: Sprout,
    empty: "No emerging products yet",
    body: "Trend Score (Beta) ranks products once there are a few days of snapshots. Collectors start in Phase 1.",
    span: "xl:col-span-7",
  },
  {
    id: "movers",
    title: "Biggest movers",
    icon: TrendingUp,
    empty: "Movers need 7 days of history",
    body: "7-day growth, up and down, comes from daily snapshots. Collectors start in Phase 1.",
    span: "xl:col-span-5",
  },
  {
    id: "launches",
    title: "New in tracked stores",
    icon: Store,
    empty: "No tracked stores yet",
    body: "Launches appear after the store crawler runs and you track stores. Collectors start in Phase 1.",
    span: "xl:col-span-6",
  },
  {
    id: "alerts",
    title: "Alerts",
    icon: Bell,
    empty: "No alerts yet",
    body: "Alert rules arrive in Phase 4 and fire once per crossing. Collectors start in Phase 1.",
    span: "xl:col-span-6",
  },
  {
    id: "watchlist",
    title: "Watchlist",
    icon: Star,
    empty: "Your watchlist is empty",
    body: "Products you watch show 30-day sparklines and daily change here. Collectors start in Phase 1.",
    span: "md:col-span-2 xl:col-span-12",
  },
];

const FLAG = "pulso:pulse-stagger";

function shouldStagger(isNavigation: boolean): boolean {
  if (!isNavigation) return false;
  try {
    if (sessionStorage.getItem(FLAG)) return false;
    sessionStorage.setItem(FLAG, "1");
  } catch {
    // Storage blocked: stagger anyway, it is cosmetic.
  }
  return true;
}

// Cards stagger in once per session on a client navigation (Motion System pattern 16: 40ms, first 6,
// opacity + y 8→0). The server-rendered first paint never animates.
export function PulseCards() {
  const isNavigation = useIsClientNavigation();
  const [animate] = useState(() => shouldStagger(isNavigation));

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 md:gap-6 xl:grid-cols-12">
      {cards.map((card, i) => (
        <m.section
          key={card.id}
          aria-labelledby={`pulse-${card.id}`}
          className={cn("flex flex-col rounded-xl border border-border bg-card shadow-card", card.span)}
          initial={animate ? { opacity: 0, y: 8 } : false}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: duration.base, ease: ease.out, delay: Math.min(i, stagger.max) * stagger.step }}
        >
          <header className="flex h-12 items-center gap-2 border-b border-border-subtle px-4 md:px-6">
            <h2 id={`pulse-${card.id}`} className="text-title-3 font-semibold text-foreground">
              {card.title}
            </h2>
            {card.beta && (
              <span className="inline-flex h-5 items-center rounded-sm border border-border px-1.5 text-micro font-medium text-muted-foreground">
                Beta
              </span>
            )}
            <span className="ml-auto text-label text-subtle-foreground">As of —</span>
          </header>
          <EmptyState icon={card.icon} title={card.empty} size="sm" className="flex-1 justify-center">
            {card.body}
          </EmptyState>
        </m.section>
      ))}
    </div>
  );
}
