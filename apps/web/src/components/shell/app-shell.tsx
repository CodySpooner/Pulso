"use client";

import { createContext, use, useCallback, useEffect, useRef, useState } from "react";

import { BottomBar } from "./bottom-bar";
import { CommandPalette } from "./command-palette";
import { MobileNav } from "./mobile-nav";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

export const SIDEBAR_COOKIE = "pulso_sidebar";

interface Shell {
  openPalette: () => void;
  openNav: () => void;
  collapsed: boolean;
  toggleCollapsed: () => void;
}

const ShellContext = createContext<Shell | null>(null);

export function useShell(): Shell {
  const shell = use(ShellContext);
  if (!shell) throw new Error("useShell must be used inside <AppShell>");
  return shell;
}

function isTyping(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
}

// Inset-panel shell (vault Design/App Shell & Navigation): sidebar on the darkest surface, a 48px top bar
// and the content in a raised panel. Below 1024px the sidebar becomes a sheet; below 768px a bottom tab bar.
export function AppShell({ children, defaultCollapsed }: { children: React.ReactNode; defaultCollapsed: boolean }) {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const paletteReturnFocus = useRef<HTMLElement | null>(null);
  const navReturnFocus = useRef<HTMLElement | null>(null);

  const togglePalette = useCallback((next?: boolean) => {
    setPaletteOpen((open) => {
      const opening = next ?? !open;
      if (opening && !open) paletteReturnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      return opening;
    });
  }, []);

  const toggleCollapsed = useCallback(() => {
    const next = !collapsed;
    // A cookie, not localStorage, so the server renders the remembered width and nothing shifts on load.
    document.cookie = `${SIDEBAR_COOKIE}=${next ? "collapsed" : "expanded"}; path=/; max-age=31536000; samesite=lax`;
    setCollapsed(next);
  }, [collapsed]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      // Ctrl+K / ⌘K works everywhere, including inside inputs (vault Features/Command Palette & Search).
      if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "k") {
        e.preventDefault();
        togglePalette();
        return;
      }
      if (e.key === "[" && !e.ctrlKey && !e.metaKey && !e.altKey && !isTyping(e.target)) {
        e.preventDefault();
        toggleCollapsed();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggleCollapsed, togglePalette]);

  const shell: Shell = {
    openPalette: () => togglePalette(true),
    openNav: () => {
      navReturnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      setNavOpen(true);
    },
    collapsed,
    toggleCollapsed,
  };

  return (
    <ShellContext value={shell}>
      <a
        href="#main"
        className="fixed hit-area top-2 left-2 z-80 -translate-y-16 rounded-md bg-primary px-3 py-2 text-data font-medium text-primary-foreground focus:translate-y-0"
      >
        Skip to content
      </a>
      <div className="flex min-h-dvh lg:h-dvh lg:overflow-hidden">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col bg-background lg:my-2 lg:mr-2 lg:overflow-hidden lg:rounded-xl lg:border lg:border-border">
          <Topbar />
          <main id="main" tabIndex={-1} className="flex-1 outline-none lg:overflow-y-auto">
            <div className="px-4 pt-6 pb-24 md:px-6 md:pt-8 md:pb-12">{children}</div>
          </main>
        </div>
      </div>
      <BottomBar />
      <MobileNav open={navOpen} onOpenChange={setNavOpen} returnFocusRef={navReturnFocus} />
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} returnFocusRef={paletteReturnFocus} />
    </ShellContext>
  );
}
