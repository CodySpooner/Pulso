"use client";

import { usePathname, useRouter } from "next/navigation";
import { useState, type RefObject } from "react";
import { Command } from "cmdk";
import { AnimatePresence, LayoutGroup } from "motion/react";
import * as m from "motion/react-m";
import { Dialog } from "radix-ui";
import { useClerk } from "@clerk/nextjs";
import { CornerDownLeft, LogOut, Monitor, Moon, PanelLeft, Search, Sun, type LucideIcon } from "lucide-react";
import { useTheme } from "next-themes";

import { Kbd } from "@/components/ui/kbd";
import { authBypass } from "@/lib/auth";
import { duration, ease, spring } from "@/lib/motion";
import { allNavItems, isBuilt } from "@/lib/nav";

import { useShell } from "./app-shell";

interface Run {
  close: () => void;
}

const item =
  "relative flex h-10 cursor-pointer items-center gap-3 rounded-lg px-2 text-body text-muted-foreground outline-none select-none data-[selected=true]:text-foreground data-[disabled=true]:cursor-default data-[disabled=true]:text-subtle-foreground";
const group =
  "px-1.5 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1.5 [&_[cmdk-group-heading]]:text-label [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-subtle-foreground";

function Row({
  value,
  selected,
  icon: Icon,
  label,
  hint,
  keywords,
  disabled,
  onSelect,
}: {
  value: string;
  selected: string;
  icon: LucideIcon;
  label: string;
  hint?: React.ReactNode;
  keywords?: string[];
  disabled?: boolean;
  onSelect?: () => void;
}) {
  return (
    <Command.Item value={value} keywords={keywords} disabled={disabled} onSelect={onSelect} className={item}>
      {selected === value && (
        // The highlight is one shared element that slides between rows (pattern 8), snaps under reduced motion.
        <m.span layoutId="palette-highlight" transition={spring.snappy} className="absolute inset-0 rounded-lg bg-accent" />
      )}
      <Icon className="relative size-4 shrink-0" strokeWidth={1.5} aria-hidden />
      <span className="relative truncate">{label}</span>
      {hint && <span className="relative ml-auto shrink-0 text-label text-subtle-foreground">{hint}</span>}
    </Command.Item>
  );
}

function SignOutRow({ selected, run }: { selected: string; run: Run }) {
  const { signOut } = useClerk();
  return (
    <Row
      value="sign-out"
      selected={selected}
      icon={LogOut}
      label="Sign out"
      onSelect={() => {
        run.close();
        void signOut({ redirectUrl: "/sign-in" });
      }}
    />
  );
}

