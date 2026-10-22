import { cn } from "@/lib/utils";

function Kbd({ className, ...props }: React.ComponentProps<"kbd">) {
  return (
    <kbd
      className={cn(
        "pointer-events-none inline-flex h-5 min-w-5 shrink-0 items-center whitespace-nowrap justify-center gap-0.5 rounded-sm border border-border bg-secondary px-1.5 text-micro font-medium text-muted-foreground select-none",
        className,
      )}
      {...props}
    />
  );
}

export { Kbd };
