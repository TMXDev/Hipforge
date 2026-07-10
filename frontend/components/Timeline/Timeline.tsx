"use client";

import { useMemo, useCallback, useState, useEffect } from "react";
import { Wifi, WifiOff, AlertTriangle } from "lucide-react";
import TimelineItem from "./TimelineItem";
import { STAGE_META, type JobState, type StageState } from "./types";
import { useWebSocket, type StreamEvent } from "@/hooks/useWebSocket";
import { getJournal, getMigrationStatus } from "@/services/api";

interface TimelineProps {
  /** The migration UUID being tracked */
  migrationId: string;
  events?: StreamEvent[];
}

/** Builds the initial pending stage map */
function buildInitialStages(): Map<JobState, StageState> {
  const map = new Map<JobState, StageState>();
  for (const meta of STAGE_META) {
    map.set(meta.state, {
      state: meta.state,
      status: "pending",
      message: "",
      timestamp: null,
    });
  }
  return map;
}

/**
 * Derives the canonical JobState from an event, accepting both
 * `stage` (WebSocket events format) and `state` (lifecycle payload format).
 */
function resolveStage(event: StreamEvent): JobState | null {
  const raw = (event.stage ?? event.state ?? "").toUpperCase() as JobState;
  const valid = STAGE_META.map((m) => m.state);
  // FAILED maps to the COMPLETED slot with failed status
  if (raw === "FAILED") return "COMPLETED";
  if (valid.includes(raw)) return raw;
  return null;
}

/**
 * Timeline — Live 10-state vertical progress display with luxury editorial styling.
 *
 * Subscribes to the migration WebSocket stream and updates each stage's
 * status in real time: pending → active (started) → completed or failed.
 * Automatically reconnects if the connection drops.
 */
