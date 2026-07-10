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
  compiler_mode?: string;
  compile_status?: string;
  validation_confidence?: string;
  runtime_validation_status?: string;
  translation_status?: string;
  static_validation_status?: string;
  compile_command?: string;
  main_error?: string;
  error_category?: string;
  recommended_next_action?: string;
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
  | "gfx942"
  | "gfx940"
  | "gfx941"
  | "gfx90a"
  | "gfx906"
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

export interface DiagnosticCheck {
  id: string;
  name: string;
  status: "pass" | "fail" | "warn" | "skip";
  critical: boolean;
  category: string;
  message: string;
  recommendation?: string;
  details?: Record<string, unknown>;
  duration_ms?: number;
}

export interface HealthReport {
  generated_at: string;
  overall_status: string;
  health_score: number;
  readiness: string;
  healthy: boolean;
  workspace_path: string;
  output_dir: string;
  checks: DiagnosticCheck[];
  critical_failures: DiagnosticCheck[];
  installed_components: string[];
  missing_components: string[];
  warnings: DiagnosticCheck[];
  recommended_fixes: string[];
}

export interface SelfTestReport {
  generated_at: string;
  workspace_path: string;
  target_arch: string;
  success: boolean;
  failure_category?: string;
  steps: Array<{
    name: string;
    success: boolean;
    message: string;
  }>;
}

export interface MigrationHistoryEntry {
  job_id: string;
  finished_at: string;
  input_name: string;
  target_architecture: string;
  final_state: string;
  compile_status: string;
  validation_confidence: string;
  error_category: string;
  main_error: string;
  report_missing: boolean;
  artifact_missing: boolean;
}

