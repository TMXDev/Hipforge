"use client";

import Link from "next/link";
import { Github, Sun, Moon } from "lucide-react";
import { useTheme } from "@/components/ThemeProvider";

/**
 * HIPForge luxury editorial navigation bar.
 * Typographic wordmark, minimal uppercase nav links with gold hover,
 * and a sun/moon theme toggle.
 */
export default function Navbar() {
  const { theme, toggleTheme } = useTheme();

  return (
    <nav
      className="sticky top-0 z-50 w-full backdrop-blur-sm"
      style={{
        backgroundColor: "color-mix(in srgb, var(--bg-primary) 95%, transparent)",
        borderBottom: "1px solid var(--border-primary)",
      }}
      role="banner"
    >
      <div className="mx-auto flex h-16 max-w-[1600px] items-center justify-between px-8 lg:px-16">
        {/* Brand — typographic wordmark */}
        <Link href="/" className="group flex items-baseline gap-3 no-underline">
          <span
            className="font-serif text-xl font-normal tracking-tight transition-colors duration-500 group-hover:text-[#D4AF37]"
            style={{
              fontFamily: "'Playfair Display', Georgia, serif",
              color: "var(--text-primary)",
            }}
          >
            HIPForge
          </span>
          <span
            className="hidden text-[10px] font-medium tracking-[0.3em] uppercase sm:inline"
            style={{ color: "var(--text-muted)" }}
          >
            CUDA → ROCm
          </span>
        </Link>

        {/* Navigation */}
        <div className="flex items-center gap-6">
          {/* Nav links */}
          <nav className="hidden items-center gap-8 sm:flex" aria-label="Primary navigation">
            <Link
              href="/upload"
              className="group relative text-[10px] font-medium tracking-[0.25em] uppercase transition-colors duration-500"
              style={{ color: "var(--text-muted)" }}
            >
              <span className="hover-text-primary transition-colors duration-500">Migrate</span>
              <span className="absolute -bottom-1 left-0 h-px w-0 bg-[#D4AF37] transition-all duration-500 group-hover:w-full" />
            </Link>
            <Link
              href="/health"
              className="group relative text-[10px] font-medium tracking-[0.25em] uppercase transition-colors duration-500"
              style={{ color: "var(--text-muted)" }}
            >
              <span className="hover-text-primary transition-colors duration-500">Health</span>
              <span className="absolute -bottom-1 left-0 h-px w-0 bg-[#D4AF37] transition-all duration-500 group-hover:w-full" />
            </Link>
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="HIPForge on GitHub"
              className="group relative text-[10px] font-medium tracking-[0.25em] uppercase transition-colors duration-500"
              style={{ color: "var(--text-muted)" }}
            >
              GitHub
              <span className="absolute -bottom-1 left-0 h-px w-0 bg-[#D4AF37] transition-all duration-500 group-hover:w-full" />
            </a>
          </nav>

          {/* API Status badge */}
          <div
            className="flex items-center gap-2 px-3 py-1.5"
            style={{ border: "1px solid var(--border-primary)" }}
          >
            <span
              className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse-slow"
              aria-hidden="true"
            />
            <span
              className="text-[10px] font-medium tracking-[0.2em] uppercase"
              style={{ color: "var(--text-muted)" }}
            >
              API Online
            </span>
          </div>

          {/* ── Theme Toggle ── */}
          <button
            type="button"
            id="theme-toggle-button"
            onClick={toggleTheme}
            aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
            className="flex h-9 w-9 items-center justify-center transition-all duration-500 hover:text-[#D4AF37]"
            style={{
              border: "1px solid var(--border-primary)",
              color: "var(--text-muted)",
              backgroundColor: "transparent",
            }}
          >
            {theme === "light" ? (
              <Moon className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
            ) : (
              <Sun className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
            )}
          </button>
        </div>
      </div>
    </nav>
  );
}
