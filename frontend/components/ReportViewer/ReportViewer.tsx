"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  FileText,
  RefreshCw,
  CheckCircle,
  XCircle,
  Download,
} from "lucide-react";
import { getMigrationStatus, getJournal, getDownloadUrl } from "@/services/api";
import type { MigrationStatus, JournalEntry } from "@/types/migration";

interface ReportViewerProps {
  migrationId: string;
  /** If true, auto-refresh every 5s (during active migration). Defaults to true. */
  isActive?: boolean;
}

/**
 * ReportViewer — Displays a structured migration summary report.
 *
 * Polls status + journal every 5s while isActive=true, then does a
 * final refresh when isActive transitions to false (migration complete).
 * This ensures the report is never stuck in a "loading" state.
 */
export default function ReportViewer({ migrationId, isActive = true }: ReportViewerProps) {
  const [status, setStatus] = useState<MigrationStatus | null>(null);
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const wasActiveRef = useRef(isActive);

  const fetchData = useCallback(async () => {
    try {
      const [s, j] = await Promise.all([
        getMigrationStatus(migrationId),
        getJournal(migrationId),
      ]);
      setStatus(s);
      setJournal(j);
      setError(null);
      setLastRefresh(new Date());
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to load report."
      );
    } finally {
      setLoading(false);
    }
  }, [migrationId]);

  // Initial fetch
  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  // Polling while isActive — every 5 seconds
  useEffect(() => {
    if (!isActive) return;
    const interval = setInterval(() => {
      void fetchData();
    }, 5_000);
    return () => clearInterval(interval);
  }, [isActive, fetchData]);

  // Final refresh when isActive transitions from true → false
  useEffect(() => {
    if (wasActiveRef.current && !isActive) {
      // Migration just completed — do a final definitive fetch
      setTimeout(() => void fetchData(), 500);
    }
    wasActiveRef.current = isActive;
  }, [isActive, fetchData]);

  if (loading) {
    return (
      <div className="flex items-center gap-3 py-6" style={{ color: "var(--text-muted)" }}>
        <RefreshCw className="h-4 w-4 animate-spin" strokeWidth={1.5} aria-hidden="true" />
        <span className="text-sm">Loading report…</span>
      </div>
    );
  }

  if (error) {
    return (
      <p
        role="alert"
        className="border-l-2 border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-700 dark:text-red-400"
      >
        {error}
      </p>
    );
  }

  // Derived metrics from journal
  const compilationAttempts = journal.filter(
    (e) => e.workflow_state === "COMPILING"
  ).length;
  const aiAnalyses = journal.filter(
    (e) => e.workflow_state === "ANALYZING"
  ).length;
  const patches = journal.filter(
    (e) => e.workflow_state === "PATCHING"
  ).length;
  const researches = journal.filter(
    (e) => e.workflow_state === "RESEARCHING"
  ).length;

  const statusStr = (status?.status || "").toUpperCase();
  const isCompleted = statusStr === "COMPLETED" || statusStr === "FAILED";
  const isSuccess = statusStr === "COMPLETED";

  const handleDownload = async (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    const downloadUrl = getDownloadUrl(migrationId);
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

  return (
    <div className="space-y-6">
      {/* Summary panel */}
      <div
        className="overflow-hidden"
        style={{ border: "1px solid var(--border-primary)", backgroundColor: "var(--bg-card)" }}
      >
        {/* Header */}
        <div
          className="flex items-center gap-3 px-5 py-4"
          style={{ borderBottom: "1px solid var(--border-primary)", backgroundColor: "var(--bg-secondary)" }}
        >
          <FileText className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" style={{ color: "var(--text-muted)" }} />
          <span
            className="text-[10px] font-medium tracking-[0.25em] uppercase"
            style={{ color: "var(--text-muted)" }}
          >
            Migration Report
          </span>

          {/* Live refresh indicator while active */}
          {isActive && (
            <span className="ml-2 flex items-center gap-1.5">
              <RefreshCw className="h-2.5 w-2.5 animate-spin text-[#D4AF37]" strokeWidth={1.5} aria-hidden="true" />
              <span className="text-[9px] tracking-[0.1em] text-[#D4AF37]">Live</span>
            </span>
          )}

          {/* Status badge */}
          {statusStr && (
            <span className="ml-auto">
              {isSuccess ? (
                <span className="inline-flex items-center gap-1.5 border border-emerald-600/20 bg-emerald-500/5 px-2.5 py-0.5 text-[10px] font-medium tracking-[0.1em] uppercase text-emerald-700 dark:text-emerald-400">
                  <CheckCircle className="h-3 w-3" strokeWidth={1.5} aria-hidden="true" />
                  Completed
                </span>
              ) : statusStr === "FAILED" ? (
                <span className="inline-flex items-center gap-1.5 border border-red-600/20 bg-red-500/5 px-2.5 py-0.5 text-[10px] font-medium tracking-[0.1em] uppercase text-red-700 dark:text-red-400">
                  <XCircle className="h-3 w-3" strokeWidth={1.5} aria-hidden="true" />
                  Failed
                </span>
              ) : (
                <span
                  className="inline-flex items-center gap-1.5 border px-2.5 py-0.5 text-[10px] font-medium tracking-[0.1em] uppercase"
                  style={{ borderColor: "var(--border-primary)", color: "var(--text-muted)" }}
                >
                  <RefreshCw className="h-3 w-3 animate-spin" strokeWidth={1.5} aria-hidden="true" />
                  {statusStr || "Running"}
                </span>
              )}
            </span>
          )}
        </div>

        {/* Migration metadata */}
        <div className="space-y-4 p-5">
          {/* ID */}
          <ReportRow label="Migration ID">
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
          </ReportRow>

          {/* Stage */}
          <ReportRow label="Current Stage">
            <span
              className="font-mono text-xs"
              style={{ fontFamily: "'JetBrains Mono', monospace", color: "var(--text-primary)" }}
            >
              {status?.stage ?? status?.current_stage ?? status?.status ?? "—"}
            </span>
          </ReportRow>

          {/* Separator */}
          <div className="h-px" style={{ backgroundColor: "var(--border-primary)" }} />

          {/* Activity metrics */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <MetricCell label="Compile Attempts" value={compilationAttempts} />
            <MetricCell label="AI Analyses" value={aiAnalyses} />
            <MetricCell label="Patches Applied" value={patches} />
            <MetricCell label="Research Queries" value={researches} />
          </div>

          {/* Journal count + last refresh */}
          <div className="flex items-center justify-between">
            {journal.length > 0 && (
              <p className="text-[10px] tracking-[0.1em]" style={{ color: "var(--text-muted)", opacity: 0.7 }}>
                {journal.length} journal {journal.length === 1 ? "entry" : "entries"} recorded.
                {!isCompleted && " Report updates automatically."}
              </p>
            )}
            {lastRefresh && (
              <p className="text-[9px] tracking-[0.1em]" style={{ color: "var(--text-muted)", opacity: 0.5 }}>
                Refreshed {lastRefresh.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Download CTA — only shown when completed */}
      {isCompleted && (
        <a
          id="report-download-zip-button"
          href={getDownloadUrl(migrationId)}
          onClick={handleDownload}
          download={`hipforge-${migrationId}.zip`}
          className="btn-primary w-full"
          aria-label="Download migration ZIP archive"
        >
          <Download className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
          <span>Download Full Report &amp; Source (ZIP)</span>
        </a>
      )}

      {/* Waiting message while running */}
      {!isCompleted && (
        <p
          className="py-2 text-center text-[10px] tracking-[0.15em] uppercase"
          style={{ color: "var(--text-muted)", opacity: 0.7 }}
        >
          Download will be available when migration completes
        </p>
      )}
    </div>
  );
}

/** Single label + value row in the report panel */
function ReportRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span
        className="text-[10px] font-medium tracking-[0.2em] uppercase"
        style={{ color: "var(--text-muted)" }}
      >
        {label}
      </span>
      <div className="text-right">{children}</div>
    </div>
  );
}

/** Metric count cell — editorial stat display with Playfair numerals */
function MetricCell({ label, value }: { label: string; value: number }) {
  return (
    <div
      className="px-3 py-4 text-center"
      style={{ border: "1px solid var(--border-primary)", backgroundColor: "var(--bg-secondary)" }}
    >
      <p
        className="font-serif text-3xl font-normal"
        style={{ fontFamily: "'Playfair Display', Georgia, serif", color: "var(--text-primary)" }}
      >
        {value}
      </p>
      <p
        className="mt-1 text-[10px] tracking-[0.15em] uppercase"
        style={{ color: "var(--text-muted)" }}
      >
        {label}
      </p>
    </div>
  );
}
