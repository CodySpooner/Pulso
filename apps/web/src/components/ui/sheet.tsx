"use client";

import * as React from "react";
import { Dialog as SheetPrimitive } from "radix-ui";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";

const Sheet = SheetPrimitive.Root;
const SheetTitle = SheetPrimitive.Title;
const SheetDescription = SheetPrimitive.Description;

// Left sheet for mobile and tablet navigation: slides x 100%→0 at `slow`, scrim fades (vault Design/Motion System).
function SheetContent({ className, children, ...props }: React.ComponentProps<typeof SheetPrimitive.Content>) {
  return (
    <SheetPrimitive.Portal>
      <SheetPrimitive.Overlay className="fixed inset-0 z-50 bg-overlay data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 duration-(--duration-fast)" />
      <SheetPrimitive.Content
        className={cn(
          "fixed inset-y-0 left-0 z-60 flex w-[min(20rem,85vw)] flex-col border-r border-border bg-sidebar shadow-dialog outline-none",
          "data-[state=open]:animate-in data-[state=open]:slide-in-from-left data-[state=open]:duration-(--duration-slow) data-[state=open]:ease-out data-[state=closed]:animate-out data-[state=closed]:slide-out-to-left data-[state=closed]:duration-(--duration-fast) data-[state=closed]:ease-in",
          className,
        )}
        {...props}
      >
        {children}
        <SheetPrimitive.Close className="absolute top-3 right-3 inline-grid size-8 place-items-center rounded-md text-muted-foreground transition-colors duration-(--duration-fast) hover:bg-accent hover:text-foreground">
          <X className="size-4" aria-hidden />
          <span className="sr-only">Close menu</span>
        </SheetPrimitive.Close>
      </SheetPrimitive.Content>
    </SheetPrimitive.Portal>
  );
}

export { Sheet, SheetContent, SheetDescription, SheetTitle };
