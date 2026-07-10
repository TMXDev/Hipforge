"use client";

import { useParams } from "next/navigation";
import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { ArrowLeft, Download, RefreshCw, Clock, Timer } from "lucide-react";
import Link from "next/link";
import Timeline from "@/components/Timeline";
import CompilerLog from "@/components/CompilerLog";
import JournalViewer from "@/components/JournalViewer";
import ReportViewer from "@/components/ReportViewer";
import { useWebSocket, type StreamEvent } from "@/hooks/useWebSocket";
import { getDownloadUrl, getMigrationStatus, getCompilerLogs } from "@/services/api";

/**
 * Migration Dashboard page — /migration/[id]
 *
 * Hosts a shared WebSocket connection and fans out events to:
 *  1. Timeline     — workflow state progression
 *  2. CompilerLog  — compiler stdout/stderr lines
 *  3. JournalViewer — fetched from REST API (polls every 4s while active)
 *  4. ReportViewer  — fetched from REST API + Download button
 *
 * isTerminal is set by BOTH the WebSocket terminal event AND a HTTP
 * polling fallback (every 3s) so the download button appears reliably.
 */
export default function MigrationPage() {
  const params = useParams();
  const migrationId =
    typeof params.id === "string" ? params.id : String(params.id ?? "");

  /* ── Shared event collection ── */
  const [allEvents, setAllEvents] = useState<StreamEvent[]>([]);
  const [isTerminal, setIsTerminal] = useState(false);
  const [migrationStatus, setMigrationStatus] = useState<string>("QUEUED");
  const [migrationStage, setMigrationStage] = useState<string>("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [startTime] = useState<number>(Date.now());
  const [elapsedDisplay, setElapsedDisplay] = useState<string>("0s");

  // Ref to avoid stale closure in polling interval
  const isTerminalRef = useRef(false);

  const markTerminal = useCallback(() => {
    if (!isTerminalRef.current) {
      isTerminalRef.current = true;
      setIsTerminal(true);
    }
  }, []);

  /* ── HTTP Status Polling — runs every 3s until terminal ── */
  useEffect(() => {
    let cancelled = false;

    async function pollStatus() {
      try {
        const s = await getMigrationStatus(migrationId);
        if (cancelled) return;

        const st = (s.status || "").toUpperCase();
        setMigrationStatus(st);
        setMigrationStage(s.stage || s.current_stage || "");
        setLastUpdated(new Date());

        if (st === "COMPLETED" || st === "FAILED") {
          markTerminal();
        }
      } catch {
        // silently ignore poll failures
      }
    }

    // Immediate first poll
    void pollStatus();

    // Continue polling every 3s until terminal
    const interval = setInterval(() => {
      if (isTerminalRef.current) {
        clearInterval(interval);
        return;
      }
      void pollStatus();
    }, 3000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [migrationId, markTerminal]);

  /* ── Elapsed time counter — ticks every second while active ── */
  useEffect(() => {
    if (isTerminal) return;
    const tick = setInterval(() => {
      const secs = Math.floor((Date.now() - startTime) / 1000);
      if (secs < 60) setElapsedDisplay(`${secs}s`);
      else if (secs < 3600) setElapsedDisplay(`${Math.floor(secs / 60)}m ${secs % 60}s`);
      else setElapsedDisplay(`${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`);
    }, 1000);
    return () => clearInterval(tick);
  }, [isTerminal, startTime]);

  /* ── Stage timing extraction from WebSocket events ── */
  const stageTimings = useMemo(() => {
    const starts: Record<string, string> = {};
    const timings: { stage: string; started: string; duration: number }[] = [];
    for (const ev of allEvents) {
      const stage = (ev.stage ?? ev.state ?? "").toUpperCase();
      const status = (ev.status ?? "").toLowerCase();
      if (!stage || stage === "COMPLETED" || stage === "FAILED") continue;
      if (status === "started" && ev.timestamp) {
        starts[stage] = ev.timestamp;
      } else if ((status === "completed" || status === "failed") && starts[stage] && ev.timestamp) {
        const ms = new Date(ev.timestamp).getTime() - new Date(starts[stage]).getTime();
        timings.push({ stage, started: starts[stage], duration: Math.max(0, ms / 1000) });
      }
    }
    return timings;
  }, [allEvents]);

  /* ── WebSocket events ── */
  const handleMessage = useCallback((event: StreamEvent) => {
    setAllEvents((prev) => [...prev, event]);
    const stage = (event.stage ?? event.state ?? "").toUpperCase();
    if (
      stage === "COMPLETED" ||
      stage === "FAILED"
    ) {
      markTerminal();
    }
  }, [markTerminal]);

  const { connectionState } = useWebSocket(migrationId, {
    onMessage: handleMessage,
  });

  // Fetch existing logs on load or whenever the connection opens
  useEffect(() => {
    if (connectionState !== "open") return;

    async function fetchExistingLogs() {
      try {
        const logs = await getCompilerLogs(migrationId);
        // Map logs to StreamEvent-like objects
        const events: StreamEvent[] = logs.map((log: any) => ({
          type: "compiler_log",
          timestamp: log.timestamp,
          level: log.level,
          content: log.content,
        }));

        setAllEvents((prev) => {
          // Keep all non-compiler_log events
          const nonLogEvents = prev.filter((e) => e.type !== "compiler_log");
          // Merge compiler logs
          return [...events, ...nonLogEvents];
        });
      } catch (err) {
        console.error("Failed to fetch compiler logs:", err);
      }
    }
    void fetchExistingLogs();
  }, [migrationId, connectionState]);

  const downloadUrl = getDownloadUrl(migrationId);

  const handleDownload = async (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    try {
      const response = await fetch(downloadUrl);
      if (!response.ok) throw new Error("Download failed");
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `hipforge-${migrationId}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Failed to download package:", err);
      window.open(downloadUrl, "_blank");
    }
  };

  /* ── Status badge colour ── */
  const statusColor =
    migrationStatus === "COMPLETED"
      ? "text-emerald-600 border-emerald-600/30 bg-emerald-50 dark:text-emerald-400 dark:border-emerald-500/20 dark:bg-emerald-950/20"
      : migrationStatus === "FAILED"
        ? "text-red-700 border-red-700/30 bg-red-50 dark:text-red-400 dark:border-red-500/20 dark:bg-red-950/20"
        : migrationStatus === "RUNNING"
          ? "text-[#D4AF37] border-[#D4AF37]/30 bg-themeBgSecondary/30"
          : "text-themeTextMuted border-themeBorder bg-themeBgSecondary/20";

  return (
    <div
      className="mx-auto w-full max-w-[1600px] px-8 py-16 lg:px-16"
      style={{ backgroundColor: "var(--bg-primary)" }}
    >
      {/* Back navigation */}
      <Link
        href="/upload"
        className="group mb-12 inline-flex items-center gap-2 text-[10px] font-medium tracking-[0.25em] uppercase transition-colors duration-500"
        style={{ color: "var(--text-muted)" }}
      >
        <ArrowLeft
          className="h-3 w-3 transition-transform duration-500 group-hover:-translate-x-1"
          strokeWidth={1.5}
          aria-hidden="true"
        />
        New Migration
      </Link>

      {/* ── Editorial Page Header ── */}
      <div className="mb-12 pb-10" style={{ borderBottom: "1px solid var(--border-primary)" }}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="mb-4 flex items-center gap-3">
              <div className="h-px w-8" style={{ backgroundColor: "rgba(26,26,26,0.3)" }} aria-hidden="true" />
              <span className="text-[10px] font-medium tracking-[0.3em] uppercase" style={{ color: "var(--text-muted)" }}>
                Step 03 of 03
              </span>
            </div>
            <h1
              className="font-serif text-4xl font-normal lg:text-5xl"
              style={{ fontFamily: "'Playfair Display', Georgia, serif", color: "var(--text-primary)" }}
            >
              Migration{" "}
              <em style={{ color: "#D4AF37" }}>Dashboard</em>
            </h1>

            {/* Migration ID + live status badges */}
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2">
                <span className="text-[10px] tracking-[0.2em] uppercase" style={{ color: "var(--text-muted)" }}>
                  Job ID:
                </span>
                <code
                  className="px-2 py-0.5 font-mono text-xs"
                  style={{
                    fontFamily: "'JetBrains Mono', monospace",
                    border: "1px solid var(--border-primary)",
                    backgroundColor: "var(--bg-secondary)",
                    color: "var(--text-primary)",
                  }}
                >
                  {migrationId}
                </code>
              </div>

              {/* Live status pill */}
              <span
                className={`inline-flex items-center gap-1.5 border px-2.5 py-0.5 text-[10px] font-medium tracking-[0.1em] uppercase ${statusColor}`}
              >
                {!isTerminal && migrationStatus === "RUNNING" && (
                  <RefreshCw className="h-2.5 w-2.5 animate-spin" strokeWidth={1.5} aria-hidden="true" />
                )}
                {migrationStatus || "QUEUED"}
                {migrationStage && migrationStage !== migrationStatus && ` — ${migrationStage}`}
              </span>

              {/* Stop Migration Button */}
              {!isTerminal && (
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/migrate/${migrationId}/cancel`, {
                        method: "POST"
                      });
                      setMigrationStatus("FAILED");
                      setIsTerminal(true);
                    } catch (err) {
                      console.error("Failed to cancel migration:", err);
                    }
                  }}
                  className="inline-flex items-center gap-1 border border-red-700/30 bg-red-500/5 px-2.5 py-0.5 text-[10px] font-medium tracking-[0.1em] uppercase text-red-700 hover:bg-red-500/20 dark:text-red-400 dark:border-red-500/20 transition-all duration-300 cursor-pointer"
                >
                  Stop Migration
                </button>
              )}

              {/* Last updated */}
              {lastUpdated && (
                <span className="text-[10px] tracking-[0.1em]" style={{ color: "var(--text-muted)", opacity: 0.6 }}>
                  Updated {lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </span>
              )}
            </div>

              {/* Elapsed time counter */}
              {!isTerminal && (
                <span className="inline-flex items-center gap-1.5 border border-themeBorder px-2.5 py-0.5 text-[10px] font-medium tracking-[0.1em] uppercase text-themeTextMuted">
                  <Timer className="h-2.5 w-2.5 animate-spin" strokeWidth={1.5} aria-hidden="true" style={{ animationDuration: "3s" }} />
                  {elapsedDisplay}
                </span>
              )}
          </div>

          {/* Download button */}
          {isTerminal ? (
            <a
              id="dashboard-download-button"
              href={downloadUrl}
              onClick={handleDownload}
              download={`hipforge-${migrationId}.zip`}
              aria-label="Download migration ZIP package"
              className="btn-primary shrink-0"
            >
              <Download className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
              <span>Download ZIP</span>
            </a>
          ) : (
            <div className="flex shrink-0 flex-col items-end gap-1">
              <button
                type="button"
                disabled
                aria-disabled="true"
                aria-label="Download available after migration completes"
                className="flex shrink-0 cursor-not-allowed items-center gap-2 px-6 py-3 text-[10px] font-medium tracking-[0.2em] uppercase opacity-40"
                style={{ border: "1px solid var(--border-primary)", color: "var(--text-muted)" }}
              >
                <Download className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
                Download ZIP
              </button>
              <p className="text-[9px] tracking-[0.1em]" style={{ color: "var(--text-muted)", opacity: 0.6 }}>
                Available when migration completes
              </p>
            </div>
          )}
        </div>
      </div>

      {/* ── Dashboard Sections — top-border-only editorial pattern ── */}
      <div className="space-y-12">

        {/* Panel 1: Live Progress Timeline */}
        <section aria-labelledby="timeline-heading">
          <div className="mb-6 pt-6" style={{ borderTop: "1px solid var(--border-primary)" }}>
            <h2
              id="timeline-heading"
              className="text-[10px] font-medium tracking-[0.3em] uppercase"
              style={{ color: "var(--text-muted)" }}
            >
              Live Progress
            </h2>
          </div>
          <Timeline migrationId={migrationId} events={allEvents} />

          {/* Stage timing breakdown — shown when we have timing data */}
          {stageTimings.length > 0 && (
            <div className="mt-4 border border-themeBorder bg-themeCard">
              <div className="flex items-center gap-3 border-b border-themeBorder px-4 py-3">
                <Clock className="h-3.5 w-3.5 text-themeTextMuted" strokeWidth={1.5} aria-hidden="true" />
                <span className="text-[10px] font-medium tracking-[0.25em] uppercase text-themeTextMuted">
                  Stage Timings
                </span>
              </div>
              <div className="grid grid-cols-2 gap-x-8 gap-y-2 p-4 sm:grid-cols-3 lg:grid-cols-4">
                {stageTimings.map((t) => (
                  <div key={t.stage} className="flex items-baseline justify-between gap-2">
                    <span className="text-[10px] font-medium tracking-[0.15em] uppercase text-themeTextMuted">
                      {t.stage}
                    </span>
                    <span
                      className="font-mono text-xs"
                      style={{ fontFamily: "'JetBrains Mono', monospace", color: "var(--text-primary)" }}
                    >
                      {t.duration < 60 ? `${t.duration.toFixed(1)}s` : `${Math.floor(t.duration / 60)}m ${(t.duration % 60).toFixed(0)}s`}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        <div className="h-px" style={{ backgroundColor: "var(--border-primary)" }} aria-hidden="true" />

        {/* Panel 2: Compiler Log Stream */}
        <section aria-labelledby="compiler-log-heading">
          <div className="mb-6 pt-6" style={{ borderTop: "1px solid var(--border-primary)" }}>
            <h2
              id="compiler-log-heading"
              className="text-[10px] font-medium tracking-[0.3em] uppercase"
              style={{ color: "var(--text-muted)" }}
            >
              Compiler Output
            </h2>
          </div>
          <CompilerLog events={allEvents} />
        </section>

        <div className="h-px" style={{ backgroundColor: "var(--border-primary)" }} aria-hidden="true" />

        {/* Panel 3: Migration Journal */}
        <section aria-labelledby="journal-heading">
          <div className="mb-6 pt-6" style={{ borderTop: "1px solid var(--border-primary)" }}>
            <h2
              id="journal-heading"
              className="text-[10px] font-medium tracking-[0.3em] uppercase"
              style={{ color: "var(--text-muted)" }}
            >
              Migration Journal
            </h2>
          </div>
          {/* isActive=true until terminal so it polls every 4s */}
          <JournalViewer migrationId={migrationId} isActive={!isTerminal} />
        </section>

        <div className="h-px" style={{ backgroundColor: "var(--border-primary)" }} aria-hidden="true" />

        {/* Panel 4: Report Viewer */}
        <section aria-labelledby="report-heading">
          <div className="mb-6 pt-6" style={{ borderTop: "1px solid var(--border-primary)" }}>
            <h2
              id="report-heading"
              className="text-[10px] font-medium tracking-[0.3em] uppercase"
              style={{ color: "var(--text-muted)" }}
            >
              Report &amp; Download
            </h2>
          </div>
          {/* Pass isActive so ReportViewer also polls until done */}
          <ReportViewer migrationId={migrationId} isActive={!isTerminal} />
        </section>
      </div>
    </div>
  );
}
