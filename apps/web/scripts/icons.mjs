// `pnpm --filter web icons`: renders the PWA and Apple icons from src/app/icon.svg with Playwright's
// Chromium (vault Design/Logo & Brand). Re-run after changing the mark; the PNGs are committed.
import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const svg = readFileSync(new URL("../src/app/icon.svg", import.meta.url), "utf8");
// Maskable and Apple icons: full-bleed square (the OS applies its own mask), mark at 60% of the tile.
const fullBleed = svg
  .replace(/<rect width="32" height="32" rx="8"/, '<rect width="32" height="32"')
  .replace(/<rect x="0.5"[^>]*\/>/, "")
  .replace("translate(3.2 3.2) scale(0.8)", "translate(6.4 6.4) scale(0.6)");

const targets = [
  { file: "public/icons/icon-192.png", size: 192, markup: svg },
  { file: "public/icons/icon-512.png", size: 512, markup: svg },
  { file: "public/icons/icon-maskable-512.png", size: 512, markup: fullBleed },
  { file: "src/app/apple-icon.png", size: 180, markup: fullBleed },
];

const browser = await chromium.launch();
for (const { file, size, markup } of targets) {
  const page = await browser.newPage({ viewport: { width: size, height: size } });
  await page.setContent(
    `<style>html,body{margin:0;background:transparent}svg{display:block;width:${size}px;height:${size}px}</style>${markup}`,
  );
  await page.screenshot({ path: fileURLToPath(new URL(`../${file}`, import.meta.url)), omitBackground: true });
  await page.close();
  console.log(`wrote ${file}`);
}
await browser.close();
