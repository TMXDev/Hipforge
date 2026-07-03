/**
 * HIPForge frontend API service.
 * All communication with the FastAPI backend goes through this module.
 * Implements endpoints defined in docs/16_API_SPECIFICATION.md.
 */

import type { MigrationResponse, MigrationStatus, JournalEntry, HealthReport, SelfTestReport } from "@/types/migration";

/** Base URL read from the Next.js environment variable, defaults to localhost for dev.
 *  Supports both NEXT_PUBLIC_API_URL and NEXT_PUBLIC_BACKEND_URL for compatibility. */
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ??
  process.env.NEXT_PUBLIC_BACKEND_URL ??
  "http://localhost:8000";


/**
 * Uploads a CUDA source file (.cu or .zip) to start a new migration.
 * Calls POST /api/v1/migrate/upload with multipart/form-data.
 *
 * @param file - The file selected by the user.
 * @param targetGpuArchitecture - Target ROCm GPU architecture (e.g. "gfx1100").
 * @param retryBudget - Maximum number of AI repair attempts (1–5).
 * @returns A resolved MigrationResponse containing the migration_id.
 * @throws An Error with a user-friendly message on non-202 responses.
 */
const toBase64 = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
      const result = reader.result as string;
      const commaIndex = result.indexOf(",");
      if (commaIndex !== -1) {
        resolve(result.substring(commaIndex + 1));
      } else {
        resolve(result);
      }
    };
    reader.onerror = (error) => reject(error);
  });

export async function submitMigration(
  file: File,
  targetGpuArchitecture: string,
  retryBudget: number
): Promise<MigrationResponse> {
  const base64File = await toBase64(file);
  const payload = {
    file: base64File,
    filename: file.name,
    target_gpu_architecture: targetGpuArchitecture,
    retry_budget: retryBudget,
    migration_mode: "file",
  };

  const response = await fetch(`${API_BASE_URL}/api/v1/migrate/upload`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let detail = `Upload failed (HTTP ${response.status})`;
    try {
      const errorBody = await response.json();
      if (errorBody?.detail) {
        detail = String(errorBody.detail);
      }
    } catch {
      // JSON parse failed — keep generic message
    }
    throw new Error(detail);
  }

  const data: MigrationResponse = await response.json();
  return data;
}

/**
 * Retrieves the current status of a migration job.
 * Calls GET /api/v1/migrate/{migration_id}/status.
 *
 * @param migrationId - UUID of the migration to query.
 * @returns The current MigrationStatus.
 * @throws An Error with a user-friendly message on failure.
 */
export async function getMigrationStatus(
  migrationId: string
): Promise<MigrationStatus> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/migrate/${migrationId}/status`
  );

  if (!response.ok) {
    throw new Error(`Status check failed (HTTP ${response.status})`);
  }

  return response.json();
}

/**
 * Returns the WebSocket URL for real-time migration event streaming.
 * Connects to ws://.../ws/v1/migrate/{migration_id}/stream as defined
 * in docs/16_API_SPECIFICATION.md.
 *
 * @param migrationId - UUID of the migration to stream.
 * @returns WebSocket URL string.
 */
export function getMigrationStreamUrl(migrationId: string): string {
  const wsBase = API_BASE_URL.replace(/^http/, "ws");
  return `${wsBase}/ws/v1/migrate/${migrationId}/stream`;
}

/**
 * Fetches all migration journal entries.
 * Calls GET /api/v1/migrate/{migration_id}/journal.
 *
 * @param migrationId - UUID of the migration.
 * @returns Array of JournalEntry objects, newest first.
 * @throws An Error on non-200 responses.
 */
export async function getJournal(
  migrationId: string
): Promise<JournalEntry[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/migrate/${migrationId}/journal`
  );

  if (!response.ok) {
    throw new Error(`Journal fetch failed (HTTP ${response.status})`);
  }

  const data: unknown = await response.json();
  // The backend returns a plain array of journal entries
  if (Array.isArray(data)) {
    return data as JournalEntry[];
  }
  return [];
}

/**
 * Returns the direct URL for downloading the migration ZIP archive.
 * The browser triggers a file download by navigating to this URL.
 * Endpoint: GET /api/v1/migrate/{migration_id}/download
 *
 * @param migrationId - UUID of the completed migration.
 * @returns Absolute URL string for the download endpoint.
 */
export function getDownloadUrl(migrationId: string): string {
  return `${API_BASE_URL}/api/v1/migrate/${migrationId}/download`;
}

/**
 * Fetches all compiler log lines.
 * Calls GET /api/v1/migrate/{migration_id}/compiler-logs.
 *
 * @param migrationId - UUID of the migration.
 * @returns Array of log line objects.
 */
export async function getCompilerLogs(
  migrationId: string
): Promise<any[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/migrate/${migrationId}/compiler-logs`
  );

  if (!response.ok) {
    throw new Error(`Compiler logs fetch failed (HTTP ${response.status})`);
  }

  return response.json();
}

export async function getHealthCheck(): Promise<HealthReport> {
  const response = await fetch(`${API_BASE_URL}/api/v1/health/check`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Health check failed (HTTP ${response.status})`);
  }

  return response.json();
}

export async function runSelfTest(): Promise<SelfTestReport> {
  const response = await fetch(`${API_BASE_URL}/api/v1/self-test`, {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`Self-test failed (HTTP ${response.status})`);
  }

  return response.json();
}
