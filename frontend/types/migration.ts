/**
 * Types for HIPForge migration API responses.
 * Matches the schemas defined in docs/16_API_SPECIFICATION.md.
 */

/** Response from POST /api/v1/migrate/upload or POST /api/v1/migrate/paste */
export interface MigrationResponse {
  /** UUID assigned to this migration job */
  migration_id: string;
  /** Initial status — always "initializing" on 202 Accepted */
  status: string;
  /** Human-readable confirmation message */
  message: string;
}

/** Response from GET /api/v1/migrate/{migration_id}/status */
export interface MigrationStatus {
  migration_id: string;
  status: string;
  stage: string;
  created_at: string;
  updated_at: string;
  current_stage?: string;
  progress?: number;
  message?: string;
}

/** Standardised API error body returned by the backend */
export interface ApiError {
  detail: string;
  code: string;
  trace_id: string;
}

/** GPU architecture options supported by the backend */
export type GpuArchitecture =
  | "gfx1100"
  | "gfx1030"
  | "gfx906"
  | "gfx90a"
  | "gfx908";

/** Migration input mode */
export type MigrationMode = "file" | "paste";

/**
 * A single entry in the migration journal.
 * Shape matches journal_service.py write_state_journal_entry().
 */
export interface JournalEntry {
  attempt: number;
  timestamp: string;
  workflow_state: string;
  compiler_result: string;
  analysis_summary: string | null;
  patch_summary: string | null;
  research_summary: string | null;
  files_modified: string[];
  compiler_error_hash: string | null;
}
