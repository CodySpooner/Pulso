import type { Metadata, Viewport } from "next";
import { ClerkProvider } from "@clerk/nextjs";

import { Providers } from "@/components/providers/providers";
import { authBypass } from "@/lib/auth";

import { geistMono, geistSans } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Pulso", template: "%s · Pulso" },
  description: "The pulse of what's selling: product research and calibrated trend forecasts.",
  applicationName: "Pulso",
  appleWebApp: { capable: true, title: "Pulso", statusBarStyle: "black-translucent" },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  // Canvas colours from tokens.css (gray-950 dark, white light); the manifest can't read CSS variables.
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0A0B0D" },
    { media: "(prefers-color-scheme: light)", color: "#FFFFFF" },
  ],
  viewportFit: "cover",
};

const clerkAppearance = {
  variables: {
    colorPrimary: "var(--primary)",
    colorBackground: "var(--card)",
    colorForeground: "var(--foreground)",
    colorMutedForeground: "var(--muted-foreground)",
    colorInput: "var(--background)",
    colorInputForeground: "var(--foreground)",
    colorBorder: "var(--border)",
    colorDanger: "var(--negative)",
    borderRadius: "var(--radius)",
    fontFamily: "var(--font-sans)",
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  const app = <Providers>{children}</Providers>;
  return (
    <html lang="en" suppressHydrationWarning className={`${geistSans.variable} ${geistMono.variable}`}>
      <body>{authBypass ? app : <ClerkProvider appearance={clerkAppearance}>{app}</ClerkProvider>}</body>
    </html>
  );
}
