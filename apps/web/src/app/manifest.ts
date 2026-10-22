import type { MetadataRoute } from "next";

// PWA manifest, no service worker (DEC-027, vault Design/Logo & Brand). Colours are the gray-950 canvas;
// a manifest can't read CSS variables. Icons are generated from src/app/icon.svg by `pnpm --filter web icons`.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Pulso",
    short_name: "Pulso",
    description: "The pulse of what's selling: product research and calibrated trend forecasts.",
    id: "/",
    start_url: "/",
    scope: "/",
    display: "standalone",
    theme_color: "#0A0B0D",
    background_color: "#0A0B0D",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
