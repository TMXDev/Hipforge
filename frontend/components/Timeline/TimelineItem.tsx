"use client";

import { Check, X, Loader2, Clock, Minus } from "lucide-react";
import type { StageState, StageMeta } from "./types";

interface TimelineItemProps {
  meta: StageMeta;
  stage: StageState;
  isLast: boolean;
}

/**
 * StatusIcon — Square luxury editorial stage icons.
 * Replaces rounded circles with precise rectangular shapes.
 */
function StatusIcon({ status }: { status: StageState["status"] }) {
  // 8×8 square icons — architectural precision
  const base = "flex h-8 w-8 shrink-0 items-center justify-center border";

  if (status === "completed") {
    return (
      <div className={`${base} border-[#D4AF37] bg-[#D4AF37]`}>
        <Check className="h-3.5 w-3.5 text-white" strokeWidth={2} aria-hidden="true" />
      </div>
    );
  }
  if (status === "failed") {
    return (
      <div className={`${base} border-red-700 bg-red-700`}>
        <X className="h-3.5 w-3.5 text-white" strokeWidth={2} aria-hidden="true" />
      </div>
    );
  }
  if (status === "active") {
    return (
      <div className={`${base} border-[#1A1A1A] bg-[#1A1A1A]`}>
        <Loader2 className="h-3.5 w-3.5 animate-spin text-[#F9F8F6]" strokeWidth={1.5} aria-hidden="true" />
      </div>
    );
  }
  if (status === "skipped") {
    return (
      <div className={`${base} border-[#1A1A1A]/10 bg-transparent opacity-30`}>
        <Minus className="h-3 w-3 text-[#6C6863]" strokeWidth={1.5} aria-hidden="true" />
      </div>
    );
  }
  // pending
  return (
    <div className={`${base} border-[#1A1A1A]/15 bg-transparent`}>
      <Clock className="h-3 w-3 text-[#6C6863]/40" strokeWidth={1.5} aria-hidden="true" />
    </div>
  );
}

/**
 * TimelineItem — A single row in the vertical migration timeline.
 *
 * Luxury editorial style: square status icons, top-border-only cards,
 * gold connector line for completed stages, gold left-border for active.
 */
export default function TimelineItem({
  meta,
  stage,
  isLast,
}: TimelineItemProps) {
  const isPending = stage.status === "pending";
  const isActive = stage.status === "active";
  const isFailed = stage.status === "failed";
  const isSkipped = stage.status === "skipped";
  const isCompleted = stage.status === "completed";

  const labelColor = isFailed
    ? "text-red-700"
    : isSkipped
      ? "text-[#1A1A1A]/20"
      : isActive
        ? "text-[#1A1A1A]"
        : isPending
          ? "text-[#6C6863]/40"
          : "text-[#1A1A1A]";

  const descColor = isFailed
    ? "text-red-600/70"
    : isSkipped
      ? "text-[#1A1A1A]/15"
      : isPending
        ? "text-[#6C6863]/25"
        : "text-[#6C6863]";

  // Connector line: gold when completed, muted when pending/skipped
  const lineColor = isCompleted
    ? "bg-[#D4AF37]/40"
    : "bg-[#1A1A1A]/8";

  return (
    <div className="flex gap-5">
      {/* Left column: square icon + connector line */}
      <div className="flex flex-col items-center">
        <StatusIcon status={stage.status} />
        {!isLast && (
          <div
            className={`mt-1 w-px flex-1 min-h-[32px] transition-colors duration-700 ${lineColor}`}
            aria-hidden="true"
          />
        )}
      </div>

      {/* Right column: content */}
      <div className={`${isLast ? "pb-0" : "pb-6"} min-w-0 flex-1`}>
        <div
          className={[
            "border-t py-4 pl-4 pr-4 transition-all duration-500",
            isActive
              ? "border-t-[#1A1A1A]/10 border-l-2 border-l-[#D4AF37] pl-5"
              : isFailed
                ? "border-t-[#1A1A1A]/10 border-l-2 border-l-red-600 pl-5"
                : isSkipped
                  ? "border-t-[#1A1A1A]/5 opacity-30"
                  : isPending
                    ? "border-t-[#1A1A1A]/8"
                    : "border-t-[#1A1A1A]/10",
          ].join(" ")}
        >
          <div className="flex items-start justify-between gap-2">
            <p
              className={`text-sm font-medium transition-colors duration-500 ${labelColor}`}
            >
              {meta.label}
            </p>
            {stage.timestamp && !isPending && (
              <time
                dateTime={stage.timestamp}
                className="shrink-0 text-[10px] tracking-[0.15em] text-[#6C6863]/50"
              >
                {new Date(stage.timestamp).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })}
              </time>
            )}
          </div>

          <p className={`mt-1 text-xs leading-relaxed transition-colors duration-500 ${descColor}`}>
            {stage.message || meta.description}
          </p>

          {/* Active pulse indicator */}
          {isActive && (
            <div className="mt-2.5 flex items-center gap-2">
              <span
                className="h-1.5 w-1.5 bg-[#D4AF37] animate-pulse"
                aria-hidden="true"
              />
              <span className="text-[10px] font-medium tracking-[0.2em] uppercase text-[#D4AF37]">
                In Progress
              </span>
            </div>
          )}

          {/* Failed error message — monospace code block */}
          {isFailed && stage.message && (
            <pre className="mt-3 overflow-x-auto border border-red-200 bg-red-50 px-3 py-2 font-mono text-xs text-red-700">
              {stage.message}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
