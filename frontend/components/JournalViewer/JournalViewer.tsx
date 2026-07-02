"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { BookOpen, RefreshCw, CheckCircle, XCircle, Minus } from "lucide-react";
import { getJournal } from "@/services/api";
import type { JournalEntry } from "@/types/migration";

interface JournalViewerProps {
  migrationId: string;
  /** If true, auto-refresh every 4s (during active migration) */
  isActive?: boolean;
}

/** Compiler result badge — luxury rectangular style */
function CompilerBadge({ result }: { result: string }) {
  if (result === "SUCCESS")
    return (
      <span className="inline-flex items-center gap-1.5 border border-emerald-600/30 bg-emerald-50 px-2.5 py-0.5 text-[10px] font-medium tracking-[0.1em] uppercase text-emerald-700">
        <CheckCircle className="h-3 w-3" strokeWidth={1.5} aria-hidden="true" />
        Success
      </span>
    );
  if (result === "FAILED")
    return (
      <span className="inline-flex items-center gap-1.5 border border-red-600/30 bg-red-50 px-2.5 py-0.5 text-[10px] font-medium tracking-[0.1em] uppercase text-red-700">
        <XCircle className="h-3 w-3" strokeWidth={1.5} aria-hidden="true" />
        Failed
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1.5 border border-[#1A1A1A]/10 bg-[#EBE5DE]/40 px-2.5 py-0.5 text-[10px] font-medium tracking-[0.1em] uppercase text-[#6C6863]">
      <Minus className="h-3 w-3" strokeWidth={1.5} aria-hidden="true" />
      {result}
    </span>
  );
}

/**
 * JournalViewer — Displays the migration journal entries in luxury editorial style.
 *
 * Fetches GET /api/v1/migrate/{id}/journal on mount and optionally
 * refreshes every 10 seconds while the migration is active.
 */
export default function JournalViewer({
  migrationId,
  isActive = false,
}: JournalViewerProps) {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const wasActiveRef = useRef(isActive);

  const fetchJournal = useCallback(async () => {
    try {
      const data = await getJournal(migrationId);
      setEntries(data);
      setError(null);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to load journal."
      );
    } finally {
      setLoading(false);
    }
  }, [migrationId]);

  // Initial fetch
  useEffect(() => {
    void fetchJournal();
  }, [fetchJournal]);

  // Poll every 4s while migration is active
  useEffect(() => {
    if (!isActive) return;
    const interval = setInterval(() => {
      void fetchJournal();
    }, 4_000);
    return () => clearInterval(interval);
  }, [isActive, fetchJournal]);

  // Final refresh when isActive transitions true → false
  useEffect(() => {
    if (wasActiveRef.current && !isActive) {
      setTimeout(() => void fetchJournal(), 600);
    }
    wasActiveRef.current = isActive;
  }, [isActive, fetchJournal]);

  if (loading) {
    return (
      <div className="flex items-center gap-3 py-6" style={{ color: "var(--text-muted)" }}>
        <RefreshCw className="h-4 w-4 animate-spin" strokeWidth={1.5} aria-hidden="true" />
        <span className="text-sm">Loading journal…</span>
      </div>
    );
  }

  if (error) {
    return (
      <p role="alert" className="border-l-2 border-red-700 bg-red-50 px-4 py-3 text-sm text-red-700">
        {error}
      </p>
    );
  }

  if (entries.length === 0) {
    return (
      <p className="py-4 text-sm italic text-[#6C6863]/60">
        No journal entries yet. The journal updates as each workflow state completes.
      </p>
    );
  }

  // Group entries by attempt number for display
  const attempts = new Map<number, JournalEntry[]>();
  for (const entry of entries) {
    const group = attempts.get(entry.attempt) ?? [];
    group.push(entry);
    attempts.set(entry.attempt, group);
  }

  return (
    <div className="space-y-4">
      {/* Refresh button + count */}
      <div className="flex items-center justify-between">
        <span className="text-[10px] tracking-[0.15em] uppercase text-[#6C6863]/60">
          {entries.length} {entries.length === 1 ? "entry" : "entries"}
        </span>
        <button
          type="button"
          id="journal-refresh-button"
          onClick={() => void fetchJournal()}
          aria-label="Refresh journal"
          className="flex items-center gap-1.5 border border-[#1A1A1A]/15 px-3 py-1.5 text-[10px] font-medium tracking-[0.15em] uppercase text-[#6C6863] transition-colors duration-500 hover:border-[#1A1A1A]/30 hover:text-[#1A1A1A]"
        >
          <RefreshCw className="h-3 w-3" strokeWidth={1.5} aria-hidden="true" />
          Refresh
        </button>
      </div>

      {/* Entries */}
      {Array.from(attempts.entries()).map(([attempt, group]) => (
        <div
          key={attempt}
          className="border border-[#1A1A1A]/10 bg-[#F9F8F6] overflow-hidden"
        >
          {/* Attempt header */}
          <div className="flex items-center gap-3 border-b border-[#1A1A1A]/8 bg-[#EBE5DE]/40 px-5 py-3">
            <BookOpen className="h-3.5 w-3.5 text-[#6C6863]" strokeWidth={1.5} aria-hidden="true" />
            <span className="text-[10px] font-medium tracking-[0.25em] uppercase text-[#6C6863]">
              Attempt {attempt}
            </span>
          </div>

          {/* Entries within this attempt */}
          <div className="divide-y divide-[#1A1A1A]/8">
            {group.map((entry, idx) => (
              <div key={idx} className="space-y-2 px-5 py-4">
                {/* State + compiler result + timestamp */}
                <div className="flex flex-wrap items-center gap-3">
                  <span className="font-mono text-xs text-[#1A1A1A] font-medium"
                    style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                    {entry.workflow_state}
                  </span>
                  <CompilerBadge result={entry.compiler_result} />
                  <time
                    dateTime={entry.timestamp}
                    className="ml-auto text-[10px] tracking-[0.1em] text-[#6C6863]/60"
                  >
                    {new Date(entry.timestamp).toLocaleTimeString()}
                  </time>
                </div>

                {/* Analysis summary */}
                {entry.analysis_summary && (
                  <p className="text-xs leading-relaxed text-[#6C6863]">
                    <span className="font-medium text-[#1A1A1A]/60">Analysis: </span>
                    {entry.analysis_summary}
                  </p>
                )}

                {/* Patch summary */}
                {entry.patch_summary && (
                  <p className="text-xs leading-relaxed text-[#6C6863]">
                    <span className="font-medium text-[#1A1A1A]/60">Patch: </span>
                    {entry.patch_summary}
                  </p>
                )}

                {/* Research summary */}
                {entry.research_summary && (
                  <p className="text-xs leading-relaxed text-[#6C6863]">
                    <span className="font-medium text-[#1A1A1A]/60">Research: </span>
                    {entry.research_summary}
                  </p>
                )}

                {/* Files modified */}
                {entry.files_modified.length > 0 && (
                  <p className="font-mono text-xs text-[#6C6863]/50"
                    style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                    Modified: {entry.files_modified.join(", ")}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
