"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, RefreshCw } from "lucide-react";
import { getMigrationHistory } from "@/services/api";
import type { MigrationHistoryEntry } from "@/types/migration";

export default function HistoryPage() {
  const [history, setHistory] = useState<MigrationHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMigrationHistory();
      setHistory(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load migration history");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  const formatDate = (dateStr: string) => {
    if (!dateStr) return "N/A";
    try {
      const date = new Date(dateStr);
      return date.toLocaleString();
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="flex flex-1 flex-col">
      {/* Header section */}
      <section className="border-b border-themeBorder px-8 py-12 lg:px-16">
        <div className="mx-auto max-w-[1600px]">
          <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="overline">Archive</div>
              <h1 className="mt-3 font-serif text-4xl font-normal text-themeText lg:text-6xl" style={{ fontFamily: "'Playfair Display', Georgia, serif" }}>
                Migration History
              </h1>
            </div>
            <div>
              <button
                type="button"
                className="btn-secondary"
                onClick={loadHistory}
                disabled={loading}
              >
                <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} strokeWidth={1.5} aria-hidden="true" />
                <span>{loading ? "Loading" : "Refresh"}</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Main Content */}
      <section className="px-8 py-12 lg:px-16 flex-1">
        <div className="mx-auto max-w-[1600px]">
          {error && (
            <div className="mb-6 border border-red-200 bg-red-50/50 p-4 text-sm text-red-800 dark:border-red-950/50 dark:bg-red-950/20 dark:text-red-300">
              {error}
            </div>
          )}

          {loading ? (
            <div className="flex py-20 items-center justify-center text-themeTextMuted">
              <RefreshCw className="h-6 w-6 animate-spin mr-3" strokeWidth={1.5} />
              <span>Loading previous migrations...</span>
            </div>
          ) : history.length === 0 ? (
            <div className="border border-dashed border-themeBorder py-20 text-center">
              <span className="overline text-themeTextMuted">No history found</span>
              <p className="mt-2 text-sm text-themeTextMuted">You haven't run any CUDA migrations yet.</p>
              <div className="mt-6">
                <Link href="/upload" className="btn-primary inline-flex">
                  <span>Start a Migration</span>
                  <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
                </Link>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="border-b border-themeBorder text-[10px] font-medium tracking-[0.2em] uppercase text-themeTextMuted">
                    <th className="px-4 py-4 font-medium">Job ID</th>
                    <th className="px-4 py-4 font-medium">Input File</th>
                    <th className="px-4 py-4 font-medium">Target GPU</th>
                    <th className="px-4 py-4 font-medium">Finished At</th>
                    <th className="px-4 py-4 font-medium">State</th>
                    <th className="px-4 py-4 font-medium text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-themeBorder">
                  {history.map((entry) => (
                    <tr key={entry.job_id} className="hover:bg-themeDarkSection/5 transition-colors duration-200">
                      <td className="px-4 py-4 font-mono text-xs text-themeText select-all">
                        {entry.job_id}
                      </td>
                      <td className="px-4 py-4 text-sm font-medium text-themeText">
                        {entry.input_name || "Unknown File"}
                      </td>
                      <td className="px-4 py-4 text-sm font-mono text-themeTextMuted">
                        {entry.target_architecture}
                      </td>
                      <td className="px-4 py-4 text-xs text-themeTextMuted">
                        {formatDate(entry.finished_at)}
                      </td>
                      <td className="px-4 py-4">
                        <div className="inline-flex items-center gap-1.5 px-2 py-1 text-xs border border-themeBorder">
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              entry.final_state === "COMPLETED" || entry.final_state === "SUCCESS"
                                ? "bg-emerald-500"
                                : entry.final_state === "FAILED" || entry.final_state === "ERROR"
                                ? "bg-rose-500"
                                : "bg-amber-500 animate-pulse"
                            }`}
                          />
                          <span className="font-mono text-[10px] font-medium uppercase text-themeText">
                            {entry.final_state}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-4 text-right">
                        <Link
                          href={`/migration/${entry.job_id}`}
                          className="btn-secondary inline-flex py-1 px-3"
                        >
                          <span>Dashboard</span>
                          <ArrowRight className="h-3 w-3 ml-1" strokeWidth={1.5} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