export default function Timeline({ migrationId, events = [] }: TimelineProps) {
  const [stages, setStages] = useState<Map<JobState, StageState>>(
    buildInitialStages
  );
  const [isFailed, setIsFailed] = useState(false);

  useEffect(() => {
    let active = true;

    async function loadInitialState() {
      try {
        const [journalData, statusData] = await Promise.all([
          getJournal(migrationId),
          getMigrationStatus(migrationId).catch(() => null)
        ]);

        if (!active) return;

        const initial = buildInitialStages();
        let failed = false;

        // 1. Replay journal entries
        if (journalData && Array.isArray(journalData)) {
          for (const entry of journalData) {
            const rawState = (entry.workflow_state || "").toUpperCase() as JobState;
            const targetState = rawState === "FAILED" ? "COMPLETED" : rawState;
            if (rawState === "FAILED") {
              failed = true;
            }

            const current = initial.get(targetState);
            if (current) {
              let status: StageState["status"] = "completed";
              if (rawState === "FAILED") {
                status = "failed";
              }

              let message = entry.analysis_summary || entry.patch_summary || entry.research_summary || "";
              if (rawState === "COMPILING") {
                message = (entry.compiler_result === "SUCCESS" || entry.compiler_result === "PASSED")
                  ? "Compilation succeeded."
                  : "Compilation failed.";
              }

              initial.set(targetState, {
                state: targetState,
                status,
                message: message || current.message,
                timestamp: entry.timestamp,
              });
            }
          }
        }

        // 2. Apply deterministic status propagation from statusData
        if (statusData) {
          const currentStatus = (statusData.status || "").toUpperCase();
          const currentStage = (statusData.stage || "").toUpperCase() as JobState;

          const repairStatus = (statusData.ai_repair_status || "").toLowerCase();
          const hasAiRepair = repairStatus === "succeeded" || repairStatus === "failed" || (statusData.compilation_history && statusData.compilation_history.length > 1);

          const orderedStages = STAGE_META.map(m => m.state);
          let targetIndex = orderedStages.indexOf(currentStage);
          if (targetIndex === -1) {
            targetIndex = orderedStages.indexOf("COMPLETED");
          }

          if (currentStatus === "FAILED") {
            failed = true;
          }

          for (const meta of STAGE_META) {
            const stateKey = meta.state;
            const current = initial.get(stateKey);
            if (!current) continue;

            const currentIndex = orderedStages.indexOf(stateKey);

            // Handle AI repair conditional stages
            if (stateKey === "ANALYZING" || stateKey === "PATCHING") {
              if (!hasAiRepair) {
                initial.set(stateKey, { ...current, status: "skipped" });
                continue;
              }
            }

            if (currentStatus === "COMPLETED") {
              initial.set(stateKey, { ...current, status: "completed" });
            } else if (currentStatus === "FAILED") {
              if (stateKey === currentStage) {
                initial.set(stateKey, { ...current, status: "failed" });
              } else if (currentIndex < targetIndex) {
                initial.set(stateKey, { ...current, status: "completed" });
              } else {
                initial.set(stateKey, { ...current, status: "skipped" });
              }
            } else {
              // RUNNING or QUEUED
              if (stateKey === currentStage) {
                initial.set(stateKey, { ...current, status: "active" });
              } else if (currentIndex < targetIndex) {
                initial.set(stateKey, { ...current, status: "completed" });
              } else {
                initial.set(stateKey, { ...current, status: "pending" });
              }
            }
          }
        }

        setIsFailed(failed);
        setStages(initial);
      } catch (err) {
        console.error("Failed to load initial timeline state:", err);
      }
    }

    loadInitialState();
    return () => {
      active = false;
    };
  }, [migrationId]);

  const handleMessage = useCallback((event: StreamEvent) => {
    const targetState = resolveStage(event);
    if (!targetState) return;

    const status = event.status ?? event.action ?? "";
    const message =
      event.message ??
      event.details ??
      event.summary ??
      event.content ??
      "";
    const timestamp = event.timestamp ?? new Date().toISOString();
    const eventIsFailed =
      (event.stage ?? event.state ?? "").toUpperCase() === "FAILED";

    setIsFailed((prev) => prev || eventIsFailed);

    setStages((prev) => {
      const next = new Map(prev);
      const current = next.get(targetState);
      if (!current) return prev;

      let newStatus: StageState["status"] = current.status;

      if (status === "started" || status === "in_progress") {
        newStatus = "active";
      } else if (status === "completed") {
        newStatus = eventIsFailed ? "failed" : "completed";
      } else if (status === "failed") {
        newStatus = "failed";
      }

      next.set(targetState, {
        ...current,
        status: newStatus,
        message: message || current.message,
        timestamp,
      });
      return next;
    });
  }, []);

  const { connectionState } = useWebSocket(migrationId, {
    onMessage: handleMessage,
  });

  const stageList = useMemo(() => {
    let hasAnalyzing = false;
    let hasPatching = false;

    // Check if stages are not pending or skipped
    const analyzingStage = stages.get("ANALYZING");
    if (analyzingStage && analyzingStage.status !== "pending" && analyzingStage.status !== "skipped") {
      hasAnalyzing = true;
    }
    const patchingStage = stages.get("PATCHING");
    if (patchingStage && patchingStage.status !== "pending" && patchingStage.status !== "skipped") {
      hasPatching = true;
    }

    // Check events
    for (const ev of events) {
      const st = (ev.stage ?? ev.state ?? "").toUpperCase();
      if (st === "ANALYZING") hasAnalyzing = true;
      if (st === "PATCHING") hasPatching = true;
    }

    return STAGE_META.filter((meta) => {
      if (meta.state === "ANALYZING") return hasAnalyzing;
      if (meta.state === "PATCHING") return hasPatching;
      return true;
    });
  }, [stages, events]);

  const isCompletedDone = stages.get("COMPLETED")?.status === "completed" || stages.get("COMPLETED")?.status === "failed";
  const isWorkflowTerminal = isFailed || isCompletedDone;

  return (
    <div className="w-full">
      {/* Connection status — luxury rectangular badge */}
      {!isWorkflowTerminal && <ConnectionBadge state={connectionState} />}

      {/* Terminal state banner — architectural left border */}
      {isFailed && (
        <div
          role="alert"
          className="mb-8 flex items-center gap-3 border-l-2 border-red-500/30 bg-red-500/5 px-4 py-3"
        >
          <AlertTriangle
            className="h-4 w-4 shrink-0 text-red-600"
            strokeWidth={1.5}
            aria-hidden="true"
          />
          <p className="text-sm text-red-700 dark:text-red-400">
            Migration failed. Check the stage details below for the error.
          </p>
        </div>
      )}

      {/* Timeline items */}
      <div role="list" aria-label="Migration progress timeline">
        {stageList.map((meta, index) => {
          const stage = stages.get(meta.state) ?? {
            state: meta.state,
            status: "pending" as const,
            message: "",
            timestamp: null,
          };
          let displayStage: StageState = stage;
          if (meta.state === "COMPLETED" && isFailed) {
            displayStage = { ...stage, status: stage.status === "pending" ? "pending" : "failed", state: "FAILED" as JobState };
          } else if (isWorkflowTerminal && stage.status === "pending") {
            displayStage = { ...stage, status: "skipped" };
          }

          return (
            <div key={meta.state} role="listitem">
              <TimelineItem
                meta={meta}
                stage={displayStage}
                isLast={index === stageList.length - 1}
                events={events}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Connection state pill shown above the timeline — luxury rectangular style */
function ConnectionBadge({
  state,
}: {
  state: "connecting" | "open" | "closed" | "error";
}) {
  if (state === "open") return null;

  const configs = {
    connecting: {
      icon: Wifi,
      label: "Connecting to live stream…",
      classes: "border-themeBorder bg-themeBgSecondary/30 text-themeTextMuted",
    },
    closed: {
      icon: WifiOff,
      label: "Connection lost. Reconnecting…",
      classes: "border-amber-500/20 bg-amber-500/5 text-amber-700 dark:text-amber-400",
    },
    error: {
      icon: WifiOff,
      label: "Stream error. Retrying…",
      classes: "border-red-500/20 bg-red-500/5 text-red-700 dark:text-red-400",
    },
  };

  const cfg = configs[state];
  const Icon = cfg.icon;

  return (
    <div
      className={`mb-6 flex items-center gap-2 border px-4 py-2.5 ${cfg.classes}`}
      role="status"
      aria-live="polite"
    >
      <Icon className="h-3.5 w-3.5 shrink-0" strokeWidth={1.5} aria-hidden="true" />
      <span className="text-[10px] font-medium tracking-[0.2em] uppercase">
        {cfg.label}
      </span>
    </div>
  );
}
