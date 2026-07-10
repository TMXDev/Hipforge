"use client";

import {
  useEffect,
  useRef,
  useState,
  useCallback,
  useMemo,
  type KeyboardEvent,
} from "react";
import { Terminal, Pause, Play, Copy, Check, Search } from "lucide-react";
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
 * copy-all, level-based colour coding, error/warning counts, search filter,
 * and line numbers.
 */
export default function CompilerLog({ events }: CompilerLogProps) {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const [copied, setCopied] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
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
      setLines((prev) => {
        const filteredNew = newLines.filter(
          (nl) => !prev.some((pl) => pl.timestamp === nl.timestamp && pl.content === nl.content)
        );
        return [...prev, ...filteredNew];
      });
    }
  }, [events]);

  // Auto-scroll to bottom when new lines arrive (ponytail: direct scrollTop to avoid viewport/camera scroll thrashing)
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [lines, autoScroll]);

  // Error/warning counts
  const { errorCount, warnCount } = useMemo(() => {
    let errors = 0;
    let warns = 0;
    for (const l of lines) {
      const lev = l.level.toUpperCase();
      if (lev === "ERROR") errors++;
      else if (lev === "WARNING") warns++;
    }
    return { errorCount: errors, warnCount: warns };
  }, [lines]);

  // Filtered lines for search
  const displayLines = useMemo(() => {
    if (!searchQuery.trim()) return lines;
    const q = searchQuery.toLowerCase();
    return lines.filter((l) => l.content.toLowerCase().includes(q) || l.level.toLowerCase().includes(q));
  }, [lines, searchQuery]);

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
    <div className="flex flex-col border border-themeBorder bg-themeCard overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between border-b border-themeBorder px-4 py-3">
        <div className="flex items-center gap-3">
          <Terminal className="h-3.5 w-3.5 text-themeTextMuted" strokeWidth={1.5} aria-hidden="true" />
          <span className="text-[10px] font-medium tracking-[0.25em] uppercase text-themeTextMuted">
            Compiler Output
          </span>
          {lines.length > 0 && (
            <span className="border border-themeBorder px-2 py-0.5 text-[10px] text-themeTextMuted">
              {lines.length} lines
            </span>
          )}
          {/* Error/warning count badges */}
          {errorCount > 0 && (
            <span className="border border-red-500/30 bg-red-500/10 px-2 py-0.5 text-[10px] font-medium text-red-400">
              {errorCount} error{errorCount !== 1 ? "s" : ""}
            </span>
          )}
          {warnCount > 0 && (
            <span className="border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-300">
              {warnCount} warning{warnCount !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Search filter */}
          <div className="relative flex items-center">
            <Search className="absolute left-2 h-3 w-3 text-themeTextMuted/50" strokeWidth={1.5} aria-hidden="true" />
            <input
              type="text"
              id="compiler-log-search"
              placeholder="Filter…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-7 w-28 border border-themeBorder bg-transparent pl-7 pr-2 text-[10px] text-themeText placeholder:text-themeTextMuted/40 focus:w-40 focus:border-[#D4AF37]/50 focus:outline-none transition-all duration-300"
              aria-label="Filter compiler log lines"
            />
          </div>

          {/* Auto-scroll toggle */}
          <button
            type="button"
            id="compiler-log-autoscroll-toggle"
            onClick={toggleAutoScroll}
            onKeyDown={handleScrollPauseKey}
            aria-pressed={autoScroll}
            aria-label={autoScroll ? "Pause auto-scroll" : "Resume auto-scroll"}
            className="flex items-center gap-1.5 border border-themeBorder px-3 py-1.5 text-[10px] font-medium tracking-[0.15em] uppercase text-themeTextMuted transition-colors duration-500 hover:border-themeBorderStrong hover:text-themeText"
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
            className="flex items-center gap-1.5 border border-themeBorder px-3 py-1.5 text-[10px] font-medium tracking-[0.15em] uppercase text-themeTextMuted transition-colors duration-500 hover:border-themeBorderStrong hover:text-themeText disabled:opacity-30 disabled:cursor-not-allowed"
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
        ref={containerRef}
        role="log"
        aria-live="polite"
        aria-label="Compiler log output"
        className="h-64 overflow-y-auto bg-[#1A1A1A] p-4 font-mono text-xs leading-relaxed text-[#EDE8E2]"
        style={{ fontFamily: "'JetBrains Mono', monospace" }}
      >
        {displayLines.length === 0 ? (
          <p className="italic text-[#6C6863]">
            {searchQuery ? "No matching log lines." : "Waiting for compiler output…"}
          </p>
        ) : (
          displayLines.map((line, idx) => (
            <div key={line.id} className="flex gap-2">
              {/* Line number */}
              <span className="shrink-0 w-8 text-right text-[#6C6863]/40 select-none">
                {idx + 1}
              </span>
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
      </div>
    </div>
  );
}
