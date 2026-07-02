import type { Metadata } from "next";
import "@/styles/globals.css";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { ThemeProvider } from "@/components/ThemeProvider";

export const metadata: Metadata = {
  title: "HIPForge — AI-Powered CUDA to ROCm Migration",
  description:
    "Automatically translate CUDA GPU code to AMD HIP/ROCm with AI-assisted error repair and a complete audit trail.",
  keywords: ["CUDA", "ROCm", "HIP", "GPU", "migration", "AMD", "NVIDIA"],
  openGraph: {
    title: "HIPForge — CUDA to ROCm Migration",
    description: "AI-powered, self-healing CUDA to ROCm code migration platform.",
    type: "website",
  },
};

/**
 * Root layout shared across all HIPForge pages.
 * Provides ThemeProvider, Navbar, Footer, global styles, paper noise overlay,
 * and editorial grid lines.
 */
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Google Fonts — Playfair Display (editorial serif) + Inter (humanist sans) */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,500;1,400;1,500&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="flex min-h-screen flex-col antialiased" style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}>
        <ThemeProvider>
          {/* Paper noise texture — fixed overlay at ~2% opacity for "expensive paper" feel */}
          <div className="paper-noise" aria-hidden="true" />

          {/* Editorial vertical grid lines — 4 lines at column boundaries */}
          <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-40 hidden lg:block">
            <div className="absolute bottom-0 left-[8%] top-0 w-px" style={{ backgroundColor: "var(--border-subtle)" }} />
            <div className="absolute bottom-0 left-[33%] top-0 w-px" style={{ backgroundColor: "var(--border-subtle)" }} />
            <div className="absolute bottom-0 right-[33%] top-0 w-px" style={{ backgroundColor: "var(--border-subtle)" }} />
            <div className="absolute bottom-0 right-[8%] top-0 w-px" style={{ backgroundColor: "var(--border-subtle)" }} />
          </div>

          <Navbar />
          <main className="flex flex-1 flex-col">{children}</main>
          <Footer />
        </ThemeProvider>
      </body>
    </html>
  );
}
