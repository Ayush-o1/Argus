import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Providers } from "./providers";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  // next/font self-hosts both faces as part of the build, so there is no slow
  // network fetch for "swap" to protect against — the font is already local.
  // "optional" skips the swap repaint entirely when the font isn't ready
  // inside its first ~100ms. Tried as a candidate fix for a separate,
  // unresolved LCP-timing finding; measured to have no effect on that (see
  // docs/performance.md) and kept anyway since it removes a real, if here
  // mostly theoretical, repaint source at no cost.
  display: "optional",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  // next/font self-hosts both faces as part of the build, so there is no slow
  // network fetch for "swap" to protect against — the font is already local.
  // "optional" skips the swap repaint entirely when the font isn't ready
  // inside its first ~100ms. Tried as a candidate fix for a separate,
  // unresolved LCP-timing finding; measured to have no effect on that (see
  // docs/performance.md) and kept anyway since it removes a real, if here
  // mostly theoretical, repaint source at no cost.
  display: "optional",
});

export const metadata: Metadata = {
  title: "ARGUS — Synthetic Intelligence Analysis Platform",
  description:
    "A graph-native investigation and analytics simulator built on a fully synthetic, India-grounded dataset. No real individuals or organizations are represented.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
