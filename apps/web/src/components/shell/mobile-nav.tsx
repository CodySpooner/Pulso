"use client";

import type { RefObject } from "react";
import { usePathname } from "next/navigation";

import { Logo } from "@/components/pulso/logo";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { settingsItem } from "@/lib/nav";

import { CollectorHostStatus } from "./collector-host-status";
import { NavLink, NavList, useActiveHref } from "./nav-list";

// The full sidebar as a left sheet below 1024px (menu button on tablets, "More" on phones).
export function MobileNav({
  open,
  onOpenChange,
  returnFocusRef,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  returnFocusRef: RefObject<HTMLElement | null>;
}) {
  const activeHref = useActiveHref();
  const pathname = usePathname();
  const close = () => onOpenChange(false);
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        // A link to another page hands focus to its h1 (template.tsx), so don't pull it back to the opener.
        onClickCapture={(e) => {
          const link = (e.target as HTMLElement).closest("a");
          if (link && link.pathname !== pathname) returnFocusRef.current = null;
        }}
        // Radix only restores focus to a Dialog.Trigger; the sheet opens from the menu button or "More".
        onCloseAutoFocus={(e) => {
          e.preventDefault();
          returnFocusRef.current?.focus();
        }}
      >
        <SheetTitle className="flex h-14 shrink-0 items-center px-4">
          <Logo />
        </SheetTitle>
        <SheetDescription className="sr-only">Every Pulso page. Pages for later phases show what they will do.</SheetDescription>
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          <NavList variant="sheet" onNavigate={close} />
        </div>
        <div className="flex flex-col gap-0.5 border-t border-sidebar-border px-2 pt-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
          <CollectorHostStatus rail={false} variant="sheet" onNavigate={close} />
          <NavLink item={settingsItem} active={activeHref === settingsItem.href} rail={false} variant="sheet" onNavigate={close} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
