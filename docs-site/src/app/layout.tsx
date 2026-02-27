import type { Metadata } from "next";
import { Suspense } from "react";
import { Inter, JetBrains_Mono } from "next/font/google";
import "highlight.js/styles/github-dark.min.css";
import "@/styles/notebook.css";
import "./globals.css";
import { PostHogProvider } from "@/components/providers/PostHogProvider";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  weight: ["300", "400", "500"],
  variable: "--font-jetbrains",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://everyrow.io"),
  title: "Everyrow Documentation",
  description: "EveryRow documentation. A researcher for every row. Forecast, score, classify, or research entire datasets.",
  openGraph: {
    siteName: "Everyrow",
    type: "website",
    images: [{ url: "https://everyrow.io/everyrow-og.png" }],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body>
        <Suspense fallback={null}>
          <PostHogProvider>{children}</PostHogProvider>
        </Suspense>
      </body>
    </html>
  );
}
