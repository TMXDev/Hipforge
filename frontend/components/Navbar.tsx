"use client";

import { Cpu } from "lucide-react";

/**
 * HIPForge top navigation bar.
 * Displays the brand logo and tagline.
 */
export default function Navbar() {
  return (
    <nav
      className="sticky top-0 z-50 w-full border-b border-white/5 bg-surface-0/80 backdrop-blur-md"
      role="banner"
    >
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 shadow-lg shadow-brand-900/40">
            <Cpu className="h-5 w-5 text-white" aria-hidden="true" />
          </div>
          <div>
            <span className="text-lg font-semibold tracking-tight text-white">
              HIPForge
            </span>
            <span className="ml-2 hidden text-sm text-white/40 sm:inline">
              CUDA → ROCm Migration
            </span>
          </div>
        </div>

        {/* Status pill */}
        <div className="flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1">
          <span
            className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse-slow"
            aria-hidden="true"
          />
          <span className="text-xs font-medium text-emerald-400">
            API Online
          </span>
        </div>
      </div>
    </nav>
  );
}
