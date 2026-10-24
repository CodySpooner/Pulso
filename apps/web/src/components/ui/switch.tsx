"use client";

import * as React from "react";
import { Switch as SwitchPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

// On/off control (vault Design/Component Inventory). The thumb slides with transform only; the global
// reduced-motion rule makes it instant. The track follows aria-checked: a tooltip trigger wrapping the switch
// replaces its data-state with the tooltip's (imp-134).
function Switch({ className, ...props }: React.ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      className={cn(
        "relative hit-area inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-(--duration-fast) ease-standard",
        "bg-input aria-checked:bg-brand disabled:opacity-50 aria-disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb className="pointer-events-none block size-4 translate-x-0.5 rounded-full bg-primary-foreground shadow-popover transition-transform duration-(--duration-fast) ease-out data-[state=checked]:translate-x-4.5" />
    </SwitchPrimitive.Root>
  );
}

export { Switch };
