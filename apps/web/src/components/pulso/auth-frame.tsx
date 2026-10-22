import { LogoMark } from "./logo";

// Centered frame for the signed-out pages (sign-in, not authorized): the mark drawn once on a faint grid.
export function AuthFrame({ title, description, children }: { title: string; description?: React.ReactNode; children: React.ReactNode }) {
  return (
    <main className="relative grid min-h-dvh place-items-center overflow-hidden bg-sidebar px-4 py-12">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[linear-gradient(var(--border-subtle)_1px,transparent_1px),linear-gradient(90deg,var(--border-subtle)_1px,transparent_1px)] bg-size-[24px_24px] [mask-image:radial-gradient(circle_at_50%_40%,black,transparent_55%)] opacity-70"
      />
      <div className="relative flex w-full max-w-100 flex-col items-center gap-6">
        <div className="flex flex-col items-center gap-4 text-center">
          <LogoMark draw className="size-12 text-brand" />
          <div className="flex flex-col gap-1.5">
            <h1 className="text-title-1 font-semibold text-foreground">{title}</h1>
            {description && <p className="text-body text-muted-foreground">{description}</p>}
          </div>
        </div>
        {children}
      </div>
    </main>
  );
}
