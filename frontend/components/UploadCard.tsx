"use client";

import {
  useRef,
  useState,
  useCallback,
  type DragEvent,
  type ChangeEvent,
} from "react";
import {
  UploadCloud,
  FileCode2,
  X,
  Loader2,
  AlertCircle,
  ChevronDown,
  Zap,
} from "lucide-react";
import { submitMigration } from "@/services/api";
import type { GpuArchitecture } from "@/types/migration";

/** Accepted MIME types and extensions for upload validation */
const ACCEPTED_EXTENSIONS = [".cu", ".zip"];
const ACCEPTED_MIME_TYPES = [
  "text/x-csrc",
  "application/zip",
  "application/x-zip-compressed",
  "application/octet-stream",
];
/** 50 MB upload size limit */
const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024;

/** GPU architecture options with friendly display names */
const GPU_ARCHITECTURES: { value: GpuArchitecture; label: string }[] = [
  { value: "gfx1100", label: "RDNA 3 — gfx1100 (RX 7000 series)" },
  { value: "gfx1030", label: "RDNA 2 — gfx1030 (RX 6000 series)" },
  { value: "gfx90a", label: "CDNA 2 — gfx90a (MI200 series)" },
  { value: "gfx906", label: "CDNA 1 — gfx906 (MI100 / Vega 20)" },
  { value: "gfx908", label: "CDNA 1 — gfx908 (MI100)" },
];

/** Retry budget options */
const RETRY_OPTIONS = [1, 2, 3, 5];

interface UploadCardProps {
  /** Called with the new migration_id after a successful submission */
  onSuccess: (migrationId: string) => void;
}

/**
 * UploadCard — Primary file upload component for HIPForge.
 *
 * Provides:
 * - Drag-and-drop zone accepting .cu and .zip files
 * - File picker button fallback
 * - File validation (type + size)
 * - GPU architecture and retry budget selectors
 * - Start Migration button with loading state
 * - Inline error display
 */
