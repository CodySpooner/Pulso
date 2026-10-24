import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";

import { cn } from "@/lib/utils";

// Pulso variants (vault Design/Component Inventory): neutral primary; at most one `brand` button per screen.
// A locked (disabled or aria-disabled) button never depresses: its `active:scale-100` outranks every size's press.
const buttonVariants = cva(
  "relative hit-area inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md border border-transparent font-medium whitespace-nowrap select-none transition-[color,background-color,border-color,scale] duration-(--duration-fast) ease-standard active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 disabled:active:scale-100 aria-disabled:pointer-events-none aria-disabled:opacity-50 aria-disabled:active:scale-100 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        primary: "bg-primary text-primary-foreground hover:bg-primary/88",
        brand: "bg-button-brand text-button-brand-foreground hover:bg-button-brand/88",
        secondary: "border-border bg-secondary text-secondary-foreground hover:border-border-strong",
        outline: "border-border-strong bg-transparent text-foreground hover:bg-accent",
        ghost: "bg-transparent text-muted-foreground hover:bg-accent hover:text-foreground",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/88",
        link: "h-auto border-0 px-0.5 text-info underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-(--button-h-sm) px-2.5 text-label",
        md: "h-(--button-h-md) px-3 text-data",
        lg: "h-(--button-h-lg) px-4 text-body",
        icon: "size-8 active:scale-[0.94]",
        "icon-sm": "size-7 active:scale-[0.94]",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "button";
  return <Comp data-slot="button" className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}

export { Button, buttonVariants };
