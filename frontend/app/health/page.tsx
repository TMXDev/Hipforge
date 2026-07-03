"use client";

import { useEffect, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, Play, RefreshCw, XCircle } from "lucide-react";

import { getHealthCheck, runSelfTest } from "@/services/api";
import type { DiagnosticCheck, HealthReport, SelfTestReport } from "@/types/migration";

const statusTone: Record<string, string> = {
  pass: "text-emerald-600",
  warn: "text-amber-600",
  fail: "text-red-600",
  skip: "text-themeTextMuted",
};

function StatusIcon({ status }: { status: string }) {
  const className = `h-4 w-4 ${statusTone[status] ?? "text-themeTextMuted"}`;
  if (status === "pass") return <CheckCircle2 className={className} strokeWidth={1.7} aria-hidden="true" />;
  if (status === "fail") return <XCircle className={className} strokeWidth={1.7} aria-hidden="true" />;
  if (status === "warn") return <AlertTriangle className={className} strokeWidth={1.7} aria-hidden="true" />;
  return <Activity className={className} strokeWidth={1.7} aria-hidden="true" />;
}

function CheckRow({ check }: { check: DiagnosticCheck }) {
  return (
    <tr className="border-t border-themeBorder">
      <td className="w-12 px-4 py-3 align-top">
        <StatusIcon status={check.status} />
      </td>
      <td className="px-4 py-3 align-top">
        <div className="text-sm font-medium text-themeText">{check.name}</div>
        <div className="mt-1 text-xs leading-5 text-themeTextMuted">{check.message}</div>
      </td>
      <td className="px-4 py-3 align-top">
        <span className="font-mono text-xs uppercase text-themeTextMuted">{check.category}</span>
      </td>
      <td className="px-4 py-3 align-top">
        <span className="font-mono text-xs uppercase text-themeTextMuted">{check.status}</span>
      </td>
    </tr>
  );
}

export default function HealthPage() {
  const [report, setReport] = useState<HealthReport | null>(null);
  const [selfTest, setSelfTest] = useState<SelfTestReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHealth = async () => {
    setLoading(true);
    setError(null);
    try {
      setReport(await getHealthCheck());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Health check failed");
    } finally {
      setLoading(false);
    }
  };

  const startSelfTest = async () => {
    setTesting(true);
    setError(null);
    try {
      setSelfTest(await runSelfTest());
      await loadHealth();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Self-test failed");
    } finally {
      setTesting(false);
    }
  };

  useEffect(() => {
    loadHealth();
  }, []);

  return (
    <div className="flex flex-1 flex-col">
      <section className="border-b border-themeBorder px-8 py-12 lg:px-16">
        <div className="mx-auto max-w-[1600px]">
          <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="overline">Health Check</div>
              <h1 className="mt-3 font-serif text-4xl font-normal text-themeText lg:text-6xl">
                System Readiness
              </h1>
            </div>
            <div className="flex flex-wrap gap-3">
              <button type="button" className="btn-secondary" onClick={loadHealth} disabled={loading}>
                <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
                <span>{loading ? "Checking" : "Refresh"}</span>
              </button>
              <button type="button" className="btn-primary" onClick={startSelfTest} disabled={testing}>
                <Play className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
                <span>{testing ? "Running" : "Self Test"}</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      <section className="px-8 py-10 lg:px-16">
        <div className="mx-auto grid max-w-[1600px] grid-cols-1 gap-6 lg:grid-cols-4">
          <div className="border-t border-themeBorder pt-5">
            <div className="text-xs font-medium uppercase tracking-[0.2em] text-themeTextMuted">Score</div>
            <div className="mt-3 font-mono text-4xl text-themeText">{report?.health_score ?? "--"}</div>
          </div>
          <div className="border-t border-themeBorder pt-5">
            <div className="text-xs font-medium uppercase tracking-[0.2em] text-themeTextMuted">Readiness</div>
            <div className="mt-3 font-mono text-lg text-themeText">{report?.readiness ?? "UNKNOWN"}</div>
          </div>
          <div className="border-t border-themeBorder pt-5">
            <div className="text-xs font-medium uppercase tracking-[0.2em] text-themeTextMuted">Missing</div>
            <div className="mt-3 font-mono text-4xl text-themeText">{report?.missing_components?.length ?? 0}</div>
          </div>
          <div className="border-t border-themeBorder pt-5">
            <div className="text-xs font-medium uppercase tracking-[0.2em] text-themeTextMuted">Warnings</div>
            <div className="mt-3 font-mono text-4xl text-themeText">{report?.warnings?.length ?? 0}</div>
          </div>
        </div>
      </section>

      {error ? (
        <section className="px-8 pb-8 lg:px-16">
          <div className="mx-auto max-w-[1600px] border-l-2 border-red-600 pl-4 text-sm text-red-600">
            {error}
          </div>
        </section>
      ) : null}

      <section className="px-8 pb-12 lg:px-16">
        <div className="mx-auto max-w-[1600px] overflow-x-auto border-t border-themeBorder">
          <table className="min-w-full table-fixed text-left">
            <thead>
              <tr className="text-xs uppercase tracking-[0.2em] text-themeTextMuted">
                <th className="w-12 px-4 py-3"></th>
                <th className="px-4 py-3">Component</th>
                <th className="w-56 px-4 py-3">Category</th>
                <th className="w-32 px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {(report?.checks ?? []).map((check) => (
                <CheckRow key={check.id} check={check} />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-8 border-t border-themeBorder px-8 py-10 lg:grid-cols-2 lg:px-16">
        <div>
          <div className="overline">Recommended Fixes</div>
          <div className="mt-5 space-y-3 text-sm leading-6 text-themeTextMuted">
            {(report?.recommended_fixes ?? []).length > 0 ? (
              (report?.recommended_fixes ?? []).map((fix) => <div key={fix}>- {fix}</div>)
            ) : (
              <div>No fixes required.</div>
            )}
          </div>
        </div>
        <div>
          <div className="overline">Self Test</div>
          <div className="mt-5 space-y-3 text-sm leading-6 text-themeTextMuted">
            {selfTest ? (
              selfTest.steps.map((step) => (
                <div key={step.name} className="flex gap-3">
                  <StatusIcon status={step.success ? "pass" : "fail"} />
                  <span>{step.name}: {step.message}</span>
                </div>
              ))
            ) : (
              <div>Not run in this session.</div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