export default function UploadCard({ onSuccess }: UploadCardProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [targetGpu, setTargetGpu] = useState<GpuArchitecture>("gfx1100");
  const [retryBudget, setRetryBudget] = useState<number>(3);

  /** Validates file type and size. Returns an error string or null. */
  const validateFile = useCallback((file: File): string | null => {
    const lower = file.name.toLowerCase();
    const hasValidExtension = ACCEPTED_EXTENSIONS.some((ext) =>
      lower.endsWith(ext)
    );
    const hasValidMime =
      ACCEPTED_MIME_TYPES.includes(file.type) || file.type === "";

    if (!hasValidExtension && !hasValidMime) {
      return `Invalid file type. Please upload a .cu CUDA source file or a .zip archive.`;
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      return `File is too large (${(file.size / 1024 / 1024).toFixed(1)} MB). Maximum size is 50 MB.`;
    }
    return null;
  }, []);

  /** Accepts a file (post-validation), clearing previous errors. */
  const acceptFile = useCallback(
    (file: File) => {
      const error = validateFile(file);
      if (error) {
        setValidationError(error);
        setSelectedFile(null);
      } else {
        setValidationError(null);
        setSubmitError(null);
        setSelectedFile(file);
      }
    },
    [validateFile]
  );

  /* ── Drag-and-drop handlers ── */

  const handleDragEnter = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragOver = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = "copy";
  }, []);

  const handleDragLeave = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    // Only clear when leaving the outer drop zone, not a child element
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragging(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);

      const files = Array.from(e.dataTransfer.files);
      if (files.length === 0) return;
      if (files.length > 1) {
        setValidationError("Please drop a single file.");
        return;
      }
      acceptFile(files[0]);
    },
    [acceptFile]
  );

  /* ── File picker handler ── */

  const handleFileChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      acceptFile(file);
      // Reset so the same file can be re-selected after clearing
      e.target.value = "";
    },
    [acceptFile]
  );

  const openFilePicker = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const clearFile = useCallback(() => {
    setSelectedFile(null);
    setValidationError(null);
    setSubmitError(null);
  }, []);

  /* ── Form submission ── */

  const handleSubmit = useCallback(async () => {
    if (!selectedFile || isSubmitting) return;
    setSubmitError(null);
    setIsSubmitting(true);

    try {
      const result = await submitMigration(selectedFile, targetGpu, retryBudget);
      onSuccess(result.migration_id);
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : "An unexpected error occurred. Please try again.";
      setSubmitError(message);
    } finally {
      setIsSubmitting(false);
    }
  }, [selectedFile, isSubmitting, targetGpu, retryBudget, onSuccess]);

  /* ── Keyboard accessibility for drop zone ── */

  const handleDropZoneKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openFilePicker();
      }
    },
    [openFilePicker]
  );

  const canSubmit = selectedFile !== null && !isSubmitting;

  return (
    <div className="w-full max-w-2xl animate-slide-up">
      {/* Card */}
      <div className="rounded-2xl border border-white/10 bg-surface-2 shadow-2xl shadow-black/40">
        {/* Card header */}
        <div className="border-b border-white/5 px-8 py-6">
          <h2 className="text-xl font-semibold text-white">
            Upload CUDA Project
          </h2>
          <p className="mt-1 text-sm text-white/50">
            Drop a single{" "}
            <code className="rounded bg-surface-4 px-1 py-0.5 font-mono text-xs text-brand-300">
              .cu
            </code>{" "}
            file or a{" "}
            <code className="rounded bg-surface-4 px-1 py-0.5 font-mono text-xs text-brand-300">
              .zip
            </code>{" "}
            archive containing your CUDA project.
          </p>
        </div>

        <div className="space-y-6 px-8 py-6">
          {/* ── Drop Zone ── */}
          <div
            id="upload-drop-zone"
            role="button"
            tabIndex={0}
            aria-label="Drop zone: drag and drop a .cu or .zip file, or press Enter to browse"
            onDragEnter={handleDragEnter}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onKeyDown={handleDropZoneKeyDown}
            onClick={!selectedFile ? openFilePicker : undefined}
            className={[
              "relative flex min-h-[180px] cursor-pointer flex-col items-center justify-center gap-3",
              "rounded-xl border-2 border-dashed transition-all duration-200",
              isDragging
                ? "border-brand-500 bg-brand-500/8 scale-[1.01]"
                : selectedFile
                  ? "border-emerald-500/40 bg-emerald-500/5 cursor-default"
                  : "border-white/10 bg-surface-3 hover:border-white/20 hover:bg-surface-4",
            ].join(" ")}
          >
            {selectedFile ? (
              /* ── File selected state ── */
              <div className="flex flex-col items-center gap-3 px-4 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/15 ring-1 ring-emerald-500/30">
                  <FileCode2
                    className="h-6 w-6 text-emerald-400"
                    aria-hidden="true"
                  />
                </div>
                <div>
                  <p className="text-sm font-medium text-white">
                    {selectedFile.name}
                  </p>
                  <p className="mt-0.5 text-xs text-white/40">
                    {(selectedFile.size / 1024).toFixed(1)} KB
                  </p>
                </div>
                <button
                  type="button"
                  id="upload-clear-button"
                  onClick={(e) => {
                    e.stopPropagation();
                    clearFile();
                  }}
                  aria-label="Remove selected file"
                  className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-surface-4 px-3 py-1.5 text-xs text-white/60 transition-colors hover:border-white/20 hover:text-white"
                >
                  <X className="h-3 w-3" aria-hidden="true" />
                  Remove
                </button>
              </div>
            ) : (
              /* ── Empty / drag state ── */
              <div className="flex flex-col items-center gap-3 px-4 text-center">
                <div
                  className={[
                    "flex h-14 w-14 items-center justify-center rounded-full ring-1 transition-all duration-200",
                    isDragging
                      ? "bg-brand-500/20 ring-brand-500/50"
                      : "bg-surface-4 ring-white/10",
                  ].join(" ")}
                >
                  <UploadCloud
                    className={[
                      "h-7 w-7 transition-colors duration-200",
                      isDragging ? "text-brand-400" : "text-white/40",
                    ].join(" ")}
                    aria-hidden="true"
                  />
                </div>
                <div>
                  <p className="text-sm font-medium text-white/80">
                    {isDragging
                      ? "Drop file to upload"
                      : "Drag & drop your file here"}
                  </p>
                  <p className="mt-1 text-xs text-white/40">
                    or{" "}
                    <span className="text-brand-400 underline underline-offset-2">
                      browse files
                    </span>{" "}
                    · .cu or .zip · max 50 MB
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            id="upload-file-input"
            type="file"
            accept=".cu,.zip"
            aria-hidden="true"
            tabIndex={-1}
            className="sr-only"
            onChange={handleFileChange}
          />

          {/* Validation error */}
          {validationError && (
            <div
              role="alert"
              id="upload-validation-error"
              className="flex items-start gap-3 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3"
            >
              <AlertCircle
                className="mt-0.5 h-4 w-4 shrink-0 text-red-400"
                aria-hidden="true"
              />
              <p className="text-sm text-red-300">{validationError}</p>
            </div>
          )}

          {/* ── Options row ── */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {/* GPU Architecture */}
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="gpu-architecture-select"
                className="text-xs font-medium text-white/60"
              >
                Target GPU Architecture
              </label>
              <div className="relative">
                <select
                  id="gpu-architecture-select"
                  value={targetGpu}
                  onChange={(e) =>
                    setTargetGpu(e.target.value as GpuArchitecture)
                  }
                  disabled={isSubmitting}
                  className="w-full appearance-none rounded-lg border border-white/10 bg-surface-3 px-3 py-2.5 pr-9 text-sm text-white/90 transition-colors hover:border-white/20 focus:border-brand-500 focus:outline-none disabled:opacity-50"
                >
                  {GPU_ARCHITECTURES.map((arch) => (
                    <option
                      key={arch.value}
                      value={arch.value}
                      className="bg-surface-3"
                    >
                      {arch.label}
                    </option>
                  ))}
                </select>
                <ChevronDown
                  className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/40"
                  aria-hidden="true"
                />
              </div>
            </div>

            {/* Retry Budget */}
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="retry-budget-select"
                className="text-xs font-medium text-white/60"
              >
                AI Repair Attempts
              </label>
              <div className="relative">
                <select
                  id="retry-budget-select"
                  value={retryBudget}
                  onChange={(e) => setRetryBudget(Number(e.target.value))}
                  disabled={isSubmitting}
                  className="w-full appearance-none rounded-lg border border-white/10 bg-surface-3 px-3 py-2.5 pr-9 text-sm text-white/90 transition-colors hover:border-white/20 focus:border-brand-500 focus:outline-none disabled:opacity-50"
                >
                  {RETRY_OPTIONS.map((n) => (
                    <option key={n} value={n} className="bg-surface-3">
                      {n} {n === 1 ? "attempt" : "attempts"}
                    </option>
                  ))}
                </select>
                <ChevronDown
                  className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/40"
                  aria-hidden="true"
                />
              </div>
            </div>
          </div>

          {/* Submit error */}
          {submitError && (
            <div
              role="alert"
              id="upload-submit-error"
              className="flex items-start gap-3 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3"
            >
              <AlertCircle
                className="mt-0.5 h-4 w-4 shrink-0 text-red-400"
                aria-hidden="true"
              />
              <div>
                <p className="text-sm font-medium text-red-300">
                  Submission Failed
                </p>
                <p className="mt-0.5 text-xs text-red-400/80">{submitError}</p>
              </div>
            </div>
          )}

          {/* ── Start Migration button ── */}
          <button
            id="start-migration-button"
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            aria-busy={isSubmitting}
            aria-label={
              isSubmitting
                ? "Starting migration, please wait"
                : "Start Migration"
            }
            className={[
              "flex w-full items-center justify-center gap-2.5 rounded-xl px-6 py-3.5 text-sm font-semibold",
              "transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-2",
              canSubmit
                ? "bg-gradient-to-r from-brand-600 to-brand-500 text-white shadow-lg shadow-brand-900/40 hover:from-brand-500 hover:to-brand-400 hover:shadow-brand-800/50 active:scale-[0.98]"
                : "cursor-not-allowed bg-surface-4 text-white/30",
            ].join(" ")}
          >
            {isSubmitting ? (
              <>
                <Loader2
                  className="h-4 w-4 animate-spin"
                  aria-hidden="true"
                />
                Starting Migration…
              </>
            ) : (
              <>
                <Zap className="h-4 w-4" aria-hidden="true" />
                Start Migration
              </>
            )}
          </button>

          {/* Info footer */}
          {!isSubmitting && (
            <p className="text-center text-xs text-white/30">
              Your job is queued immediately. You will be redirected to the live
              dashboard.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
