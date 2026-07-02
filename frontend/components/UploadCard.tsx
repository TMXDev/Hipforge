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
  ArrowRight,
  ClipboardType,
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

type InputMode = "file" | "paste";

interface UploadCardProps {
  /** Called with the new migration_id after a successful submission */
  onSuccess: (migrationId: string) => void;
}

/**
 * UploadCard — Luxury editorial file upload component for HIPForge.
 *
 * Provides:
 * - Two modes: drag-and-drop file upload, or paste CUDA code directly
 * - File validation (type + size)
 * - GPU architecture and retry budget selectors (underline-only luxury inputs)
 * - Start Migration button with gold slide animation
 * - Inline error display with architectural border treatment
 */
export default function UploadCard({ onSuccess }: UploadCardProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [inputMode, setInputMode] = useState<InputMode>("file");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [pastedCode, setPastedCode] = useState("");
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

  /* ── Mode switching ── */

  const switchMode = useCallback((mode: InputMode) => {
    setInputMode(mode);
    setValidationError(null);
    setSubmitError(null);
    setSelectedFile(null);
    setPastedCode("");
  }, []);

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

  /* ── Form submission ── */

  const handleSubmit = useCallback(async () => {
    if (isSubmitting) return;

    // Validate paste mode
    if (inputMode === "paste") {
      if (!pastedCode.trim()) {
        setValidationError("Please paste your CUDA code before submitting.");
        return;
      }
      // Convert pasted code to a File object for the API
      const blob = new Blob([pastedCode], { type: "text/x-csrc" });
      const file = new File([blob], "pasted_code.cu", { type: "text/x-csrc" });
      setSubmitError(null);
      setIsSubmitting(true);
      try {
        const result = await submitMigration(file, targetGpu, retryBudget);
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
      return;
    }

    // Validate file mode
    if (!selectedFile) return;
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
  }, [selectedFile, pastedCode, isSubmitting, inputMode, targetGpu, retryBudget, onSuccess]);

  const canSubmit =
    !isSubmitting &&
    (inputMode === "file" ? selectedFile !== null : pastedCode.trim().length > 0);

  return (
    <div className="w-full max-w-2xl animate-slide-up">
      {/* ── Mode Tabs ── */}
      <div className="flex border-b border-themeBorder">
        <button
          type="button"
          id="upload-tab-file"
          onClick={() => switchMode("file")}
          className={[
            "flex items-center gap-2 border-b-2 px-6 py-4 text-[10px] font-medium tracking-[0.25em] uppercase transition-all duration-500",
            inputMode === "file"
              ? "border-themeText text-themeText"
              : "border-transparent text-themeTextMuted hover:text-themeText",
          ].join(" ")}
        >
          <UploadCloud className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
          Upload File
        </button>
        <button
          type="button"
          id="upload-tab-paste"
          onClick={() => switchMode("paste")}
          className={[
            "flex items-center gap-2 border-b-2 px-6 py-4 text-[10px] font-medium tracking-[0.25em] uppercase transition-all duration-500",
            inputMode === "paste"
              ? "border-themeText text-themeText"
              : "border-transparent text-themeTextMuted hover:text-themeText",
          ].join(" ")}
        >
          <ClipboardType className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
          Paste Code
        </button>
      </div>

      {/* ── Card body ── */}
      <div className="space-y-8 border border-t-0 border-themeBorder bg-themeCard px-8 py-8">

        {/* ══ FILE MODE ══ */}
        {inputMode === "file" && (
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
              "relative flex min-h-[200px] cursor-pointer flex-col items-center justify-center gap-4",
              "border border-dashed transition-all duration-700",
              isDragging
                ? "border-[#D4AF37] bg-[#D4AF37]/4"
                : selectedFile
                  ? "cursor-default border-themeBorderStrong bg-themeBgSecondary/40"
                  : "border-themeBorder/15 bg-transparent hover:border-themeBorderStrong hover:bg-themeBgSecondary/20",
            ].join(" ")}
          >
            {selectedFile ? (
              /* ── File selected state ── */
              <div className="flex flex-col items-center gap-4 px-4 text-center">
                <div className="flex h-12 w-12 items-center justify-center border border-[#D4AF37]/40 bg-[#D4AF37]/8">
                  <FileCode2
                    className="h-5 w-5 text-[#D4AF37]"
                    strokeWidth={1.5}
                    aria-hidden="true"
                  />
                </div>
                <div>
                  <p className="text-sm font-medium text-themeText">
                    {selectedFile.name}
                  </p>
                  <p className="mt-1 text-xs text-themeTextMuted">
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
                  className="flex items-center gap-1.5 border border-themeBorder/15 px-4 py-2 text-[10px] font-medium tracking-[0.2em] uppercase text-themeTextMuted transition-all duration-500 hover:border-themeBorderStrong hover:text-themeText"
                >
                  <X className="h-3 w-3" strokeWidth={1.5} aria-hidden="true" />
                  Remove
                </button>
              </div>
            ) : (
              /* ── Empty / drag state ── */
              <div className="flex flex-col items-center gap-4 px-4 text-center">
                <div
                  className={[
                    "flex h-14 w-14 items-center justify-center border transition-all duration-700",
                    isDragging
                      ? "border-[#D4AF37] bg-[#D4AF37]/10"
                      : "border-themeBorder bg-themeBgSecondary/40",
                  ].join(" ")}
                >
                  <UploadCloud
                    className={[
                      "h-6 w-6 transition-colors duration-700",
                      isDragging ? "text-[#D4AF37]" : "text-themeTextMuted",
                    ].join(" ")}
                    strokeWidth={1.5}
                    aria-hidden="true"
                  />
                </div>
                <div>
                  <p className="text-sm font-medium text-themeText">
                    {isDragging
                      ? "Release to upload"
                      : "Drag & drop your file here"}
                  </p>
                  <p className="mt-1.5 text-xs text-themeTextMuted">
                    or{" "}
                    <span className="border-b border-[#D4AF37] text-themeText">
                      browse files
                    </span>{" "}
                    · .cu or .zip · max 50 MB
                  </p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ══ PASTE MODE ══ */}
        {inputMode === "paste" && (
          <div className="flex flex-col gap-2">
            <label
              htmlFor="paste-code-textarea"
              className="text-[10px] font-medium tracking-[0.25em] uppercase text-themeTextMuted"
            >
              Paste CUDA Source Code
            </label>
            <textarea
              id="paste-code-textarea"
              value={pastedCode}
              onChange={(e) => {
                setPastedCode(e.target.value);
                if (validationError) setValidationError(null);
              }}
              disabled={isSubmitting}
              placeholder="// Paste your .cu CUDA source code here…"
              rows={12}
              className="w-full border border-themeBorder bg-themeBgSecondary/20 p-4 font-mono text-sm text-themeText placeholder-themeTextMuted/60 transition-colors duration-500 focus:border-[#D4AF37] focus:outline-none disabled:opacity-50 resize-y"
              style={{ fontFamily: "'JetBrains Mono', monospace", lineHeight: "1.6" }}
              aria-label="Paste your CUDA source code here"
            />
            <p className="text-[10px] tracking-[0.1em] text-themeTextMuted/60">
              The code will be saved as <code className="font-mono">pasted_code.cu</code> and submitted for migration.
            </p>
          </div>
        )}

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

        {/* Validation error — architectural left-border treatment */}
        {validationError && (
          <div
            role="alert"
            id="upload-validation-error"
            className="flex items-start gap-3 border-l-2 border-red-700 bg-red-50 px-4 py-3"
          >
            <AlertCircle
              className="mt-0.5 h-4 w-4 shrink-0 text-red-600"
              strokeWidth={1.5}
              aria-hidden="true"
            />
            <p className="text-sm text-red-700">{validationError}</p>
          </div>
        )}

        {/* ── Options row — underline-only luxury selects ── */}
        <div className="grid grid-cols-1 gap-8 sm:grid-cols-2">
          {/* GPU Architecture */}
          <div className="flex flex-col gap-2">
            <label
              htmlFor="gpu-architecture-select"
              className="text-[10px] font-medium tracking-[0.25em] uppercase text-themeTextMuted"
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
                className="select-luxury"
              >
                {GPU_ARCHITECTURES.map((arch) => (
                  <option
                    key={arch.value}
                    value={arch.value}
                    className="bg-themeBg text-themeText"
                  >
                    {arch.label}
                  </option>
                ))}
              </select>
              <ChevronDown
                className="pointer-events-none absolute right-1 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-themeTextMuted"
                strokeWidth={1.5}
                aria-hidden="true"
              />
            </div>
            <p className="text-[9px] leading-relaxed text-themeTextMuted/60 uppercase tracking-wider">
              Sets the --offload-arch compilation target target for ROCm/HIP.
            </p>
          </div>

          {/* Retry Budget */}
          <div className="flex flex-col gap-2">
            <label
              htmlFor="retry-budget-select"
              className="text-[10px] font-medium tracking-[0.25em] uppercase text-themeTextMuted"
            >
              AI Repair Attempts
            </label>
            <div className="relative">
              <select
                id="retry-budget-select"
                value={retryBudget}
                onChange={(e) => setRetryBudget(Number(e.target.value))}
                disabled={isSubmitting}
                className="select-luxury"
              >
                {RETRY_OPTIONS.map((n) => (
                  <option
                    key={n}
                    value={n}
                    className="bg-themeBg text-themeText"
                  >
                    {n} {n === 1 ? "attempt" : "attempts"}
                  </option>
                ))}
              </select>
              <ChevronDown
                className="pointer-events-none absolute right-1 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-themeTextMuted"
                strokeWidth={1.5}
                aria-hidden="true"
              />
            </div>
            <p className="text-[9px] leading-relaxed text-themeTextMuted/60 uppercase tracking-wider">
              Max AI analysis and patch cycles to resolve compilation errors.
            </p>
          </div>
        </div>

        {/* Submit error */}
        {submitError && (
          <div
            role="alert"
            id="upload-submit-error"
            className="flex items-start gap-3 border-l-2 border-red-700 bg-red-50 px-4 py-3"
          >
            <AlertCircle
              className="mt-0.5 h-4 w-4 shrink-0 text-red-600"
              strokeWidth={1.5}
              aria-hidden="true"
            />
            <div>
              <p className="text-sm font-medium text-red-700">
                Submission Failed
              </p>
              <p className="mt-0.5 text-xs text-red-600/80">{submitError}</p>
            </div>
          </div>
        )}

        {/* ── Divider ── */}
        <div className="border-t border-themeBorder" />

        {/* ── Start Migration button — luxury primary with gold slide ── */}
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
          className="btn-primary w-full"
        >
          {isSubmitting ? (
            <>
              <Loader2
                className="h-3.5 w-3.5 animate-spin"
                strokeWidth={1.5}
                aria-hidden="true"
              />
              <span>Starting Migration…</span>
            </>
          ) : (
            <>
              <span>Start Migration</span>
              <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
            </>
          )}
        </button>

        {/* Info footer */}
        {!isSubmitting && (
          <p className="text-center text-[10px] tracking-[0.1em] text-themeTextMuted/70">
            Your job is queued immediately — you will be redirected to the live dashboard.
          </p>
        )}

      </div>
    </div>
  );
}
