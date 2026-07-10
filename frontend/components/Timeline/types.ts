/**
 * Shared types for the HIPForge Timeline component.
 * State ordering and metadata are derived from docs/26_JOB_LIFECYCLE.md.
 */

/** All canonical job state values as defined in 26_JOB_LIFECYCLE.md */
export type JobState =
  | "QUEUED"
  | "PREPARING"
  | "PREFLIGHT"
  | "HIPIFY"
  | "SCA"
  | "COMPILING"
  | "ANALYZING"
  | "PATCHING"
  | "RESEARCHING"
  | "GENERATING_REPORT"
  | "COMPLETED"
  | "FAILED";

/** Per-stage status driven by WebSocket events */
export type StageStatus = "pending" | "active" | "completed" | "failed" | "skipped";

/** Runtime state for a single timeline stage */
export interface StageState {
  state: JobState;
  status: StageStatus;
  /** Latest message received for this stage */
  message: string;
  /** ISO timestamp of the last event for this stage */
  timestamp: string | null;
}

/** Static metadata about each stage (label, description) */
export interface StageMeta {
  state: JobState;
  label: string;
  description: string;
}

/**
 * The ordered list of stages as displayed in the timeline.
 * COMPLETED and FAILED share a slot — the terminal item.
 */
export const STAGE_META: StageMeta[] = [
  {
    state: "QUEUED",
    label: "Queued",
    description: "Job accepted and queued for processing.",
  },
  {
    state: "PREPARING",
    label: "Preparing Workspace",
    description: "Creating isolated workspace and writing source files.",
  },
  {
    state: "PREFLIGHT",
    label: "Preflight Validation",
    description: "Running environment validation and preflight checks.",
  },
  {
    state: "HIPIFY",
    label: "HIPIFY Translation",
    description: "Running hipify-clang to translate CUDA to HIP.",
  },
  {
    state: "SCA",
    label: "Compatibility Analysis",
    description: "Scanning for deep architectural mismatches.",
  },
  {
    state: "COMPILING",
    label: "Compiling",
    description: "Running hipcc to validate translated code.",
  },
  {
    state: "ANALYZING",
    label: "AI Analysis",
    description: "Analysis Agent diagnosing compiler errors.",
  },
  {
    state: "PATCHING",
    label: "AI Patching",
    description: "Patch Agent applying targeted code fix.",
  },
  {
    state: "GENERATING_REPORT",
    label: "Generating Report",
    description: "Building migration report, patches, and ZIP archive.",
  },
  {
    state: "COMPLETED",
    label: "Completed",
    description: "Migration finished. Your package is ready to download.",
  },
];
