"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import { Check, X, Loader2, Clock, Minus, ChevronDown, ChevronUp } from "lucide-react";
import type { StageState, StageMeta } from "./types";

interface TimelineItemProps {
  meta: StageMeta;
  stage: StageState;
  isLast: boolean;
  events?: any[];
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
      <div className={`${base} border-themeText bg-themeText`}>
        <Loader2 className="h-3.5 w-3.5 animate-spin text-themeBg" strokeWidth={1.5} aria-hidden="true" />
      </div>
    );
  }
  if (status === "skipped") {
    return (
      <div className={`${base} border-themeBorder bg-transparent opacity-30`}>
        <Minus className="h-3 w-3 text-themeTextMuted" strokeWidth={1.5} aria-hidden="true" />
      </div>
    );
  }
  // pending
  return (
    <div className={`${base} border-themeBorder bg-transparent`}>
      <Clock className="h-3 w-3 text-themeTextMuted/40" strokeWidth={1.5} aria-hidden="true" />
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
  events = [],
}: TimelineItemProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const isPending = stage.status === "pending";
  const isActive = stage.status === "active";
  const isFailed = stage.status === "failed";
  const isSkipped = stage.status === "skipped";
  const isCompleted = stage.status === "completed";

  const isClickable = !isPending && !isSkipped;
  const [isExpanded, setIsExpanded] = useState(isActive);
  const [copied, setCopied] = useState(false);

  // Auto-expand when stage becomes active
  useEffect(() => {
    if (isActive) {
      setIsExpanded(true);
    }
  }, [isActive]);

  useEffect(() => {
    if (isActive || isFailed) {
      containerRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [isActive, isFailed]);

  // Filter logs relevant to this stage
  const stageEvents = useMemo(() => {
    return events.filter((e) => {
      const rawStage = (e.stage ?? e.state ?? "").toUpperCase();
      if (meta.state === "COMPILING") {
        return rawStage === "COMPILING" || e.type === "compiler_log";
      }
      return rawStage === meta.state;
    });
  }, [events, meta.state]);

  const labelColor = isFailed
    ? "text-red-700 dark:text-red-400"
    : isSkipped
      ? "text-themeText/20"
      : isActive
        ? "text-themeText"
        : isPending
          ? "text-themeTextMuted/40"
          : "text-themeText";

  const descColor = isFailed
    ? "text-red-600/70 dark:text-red-400/70"
    : isSkipped
      ? "text-themeText/15"
      : isPending
        ? "text-themeTextMuted/25"
        : "text-themeTextMuted";

  // Connector line: gold when completed, muted when pending/skipped
  const lineColor = isCompleted
    ? "bg-[#D4AF37]/40"
    : "bg-themeBorder";

  return (
    <div ref={containerRef} className="flex gap-5">
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
          onClick={() => isClickable && setIsExpanded(!isExpanded)}
          className={[
            "group border-t py-4 pl-4 pr-4 transition-all duration-500 select-none",
            isClickable ? "cursor-pointer hover:bg-themeBgSecondary/10" : "",
            isActive
              ? "border-t-themeBorder border-l-2 border-l-[#D4AF37] pl-5 animate-active-stage bg-[#D4AF37]/5"
              : isFailed
                ? "border-t-themeBorder border-l-2 border-l-red-600 pl-5 bg-red-600/5"
                : isSkipped
                  ? "border-t-themeBorder/30 opacity-30"
                  : isPending
                    ? "border-t-themeBorder/50"
                    : "border-t-themeBorder",
          ].join(" ")}
        >
          <div className="flex items-start justify-between gap-2">
            <p
              className={`text-sm font-medium transition-colors duration-500 ${labelColor}`}
            >
              {meta.label}
            </p>
            <div className="flex items-center gap-2">
              {stage.timestamp && !isPending && (
                <time
                  dateTime={stage.timestamp}
                  className="shrink-0 text-[10px] tracking-[0.15em] text-themeTextMuted/50"
                >
                  {new Date(stage.timestamp).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </time>
              )}
              {isClickable && (
                <div className="text-themeTextMuted/40 group-hover:text-themeText transition-colors duration-300">
                  {isExpanded ? (
                    <ChevronUp className="h-3.5 w-3.5" strokeWidth={1.5} />
                  ) : (
                    <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.5} />
                  )}
                </div>
              )}
            </div>
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
            <pre className="mt-3 overflow-x-auto border border-red-500/20 bg-red-500/5 px-3 py-2 font-mono text-xs text-red-700 dark:text-red-400">
              {stage.message}
            </pre>
          )}

          {/* Expanded logs / details */}
          {isExpanded && isClickable && (
            <div className="mt-3 space-y-2 border-t border-themeBorder/20 pt-3" onClick={(e) => e.stopPropagation()}>
              {stageEvents.length > 0 ? (
                <>
                  <div className="flex justify-between items-center px-1 mb-1">
                    <span className="text-[10px] text-themeTextMuted/50 uppercase tracking-[0.1em] font-medium">Stage Logs</span>
                    <button
                      type="button"
                      onClick={() => {
                        const logText = stageEvents.map((evt) => {
                          const time = evt.timestamp
                            ? `[${new Date(evt.timestamp).toLocaleTimeString()}] `
                            : "";
                          return `${time}${evt.message || evt.content || evt.details || ""}`;
                        }).join("\n");
                        navigator.clipboard.writeText(logText).then(() => {
                          setCopied(true);
                          setTimeout(() => setCopied(false), 2000);
                        });
                      }}
                      className="text-[10px] text-[#D4AF37] hover:underline uppercase tracking-[0.15em] font-medium transition-all duration-300"
                    >
                      {copied ? "Copied!" : "Copy Logs"}
                    </button>
                  </div>
                  <div className="max-h-60 overflow-y-auto bg-black/10 dark:bg-black/40 p-3 font-mono text-[11px] leading-relaxed text-themeText/95 rounded border border-themeBorder/20">
                    {stageEvents.map((evt, idx) => {
                      const time = evt.timestamp
                        ? new Date(evt.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
                        : "";
                      const content = evt.message || evt.content || evt.details || "";
                      const level = evt.level || "INFO";
                      const isError = level === "ERROR" || level === "WARNING" || evt.type === "error";
                      return (
                        <div key={idx} className={`py-0.5 ${isError ? "text-red-500" : ""}`}>
                          {time && <span className="opacity-40 mr-2">[{time}]</span>}
                          <span>{content}</span>
                        </div>
                      );
                    })}
                  </div>
                </>
              ) : (
                <p className="text-[11px] text-themeTextMuted/60 italic pl-1">
                  No detailed log entries recorded for this stage yet.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
