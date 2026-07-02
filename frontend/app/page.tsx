"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";

/** Process steps for the editorial flow section */
const PROCESS_STEPS = [
  {
    num: "01",
    title: "Upload",
    description:
      "Provide a single .cu CUDA source file or a .zip archive of your project. Paste code directly or drag-and-drop.",
  },
  {
    num: "02",
    title: "Translate",
    description:
      "hipify-clang performs automated CUDA-to-HIP API mapping with deep source transformation.",
  },
  {
    num: "03",
    title: "Repair",
    description:
      "An AI triad — Analysis, Patch, and Research agents — resolve compiler errors in a self-healing loop.",
  },
  {
    num: "04",
    title: "Download",
    description:
      "Receive a complete package: translated source, git-compatible patches, a migration journal, and a full report.",
  },
];

/** Feature cards for the dark editorial section */
const FEATURES = [
  {
    label: "Translation Engine",
    title: "hipify-clang",
    description:
      "Deep CUDA API mapping across kernel syntax, memory management, and device intrinsics.",
  },
  {
    label: "AI Repair Loop",
    title: "Self-Healing Compilation",
    description:
      "Three specialised agents collaborate to diagnose, patch, and research every compiler error automatically.",
  },
  {
    label: "Audit Trail",
    title: "Full Provenance",
    description:
      "Git-compatible patches, a migration journal, and a downloadable ZIP with complete change history.",
  },
];

/**
 * Home — Editorial landing page for HIPForge.
 * Flow: Landing (/) → Upload (/upload) → Dashboard (/migration/[id])
 */
