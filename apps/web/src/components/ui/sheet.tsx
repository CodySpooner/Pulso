"use client";

import * as React from "react";
import { Dialog as SheetPrimitive } from "radix-ui";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";

const Sheet = SheetPrimitive.Root;
const SheetTitle = SheetPrimitive.Title;
const SheetDescription = SheetPrimitive.Description;

// Left sheet for mobile and tablet navigation, right sheet for detail drawers, bottom sheet for phone filters:
// slides in at `slow`, scrim fades (vault Design/Motion System pattern 10).
function SheetContent({
  className,
  children,
  side = "left",
  closeLabel = "Close menu",
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Content> & { side?: "left" | "right" | "bottom"; closeLabel?: string }) {
  return (
    <SheetPrimitive.Portal>
      <SheetPrimitive.Overlay className="fixed inset-0 z-50 bg-overlay data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 duration-(--duration-fast)" />
      <SheetPrimitive.Content
        className={cn(
          "fixed z-60 flex flex-col border-border shadow-dialog outline-none",
          "data-[state=open]:animate-in data-[state=open]:duration-(--duration-slow) data-[state=open]:ease-out data-[state=closed]:animate-out data-[state=closed]:duration-(--duration-fast) data-[state=closed]:ease-in",
          side === "left" &&
            "inset-y-0 left-0 w-[min(20rem,85vw)] border-r bg-sidebar data-[state=open]:slide-in-from-left data-[state=closed]:slide-out-to-left",
          side === "right" &&
            "inset-y-0 right-0 w-[min(32rem,100vw)] border-l bg-card data-[state=open]:slide-in-from-right data-[state=closed]:slide-out-to-right",
          side === "bottom" &&
            "inset-x-0 bottom-0 max-h-[85dvh] rounded-t-xl border-t bg-card pb-[env(safe-area-inset-bottom)] data-[state=open]:slide-in-from-bottom data-[state=closed]:slide-out-to-bottom",
          className,
        )}
        {...props}
      >
        {children}
        <SheetPrimitive.Close className="absolute hit-area top-3 right-3 inline-grid size-8 place-items-center rounded-md text-muted-foreground transition-colors duration-(--duration-fast) hover:bg-accent hover:text-foreground">
          <X className="size-4" aria-hidden />
          <span className="sr-only">{closeLabel}</span>
        </SheetPrimitive.Close>
      </SheetPrimitive.Content>
    </SheetPrimitive.Portal>
  );
}

export { Sheet, SheetContent, SheetDescription, SheetTitle };
