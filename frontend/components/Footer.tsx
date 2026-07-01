"use client";

import { Cpu, Github } from "lucide-react";

/**
 * HIPForge page footer with branding and links.
 */
export default function Footer() {
  return (
    <footer
      className="w-full border-t border-white/5 bg-surface-0 py-8"
      role="contentinfo"
    >
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-6 sm:flex-row">
        <div className="flex items-center gap-2 text-white/30">
          <Cpu className="h-4 w-4" aria-hidden="true" />
          <span className="text-sm">
            HIPForge &copy; {new Date().getFullYear()} — AI-powered CUDA to ROCm migration
          </span>
        </div>
        <a
          href="https://github.com"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="HIPForge on GitHub"
          className="flex items-center gap-2 text-sm text-white/30 transition-colors hover:text-white/60"
        >
          <Github className="h-4 w-4" aria-hidden="true" />
          <span>GitHub</span>
        </a>
      </div>
    </footer>
  );
}