export default function HomePage() {
  return (
    <div className="flex flex-1 flex-col">

      {/* ══════════════════════════════════════════════════
          HERO SECTION — Asymmetric editorial layout
      ══════════════════════════════════════════════════ */}
      <section className="relative flex min-h-[92vh] flex-col justify-end overflow-hidden px-8 pb-20 pt-24 lg:px-16 lg:pb-28">

        {/* Decorative top border */}
        <div className="absolute left-0 right-0 top-0 h-px bg-themeBorder" aria-hidden="true" />

        {/* Vertical text label — desktop only */}
        <div
          className="absolute right-10 top-1/2 hidden -translate-y-1/2 lg:block"
          aria-hidden="true"
        >
          <span className="vertical-text text-themeTextMuted opacity-30">
            Editorial / Vol. 01 — CUDA Migration
          </span>
        </div>

        {/* Content — bottom-left aligned (luxury asymmetry) */}
        <div className="max-w-[1600px]">
          {/* Overline label */}
          <div className="mb-6 flex items-center gap-3">
            <div className="h-px w-10 bg-themeText/30" aria-hidden="true" />
            <span className="overline">CUDA → ROCm Migration Platform</span>
          </div>

          {/* Massive headline — Playfair Display with mixed italic */}
          <h1
            className="max-w-4xl font-serif text-5xl font-normal leading-[0.95] tracking-tight text-themeText sm:text-6xl lg:text-8xl xl:text-[7rem]"
            style={{ fontFamily: "'Playfair Display', Georgia, serif" }}
          >
            Migrate CUDA
            <br />
            to{" "}
            <em className="not-italic" style={{ color: "#D4AF37", fontStyle: "italic" }}>
              ROCm
            </em>
            <br />
            in minutes
          </h1>

          {/* Body copy */}
          <p className="mt-8 max-w-lg text-base leading-relaxed text-themeTextMuted lg:text-lg">
            HIPForge handles automated translation, AI-assisted compilation repair,
            and delivers a complete migration report — so you ship faster.
          </p>

          {/* CTA row */}
          <div className="mt-12 flex flex-col items-start gap-4 sm:flex-row sm:items-center">
            {/* Primary CTA — gold slide animation */}
            <Link href="/upload" className="btn-primary" id="hero-cta-button">
              <span>Begin Migration</span>
              <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
            </Link>

            {/* Secondary link */}
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="group relative text-xs font-medium tracking-[0.2em] uppercase text-themeTextMuted transition-colors duration-500 hover:text-themeText"
            >
              View on GitHub
              <span className="absolute -bottom-0.5 left-0 h-px w-0 bg-[#D4AF37] transition-all duration-700 group-hover:w-full" />
            </a>
          </div>
        </div>

        {/* Bottom decorative separator */}
        <div className="absolute bottom-0 left-0 right-0 h-px bg-themeBorder" aria-hidden="true" />
      </section>

      {/* ══════════════════════════════════════════════════
          FEATURES SECTION — Dark inverted editorial
      ══════════════════════════════════════════════════ */}
      <section className="bg-themeDarkSection px-8 py-24 lg:px-16 lg:py-32">
        <div className="mx-auto max-w-[1600px]">
          {/* Section header */}
          <div className="mb-16 flex items-start justify-between border-b border-themeBorder pb-8">
            <div>
              <span className="overline text-themeTextMuted">What We Offer</span>
              <h2
                className="mt-3 font-serif text-3xl font-normal text-themeTextInverted lg:text-5xl"
                style={{ fontFamily: "'Playfair Display', Georgia, serif" }}
              >
                Precision at every{" "}
                <em style={{ color: "#D4AF37" }}>stage</em>
              </h2>
            </div>
          </div>

          {/* Feature grid — 3 columns, top-border-only cards */}
          <div className="grid grid-cols-1 gap-0 sm:grid-cols-3">
            {FEATURES.map((feature, i) => (
              <div
                key={feature.title}
                className={[
                  "border-t border-themeBorder py-10 transition-all duration-700",
                  i > 0 ? "sm:pl-10" : "",
                  i < FEATURES.length - 1 ? "sm:border-r sm:border-themeBorder sm:pr-10" : "",
                ].join(" ")}
              >
                <span className="overline text-themeTextMuted">{feature.label}</span>
                <h3
                  className="mt-4 font-serif text-2xl font-normal text-themeTextInverted lg:text-3xl"
                  style={{ fontFamily: "'Playfair Display', Georgia, serif" }}
                >
                  {feature.title}
                </h3>
                <p className="mt-4 text-sm leading-relaxed text-themeTextMuted">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════
          PROCESS SECTION — Light, numbered editorial steps
      ══════════════════════════════════════════════════ */}
      <section className="px-8 py-24 lg:px-16 lg:py-32">
        <div className="mx-auto max-w-[1600px]">
          {/* Section header */}
          <div className="mb-16 border-b border-themeBorder pb-8">
            <span className="overline">The Process</span>
            <h2
              className="mt-3 font-serif text-3xl font-normal text-themeText lg:text-5xl"
              style={{ fontFamily: "'Playfair Display', Georgia, serif" }}
            >
              Four steps to{" "}
              <em style={{ color: "#D4AF37" }}>complete migration</em>
            </h2>
          </div>

          {/* Steps — numbered with extreme type scale */}
          <div className="grid grid-cols-1 gap-0 sm:grid-cols-2 lg:grid-cols-4">
            {PROCESS_STEPS.map((step, i) => (
              <div
                key={step.num}
                className={[
                  "group border-t border-themeBorder py-10 transition-all duration-700",
                  i > 0 ? "sm:pl-10" : "",
                  i < PROCESS_STEPS.length - 1 ? "sm:border-r sm:border-themeBorder sm:pr-10" : "",
                ].join(" ")}
              >
                {/* Large editorial number */}
                <span
                  className="block font-serif text-6xl font-normal leading-none text-themeText/10 transition-colors duration-700 group-hover:text-[#D4AF37]/30 lg:text-8xl"
                  aria-hidden="true"
                  style={{ fontFamily: "'Playfair Display', Georgia, serif" }}
                >
                  {step.num}
                </span>
                <h3
                  className="mt-6 font-serif text-xl font-normal text-themeText lg:text-2xl"
                  style={{ fontFamily: "'Playfair Display', Georgia, serif" }}
                >
                  {step.title}
                </h3>
                <p className="mt-3 text-sm leading-relaxed text-themeTextMuted">
                  {step.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════
          CTA STRIP — Dark closing section
      ══════════════════════════════════════════════════ */}
      <section className="bg-themeDarkSection px-8 py-24 lg:px-16 lg:py-32">
        <div className="mx-auto max-w-[1600px]">
          <div className="flex flex-col items-start gap-10 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <span className="overline text-themeTextMuted">Ready to migrate?</span>
              <h2
                className="mt-4 max-w-2xl font-serif text-4xl font-normal leading-tight text-themeTextInverted lg:text-6xl"
                style={{ fontFamily: "'Playfair Display', Georgia, serif" }}
              >
                Begin your{" "}
                <em style={{ color: "#D4AF37" }}>migration</em>{" "}
                today
              </h2>
            </div>

            <div className="flex flex-col gap-4 sm:flex-row">
              <Link
                href="/upload"
                id="cta-strip-button"
                className="btn-primary"
                style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
              >
                <span>Upload Your Code</span>
                <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
              </Link>
            </div>
          </div>

          {/* Decorative bottom rule */}
          <div className="mt-20 border-t border-themeBorder" />
        </div>
      </section>
    </div>
  );
}
