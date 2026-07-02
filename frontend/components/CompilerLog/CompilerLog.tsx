"use client";

import {
  useEffect,
  useRef,
  useState,
  useCallback,
  type KeyboardEvent,
} from "react";
import { Terminal, Pause, Play, Copy, Check } from "lucide-react";
import type { StreamEvent } from "@/hooks/useWebSocket";

export interface LogLine {
  id: string;
  timestamp: string;
  level: "INFO" | "WARNING" | "ERROR" | string;
  content: string;
}

interface CompilerLogProps {
  /** New log events pushed in from the parent (via WebSocket onMessage) */
  events: StreamEvent[];
}

let lineCounter = 0;
function nextId() {
  return `log-${++lineCounter}`;
}

/** Level → colour mapping (used inside dark terminal area) */
function levelClass(level: string): string {
  const l = level.toUpperCase();
  if (l === "ERROR") return "text-red-400";
  if (l === "WARNING") return "text-amber-300";
  return "text-emerald-400";
}

/**
 * CompilerLog — Real-time compiler log stream viewer.
 *
 * Receives WebSocket compiler_log events from the parent, displays them in
 * a scrollable monospaced terminal window. Supports auto-scroll toggle,
 * copy-all, and level-based colour coding.
 */
export default function CompilerLog({ events }: CompilerLogProps) {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const [copied, setCopied] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const prevEventLenRef = useRef(0);

  // Convert new incoming events to log lines
  useEffect(() => {
    if (events.length === prevEventLenRef.current) return;
    const newEvents = events.slice(prevEventLenRef.current);
    prevEventLenRef.current = events.length;

    const newLines: LogLine[] = newEvents
      .filter((ev) => ev.type === "compiler_log" || ev.content)
      .map((ev) => ({
        id: nextId(),
        timestamp: ev.timestamp ?? new Date().toISOString(),
        level: ev.level ?? "INFO",
        content: ev.content ?? ev.message ?? "",
      }));

    if (newLines.length > 0) {
      setLines((prev) => [...prev, ...newLines]);
    }
  }, [events]);

  // Auto-scroll to bottom when new lines arrive
  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [lines, autoScroll]);

  const handleCopy = useCallback(async () => {
    const text = lines
      .map((l) => `[${l.level}] ${l.content}`)
      .join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard access denied — silently ignore
    }
  }, [lines]);

  const toggleAutoScroll = useCallback(() => {
    setAutoScroll((v) => !v);
  }, []);

  const handleScrollPauseKey = useCallback(
    (e: KeyboardEvent<HTMLButtonElement>) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggleAutoScroll();
      }
    },
    [toggleAutoScroll]
  );

  return (
    <div className="flex flex-col border border-[#1A1A1A]/10 bg-[#F9F8F6] overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between border-b border-[#1A1A1A]/8 px-4 py-3">
        <div className="flex items-center gap-3">
          <Terminal className="h-3.5 w-3.5 text-[#6C6863]" strokeWidth={1.5} aria-hidden="true" />
          <span className="text-[10px] font-medium tracking-[0.25em] uppercase text-[#6C6863]">
            Compiler Output
          </span>
          {lines.length > 0 && (
            <span className="border border-[#1A1A1A]/10 px-2 py-0.5 text-[10px] text-[#6C6863]">
              {lines.length} lines
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Auto-scroll toggle */}
          <button
            type="button"
            id="compiler-log-autoscroll-toggle"
            onClick={toggleAutoScroll}
            onKeyDown={handleScrollPauseKey}
            aria-pressed={autoScroll}
            aria-label={autoScroll ? "Pause auto-scroll" : "Resume auto-scroll"}
            className="flex items-center gap-1.5 border border-[#1A1A1A]/15 px-3 py-1.5 text-[10px] font-medium tracking-[0.15em] uppercase text-[#6C6863] transition-colors duration-500 hover:border-[#1A1A1A]/30 hover:text-[#1A1A1A]"
          >
            {autoScroll ? (
              <Pause className="h-3 w-3" strokeWidth={1.5} aria-hidden="true" />
            ) : (
              <Play className="h-3 w-3" strokeWidth={1.5} aria-hidden="true" />
            )}
            {autoScroll ? "Pause" : "Resume"}
          </button>

          {/* Copy all */}
          <button
            type="button"
            id="compiler-log-copy-button"
            onClick={handleCopy}
            aria-label="Copy all log lines to clipboard"
            disabled={lines.length === 0}
            className="flex items-center gap-1.5 border border-[#1A1A1A]/15 px-3 py-1.5 text-[10px] font-medium tracking-[0.15em] uppercase text-[#6C6863] transition-colors duration-500 hover:border-[#1A1A1A]/30 hover:text-[#1A1A1A] disabled:opacity-30 disabled:cursor-not-allowed"
          >
            {copied ? (
              <Check className="h-3 w-3 text-emerald-600" strokeWidth={1.5} aria-hidden="true" />
            ) : (
              <Copy className="h-3 w-3" strokeWidth={1.5} aria-hidden="true" />
            )}
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>
      </div>

      {/* Log body — dark terminal area preserves code readability */}
      <div
        role="log"
        aria-live="polite"
        aria-label="Compiler log output"
        className="h-64 overflow-y-auto bg-[#1A1A1A] p-4 font-mono text-xs leading-relaxed"
        style={{ fontFamily: "'JetBrains Mono', monospace" }}
      >
        {lines.length === 0 ? (
          <p className="italic text-[#6C6863]">
            Waiting for compiler output…
          </p>
        ) : (
          lines.map((line) => (
            <div key={line.id} className="flex gap-2">
              <span className="shrink-0 text-[#6C6863]/60">
                {new Date(line.timestamp).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })}
              </span>
              <span className={`shrink-0 w-16 ${levelClass(line.level)}`}>
                [{line.level}]
              </span>
              <span className="text-[#EBE5DE]/80 break-all">{line.content}</span>
            </div>
          ))
        )}
        <div ref={bottomRef} aria-hidden="true" />
      </div>
    </div>
  );
}
