import { Geist, Geist_Mono } from "next/font/google";

// Self-hosted at build time by next/font; only Geist Sans is preloaded (vault Design/Typography).
export const geistSans = Geist({ subsets: ["latin"], variable: "--font-geist-sans", display: "swap" });
export const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap", preload: false });
