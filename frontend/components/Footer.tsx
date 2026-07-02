"use client";

import Link from "next/link";
import { Github } from "lucide-react";

/**
 * HIPForge page footer — dark inverted editorial section.
 */
export default function Footer() {
  return (
    <footer
      className="w-full border-t border-themeBorder bg-themeDarkSection py-12"
      role="contentinfo"
    >
      <div className="mx-auto flex max-w-[1600px] flex-col items-start justify-between gap-8 px-8 sm:flex-row sm:items-center lg:px-16">
        {/* Brand */}
        <div className="flex flex-col gap-2">
          <span
            className="font-serif text-lg font-normal text-themeBg"
            style={{ fontFamily: "'Playfair Display', Georgia, serif" }}
          >
            HIPForge
          </span>
          <p className="text-[10px] font-medium tracking-[0.25em] uppercase text-themeTextMuted">
            AI-Powered CUDA to ROCm Migration
          </p>
        </div>

        {/* Right group */}
        <div className="flex flex-col items-start gap-4 sm:items-end">
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="HIPForge on GitHub"
            className="group flex items-center gap-2 text-themeTextMuted transition-colors duration-500 hover:text-[#D4AF37]"
          >
            <Github className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
            <span className="text-[10px] font-medium tracking-[0.2em] uppercase">
              GitHub
            </span>
          </a>
          <p className="text-[10px] tracking-[0.15em] text-themeTextMuted/60">
            © {new Date().getFullYear()} HIPForge — All rights reserved
          </p>
        </div>
      </div>
    </footer>
  );
}
