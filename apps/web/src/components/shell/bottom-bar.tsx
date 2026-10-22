"use client";

import Link from "next/link";
import { LayoutGroup } from "motion/react";
import * as m from "motion/react-m";
import { Activity, Compass, Ellipsis, FlaskConical, Search, type LucideIcon } from "lucide-react";

import { spring } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { useShell } from "./app-shell";
import { useActiveHref } from "./nav-list";

const tab = "relative flex flex-1 flex-col items-center justify-center gap-1 text-micro font-medium text-muted-foreground transition-colors duration-(--duration-fast) ease-standard aria-[current=page]:text-foreground";

function TabIcon({ icon: Icon, active }: { icon: LucideIcon; active?: boolean }) {
  return (
    <>
      {active && <m.span layoutId="tab-active" transition={spring.snappy} className="absolute top-0 h-0.5 w-8 rounded-full bg-brand" />}
      <Icon className="size-5" strokeWidth={1.5} aria-hidden />
    </>
  );
}

// Phone tab bar below 768px (vault Design/App Shell & Navigation): Pulse · Discover · Search · Testing · More.
export function BottomBar() {
  const { openPalette, openNav } = useShell();
  const active = useActiveHref();
  const links = [
    { href: "/", label: "Pulse", icon: Activity },
    { href: "/discover", label: "Discover", icon: Compass },
  ];
  const linkTab = (t: (typeof links)[number]) => (
    <Link key={t.href} href={t.href} aria-current={active === t.href ? "page" : undefined} className={tab}>
      <TabIcon icon={t.icon} active={active === t.href} />
      {t.label}
    </Link>
  );
  return (
    <LayoutGroup id="tabbar">
      <nav
        aria-label="Tab bar"
        className="fixed inset-x-0 bottom-0 z-20 flex h-[calc(3.5rem+env(safe-area-inset-bottom))] border-t border-border-subtle bg-background pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        {links.map(linkTab)}
        <button type="button" onClick={openPalette} className={tab}>
          <TabIcon icon={Search} />
          Search
        </button>
        {linkTab({ href: "/testing", label: "Testing", icon: FlaskConical })}
        <button type="button" onClick={openNav} className={cn(tab)}>
          <TabIcon icon={Ellipsis} />
          More
        </button>
      </nav>
    </LayoutGroup>
  );
}