// Ctrl+K stub (vault Features/Command Palette & Search): navigation to every §10 route, theme, sidebar and
// sign-out. Search arrives in Phase 2. Radix Dialog traps focus, closes on Esc and returns focus to
// whatever had it before opening; cmdk provides listbox semantics and arrow/Enter handling.
export function CommandPalette({
  open,
  onOpenChange,
  returnFocusRef,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Element focused before the palette opened (set by the shell); focus goes back there on close. */
  returnFocusRef: RefObject<HTMLElement | null>;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { resolvedTheme, setTheme } = useTheme();
  const { collapsed, toggleCollapsed } = useShell();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState("");

  const setOpen = (next: boolean) => {
    if (!next) {
      setQuery("");
      setSelected("");
    }
    onOpenChange(next);
  };
  const run: Run = { close: () => setOpen(false) };
  const go = (href: string) => {
    // A new route moves focus to its h1 (template.tsx), so don't pull it back to the old trigger.
    if (href !== pathname) returnFocusRef.current = null;
    run.close();
    router.push(href);
  };
  const nextTheme = resolvedTheme === "light" ? "dark" : "light";

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <AnimatePresence>
        {open && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild forceMount>
              <m.div
                className="fixed inset-0 z-50 bg-overlay"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1, transition: { duration: duration.fast, ease: ease.out } }}
                exit={{ opacity: 0, transition: { duration: duration.fast, ease: ease.in } }}
              />
            </Dialog.Overlay>
            <Dialog.Content
              asChild
              forceMount
              aria-describedby={undefined}
              onCloseAutoFocus={(e) => {
                // Radix only restores focus to a Dialog.Trigger; this palette also opens from Ctrl+K.
                e.preventDefault();
                returnFocusRef.current?.focus();
              }}
              onEscapeKeyDown={(e) => {
                // First Esc clears the query, the second closes.
                if (query) {
                  e.preventDefault();
                  setQuery("");
                }
              }}
            >
              <m.div
                className="fixed inset-x-4 top-[12vh] z-60 mx-auto max-w-160 origin-top overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-dialog outline-none max-md:inset-x-0 max-md:top-0 max-md:h-dvh max-md:max-w-none max-md:rounded-none"
                initial={{ opacity: 0, scale: 0.98, y: -8 }}
                animate={{ opacity: 1, scale: 1, y: 0, transition: { duration: duration.base, ease: ease.out } }}
                exit={{ opacity: 0, transition: { duration: duration.fast, ease: ease.in } }}
              >
                <Dialog.Title className="sr-only">Command palette</Dialog.Title>
                <Command label="Command palette" value={selected} onValueChange={setSelected} loop className="flex h-full flex-col">
                  <div className="flex h-13 items-center gap-2 border-b border-border-subtle px-4 text-subtle-foreground">
                    <Search className="size-4 shrink-0" strokeWidth={1.5} aria-hidden />
                    <Command.Input
                      value={query}
                      onValueChange={setQuery}
                      placeholder="Type a command or page…"
                      className="h-full min-w-0 flex-1 bg-transparent text-title-3 text-foreground outline-none placeholder:text-subtle-foreground max-md:text-base"
                    />
                    <Kbd className="max-md:hidden">Esc</Kbd>
                    <Dialog.Close className="text-data font-medium text-muted-foreground md:hidden">Close</Dialog.Close>
                  </div>
                  <LayoutGroup id="palette">
                    <Command.List className="max-h-105 flex-1 scroll-py-1.5 overflow-y-auto overscroll-contain py-1.5 max-md:max-h-none">
                      <Command.Empty className="px-6 py-8 text-center text-data text-muted-foreground">
                        No command matches “{query}”. Product, store and supplier search arrives in Phase 2.
                      </Command.Empty>

                      <Command.Group heading="Search" className={group}>
                        <Row value="search-stub" selected={selected} icon={Search} label="Search products, stores, suppliers" hint="Phase 2" keywords={["find"]} disabled />
                      </Command.Group>

                      <Command.Group heading="Go to" className={group}>
                        {allNavItems.map((nav) => (
                          <Row
                            key={nav.href}
                            value={`go ${nav.href}`}
                            selected={selected}
                            icon={nav.icon}
                            label={nav.label}
                            keywords={[nav.label, nav.href]}
                            hint={isBuilt(nav) ? <CornerDownLeft className="size-3.5" aria-hidden /> : `Phase ${nav.phase}`}
                            onSelect={() => go(nav.href)}
                          />
                        ))}
                      </Command.Group>

                      <Command.Group heading="Preferences" className={group}>
                        <Row
                          value="theme-toggle"
                          selected={selected}
                          icon={nextTheme === "light" ? Sun : Moon}
                          label={`Switch to ${nextTheme} theme`}
                          keywords={["theme", "dark", "light", "appearance"]}
                          onSelect={() => setTheme(nextTheme)}
                        />
                        <Row value="theme-system" selected={selected} icon={Monitor} label="Use system theme" keywords={["theme", "appearance"]} onSelect={() => setTheme("system")} />
                        <Row
                          value="sidebar-toggle"
                          selected={selected}
                          icon={PanelLeft}
                          label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                          keywords={["sidebar", "rail"]}
                          hint={<Kbd>[</Kbd>}
                          onSelect={() => {
                            run.close();
                            toggleCollapsed();
                          }}
                        />
                      </Command.Group>

                      {!authBypass && (
                        <Command.Group heading="Account" className={group}>
                          <SignOutRow selected={selected} run={run} />
                        </Command.Group>
                      )}
                    </Command.List>
                  </LayoutGroup>
                  <div className="flex h-10 shrink-0 items-center gap-4 border-t border-border-subtle px-4 text-label text-subtle-foreground max-md:hidden">
                    <span className="inline-flex items-center gap-1.5">
                      <Kbd>↑</Kbd>
                      <Kbd>↓</Kbd> Navigate
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <Kbd>↵</Kbd> Open
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <Kbd>Esc</Kbd> Close
                    </span>
                  </div>
                </Command>
              </m.div>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
