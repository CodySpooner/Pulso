import { existsSync } from "node:fs";
import { describe, expect, test } from "vitest";

import manifest from "./manifest";

describe("PWA manifest", () => {
  const m = manifest();

  test("has the installability fields Chrome checks", () => {
    expect(m).toMatchObject({ name: "Pulso", short_name: "Pulso", start_url: "/", display: "standalone" });
    expect(m.theme_color).toMatch(/^#[0-9A-F]{6}$/i);
    expect(m.background_color).toMatch(/^#[0-9A-F]{6}$/i);
  });

  test("ships 192, 512 and a maskable 512 icon that exist on disk", () => {
    const icons = m.icons ?? [];
    expect(icons.map((i) => `${i.sizes} ${i.purpose}`)).toEqual(["192x192 any", "512x512 any", "512x512 maskable"]);
    for (const icon of icons) expect(existsSync(new URL(`../../public${icon.src}`, import.meta.url))).toBe(true);
  });

  test("a long press on the icon offers the phone's daily loop: Daily Pulse, Watchlists, Testing (WF-8)", () => {
    const shortcuts = m.shortcuts ?? [];
    expect(shortcuts.map((s) => [s.name, s.url])).toEqual([
      ["Daily Pulse", "/"],
      ["Watchlists", "/watchlists"],
      ["Testing", "/testing"],
    ]);
    for (const { url, icons = [] } of shortcuts) {
      expect(existsSync(new URL(`./(app)${url === "/" ? "/(pulse)" : url}/page.tsx`, import.meta.url)), url).toBe(true); // a real route
      expect(icons.map((i) => i.sizes)).toEqual(["192x192"]); // Chrome wants a 96px-or-larger icon per shortcut
      for (const icon of icons) expect(existsSync(new URL(`../../public${icon.src}`, import.meta.url))).toBe(true);
    }
  });
});
