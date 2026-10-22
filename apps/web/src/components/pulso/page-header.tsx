import { cn } from "@/lib/utils";

// Page title (the route's only h1, which receives focus on navigation), one muted line, actions right.
export function PageHeader({
  title,
  description,
  meta,
  actions,
  className,
}: {
  title: string;
  description?: React.ReactNode;
  meta?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="flex min-w-0 flex-col gap-1">
        <h1 tabIndex={-1} className="text-title-1 font-semibold text-foreground outline-none">
          {title}
        </h1>
        {description && <p className="max-w-[68ch] text-body text-muted-foreground">{description}</p>}
        {meta && <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-label font-normal text-subtle-foreground">{meta}</div>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
