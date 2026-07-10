"""
backend/app/services/report_service.py

Report Generator Service — Session 11.1

Generates markdown reports, JSON reports, git unified diff patches,
and packages them along with source artifacts into a downloadable ZIP archive.
"""

import os
import json
import datetime
import hashlib
import logging
import zipfile
import difflib
import re
from typing import Any, Dict, List, Optional
from pathlib import Path

from app.workspace.manager import get_workspace_path
from app.redis.client import redis_client
from app.redis.keys import status_key
from app.compiler.project_scanner import project_summary_line

logger = logging.getLogger("report_service")


def _actual_compiled_architecture(context: Any) -> str:
    if not getattr(context, "compilation_success", False):
        return ""
    actual = getattr(context, "actual_compiled_architecture", "") or ""
    if actual:
        return actual
    match = re.search(
        r"--offload-arch(?:=|\s+)(gfx\w+)",
        getattr(context, "last_compile_command", "") or "",
    )
    return match.group(1) if match else ""


def _ai_repair_status(context: Any, cycles: int) -> str:
    if cycles > 0:
        return "succeeded" if getattr(context, "compilation_success", False) else "failed"
    if get_skipped_ai_repair_reason(context):
        return "skipped" if not getattr(context, "compilation_success", False) else "not_needed"
    return "not_needed"


def _final_workflow_state(context: Any) -> str:
    state = getattr(context, "current_state", "COMPLETED")
    return "COMPLETED" if state == "GENERATING_REPORT" else state


def compute_file_hash(file_path: Path) -> str:
    """Computes the SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as exc:
        logger.error("[ReportService] Failed to hash file %s: %s", file_path, exc)
        return "unknown"


def _get_final_source(workspace_path: Path, original_filename: str) -> Optional[str]:
    """
    Attempts to locate the final translated/patched content for an original input file.
    Checks generated/ folder first, then falls back to the latest patch attempt file.
    """
    stem = Path(original_filename).stem
    
    # 1. Try generated/ folder (with .hip or original extension)
    for ext in (".hip", ".cu", ".cpp", ".cuh"):
        gen_file = workspace_path / "generated" / f"{stem}{ext}"
        if gen_file.exists():
            return gen_file.read_text(encoding="utf-8", errors="replace")

    # 2. Try latest patch file in patches/
    patches_dir = workspace_path / "patches"
    if patches_dir.exists():
        patch_candidates = list(patches_dir.glob(f"patch_attempt_*_{stem}.hip"))
        if not patch_candidates:
            patch_candidates = list(patches_dir.glob(f"patch_attempt_*_{original_filename}"))
        if patch_candidates:
            # Sort to get the latest attempt (e.g. patch_attempt_002_... vs patch_attempt_001_...)
            patch_candidates.sort()
            latest_patch = patch_candidates[-1]
            return latest_patch.read_text(encoding="utf-8", errors="replace")

    return None


def get_skipped_ai_repair_reason(context: Any) -> Optional[str]:
    """
    Computes why AI repair was skipped during the migration.
    """
    compilation_success = getattr(context, "compilation_success", False)
    actual_attempts = getattr(context, "current_attempt", 0)
    retry_budget = getattr(context, "retry_budget", 0)
    error_category = getattr(context, "error_category", "NONE")

    if compilation_success and actual_attempts == 0:
        return "Not needed: compilation succeeded on first attempt."
    if error_category in ("NO_PROJECT_FILES", "ENVIRONMENT_FAIL") or getattr(context, "infrastructure_error", False):
        return f"Skipped: migration aborted due to infrastructure/preflight error ({error_category})."
    if retry_budget == 0 and not compilation_success:
        return "Skipped: retry budget set to 0."

    journal = getattr(context, "migration_journal", [])
    ai_requests = len([entry for entry in journal if entry.get("analysis_summary") or entry.get("patch_summary") or entry.get("research_summary")])
    if ai_requests > 0:
        return None

    return "Skipped: no compile failure encountered."


async def _recalculate_validation_confidence(context: Any) -> None:
    from app.compiler.validation_confidence import compute_confidence
    from app.config.settings import settings

    compiler_mode = getattr(context, "compiler_mode", "real")
    compile_status = getattr(context, "compile_status", "NOT_RUN")
    
    hipify_ok = bool(getattr(context, "hipify_output_path", None))
    compile_ok = getattr(context, "compilation_success", False)
    
    tools_missing = (compiler_mode == "unavailable")
    if compile_status == "FAILED_SETUP":
        tools_missing = True
        
    runtime_ok = (getattr(context, "runtime_validation_status", "NOT_RUN") == "PASSED")
    profiled = (getattr(context, "profiling_status", "NOT_RUN") == "PASSED")
    
    level, reason = compute_confidence(
        hipify_ok=hipify_ok,
        compile_ok=compile_ok,
        runtime_ok=runtime_ok,
        profiled=profiled,
        compiler_mocked=(compiler_mode == "test-only" or settings.USE_MOCK_COMPILER),
        tools_missing=tools_missing
    )
    context.validation_confidence = level
    context.validation_confidence_reason = reason

    # Save fields to Redis metadata
    try:
        from app.redis.keys import metadata_key
        from app.redis.client import redis_client
        m_key = metadata_key(context.migration_id)
        await redis_client.hset(
            m_key,
            mapping={
                "validation_confidence": level,
                "validation_confidence_reason": reason,
                "compiler_mode": compiler_mode,
                "compile_status": compile_status,
                "translation_status": "PASSED" if bool(getattr(context, "hipify_output_path", None)) else "FAILED",
                "static_validation_status": getattr(context, "static_validation_status", "NOT_RUN"),
                "runtime_validation_status": getattr(context, "runtime_validation_status", "NOT_RUN"),
                "last_compile_command": getattr(context, "last_compile_command", ""),
                "failure_reason": getattr(context, "failure_reason", "") or "",
                "main_error": getattr(context, "main_error", "") or getattr(context, "last_compile_stderr", "") or ""
            }
        )
    except Exception as exc:
        logger.warning("[ReportService] Failed to save recalculated metadata to Redis: %s", exc)

async def generate_markdown_report(migration_id: str, context: Any) -> None:
    """
    Generates reports/migration_report.md summarizing the migration session,
    metrics, compiler history, and AI activities.
    """
    await _recalculate_validation_confidence(context)
    workspace_path = get_workspace_path(migration_id)
    reports_dir = workspace_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / "migration_report.md"

    status = "PASSED" if getattr(context, "compilation_success", False) else "FAILED"
    actual_retries = getattr(context, "current_attempt", 0)
    preflight_report = getattr(context, "preflight_report", None) or {}
    failure_category = getattr(context, "error_category", "NONE")
    try:
        from app.diagnostics import recommended_next_action
        next_action = getattr(context, "recommended_next_action", "") or recommended_next_action(failure_category, preflight_report)
    except Exception:
        next_action = getattr(context, "recommended_next_action", "") or "Run hipforge doctor and inspect the generated diagnostics."

    import datetime
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    start_time = getattr(context, "start_time", now_str)
    
    start_time_secs = getattr(context, "start_time_secs", None)
    duration_seconds = 0.0
    if start_time_secs:
        import time
        duration_seconds = round(time.time() - start_time_secs, 2)
    
    # project scan summary
    project_scan = getattr(context, "project_scan", {}) or {}
    project_scan_category = project_scan.get("category", "standard_cuda")
    project_scan_summary = project_scan.get("message", "standard_cuda")
    project_scan_strategy = project_scan.get("compile_strategy", "none")
    project_scan_summary = project_scan_summary or "standard_cuda"
    project_scan_strategy = project_scan_strategy or "none"
    scan_detail = project_scan.get("detail", "") or ""

    # original files
    input_dir = workspace_path / "input"
    original_files = []
    if input_dir.exists():
        original_files = [f.name for f in input_dir.iterdir() if f.is_file()]

    # Collect compilation log list
    logs_dir = workspace_path / "logs"
    log_summaries = []
    if logs_dir.exists():
        for log_file in sorted(logs_dir.glob("compile_attempt_*.log")):
            try:
                content = log_file.read_text(encoding="utf-8", errors="replace")
                log_summaries.append(f"**{log_file.name}**:\n```\n{content.strip()}\n```")
            except Exception:
                pass

    journal = getattr(context, "migration_journal", [])

    compile_attempts = len(log_summaries)
    ai_repair_cycles = len([entry for entry in journal if entry.get("analysis_summary") or entry.get("patch_summary") or entry.get("research_summary")])
    failed_stage = getattr(context, "failed_stage", "") or ""
    main_error = getattr(context, "main_error", "") or ""
    skipped_reason = get_skipped_ai_repair_reason(context) or ""

    # Build markdown report content
    translation_status = "PASSED" if bool(getattr(context, "hipify_output_path", None)) else "FAILED"
    compile_status = getattr(context, "compile_status", "NOT_RUN")
    static_validation_status = getattr(context, "static_validation_status", "NOT_RUN")
    runtime_validation_status = getattr(context, "runtime_validation_status", "NOT_RUN")

    lines = [
        f"# HIPForge Migration Report",
        f"",
        f"## 1. Migration Summary",
        f"- **Migration ID**: `{migration_id}`",
        f"- **Status**: `{status}`",
        f"- **Start Time**: `{start_time}`",
        f"- **End Time**: `{now_str}`",
        f"- **Target GPU Architecture**: `{getattr(context, 'target_gpu_architecture', 'gfx90a')}`",
        f"- **Actual Compiled Architecture**: `{_actual_compiled_architecture(context) or 'N/A'}`",
        f"- **Last Compile Command**: `{getattr(context, 'last_compile_command', 'N/A')}`",
        f"- **Architecture Selection Source**: `{getattr(context, 'architecture_selection_source', 'unknown')}`",
        f"- **Architecture Confidence**: `{getattr(context, 'architecture_confidence', 'LOW')}`",
        f"- **Retry Budget**: `{getattr(context, 'retry_budget', 0)}`",
        f"- **Actual Retries**: `{actual_retries}`",
        f"- **Translation Status**: `{translation_status}`",
        f"- **Compilation Status**: `{compile_status}`",
        f"- **Static Validation Status**: `{static_validation_status}`",
        f"- **Runtime Validation Status**: `{runtime_validation_status}`",
        f"",
        f"> [!NOTE]",
        f"> Local AMD hardware is not required for translation and cross-compilation.",
        f"",

        f"## 2. Environment Summary",
        f"- **Pre-flight Status**: `{preflight_report.get('overall_status', 'not recorded')}`",
        f"- **Health Score**: `{preflight_report.get('health_score', 'n/a')}`",
        f"- **Readiness**: `{preflight_report.get('readiness', 'n/a')}`",
        f"- **Critical Environment Failures**: `{len(preflight_report.get('critical_failures', []))}`",
        f"",
        f"## 3. Project Scan",
        f"- **Classification**: `{project_scan_category}`",
        f"- **Message**: {project_scan_summary}",
        f"- **Scan Detail**: {scan_detail}",
        f"- **Compile Strategy**: `{project_scan_strategy}`",
        f"- **Generated Build Plan**: `{'Yes' if getattr(context, 'generated_build_plan', False) else 'No'}`",
        f"",
        f"## 4. Input Project Details",
        f"- **Original Files Uploaded**:"
    ]

    # ── Architecture Advice Section ──────────────────────────────────────────
    arch_advice = getattr(context, "architecture_advice", {}) or {}
    cuda_hints = arch_advice.get("cuda_arch_hints", [])
    arch_risk_warnings = arch_advice.get("risk_warnings", [])
    arch_recommended = arch_advice.get("recommended_actions", [])
    if cuda_hints or arch_risk_warnings or arch_recommended:
        lines.append(f"## 3b. Architecture Advisor")
        if cuda_hints:
            lines.append(f"- **CUDA Arch Hints Found**: {', '.join(f'`{h}`' for h in cuda_hints)}")
        if arch_risk_warnings:
            lines.append(f"- **Risk Warnings** ({len(arch_risk_warnings)}):")
            for w in arch_risk_warnings:
                lines.append(f"  - {w}")
        if arch_recommended:
            lines.append(f"- **Advisor Notes**:")
            for n in arch_recommended:
                lines.append(f"  - {n}")
        lines.append(f"")

    project_inventory = getattr(context, "project_inventory", None) or {}
    if project_inventory:
        lines.extend([
            f"- **Input Kind**: `{project_inventory.get('input_kind', 'unknown')}`",
            f"- **Build System**: `{project_inventory.get('build_system_detected', 'none')}`",
            f"- **Generated Makefile Fallback**: `{'Yes' if project_inventory.get('generated_makefile_fallback') else 'No'}`",
        ])

    generated_makefile_path = getattr(context, "generated_makefile_path", None)
    if generated_makefile_path:
        lines.append(f"- **Generated Makefile Path**: `{generated_makefile_path}`")

    source_files = getattr(context, "source_files", []) or []
    if source_files:
        lines.append(f"- **Source Files Compiled**: {', '.join(f'`{f}`' for f in source_files)}")

    last_compile_cmd = getattr(context, "last_compile_command", "") or ""
    if last_compile_cmd:
        lines.append(f"- **Last Compile Command**: `{last_compile_cmd}`")
    
    for f in original_files:
        h = compute_file_hash(input_dir / f)
        lines.append(f"  - `{f}` (SHA-256: `{h}`)")

    # ── File Lifecycle Tracking Section ──
    lines.extend([
        f"",
        f"## 4b. File Lifecycle Tracking",
    ])
    file_lifecycle = getattr(context, "file_lifecycle", {})
    if file_lifecycle:
        for orig_path, meta in file_lifecycle.items():
            lines.extend([
                f"- **Original File**: `{orig_path}`",
                f"  - **Generated Path**: `{meta.get('generated_path', 'N/A')}`",
                f"  - **Converted**: `{'Yes' if meta.get('converted') else 'No'}`",
                f"  - **Modified by AI**: `{'Yes' if meta.get('modified_by_ai') else 'No'}`",
                f"  - **Included in Compile**: `{'Yes' if meta.get('included_in_compile') else 'No'}`",
                f"  - **Compile Status**: `{meta.get('compile_status', 'NOT_RUN')}`",
            ])
            if meta.get("failure_reason"):
                lines.append(f"  - **Failure Reason**: {meta.get('failure_reason')}")
            if meta.get("skipped_reason"):
                lines.append(f"  - **Skipped Reason**: {meta.get('skipped_reason')}")
    else:
        lines.append("- No file lifecycle tracking data available.")

    lines.extend([
        f"",
        f"## 5. Translation Summary",
        f"- **hipify-clang Status**: `SUCCESS`" if getattr(context, "hipify_output_path", None) else "- **hipify-clang Status**: `FAILED` / `SKIPPED`"
    ])

    if getattr(context, "sca_result", None):
        lines.append(f"- **Semantic Compatibility Analysis (SCA) Findings**:")
        issues = context.sca_result.get("issues", [])
        if issues:
            for issue in issues:
                desc = issue.get("description", "Potential migration risk") if isinstance(issue, dict) else str(issue)
                lines.append(f"  - {desc}")
        else:
            lines.append("  - No compatibility issues detected.")

    lines.extend([
        f"",
        f"## 6. Compilation History",
    ])
    if log_summaries:
        lines.extend(log_summaries)
    else:
        lines.append("- No compilation logs recorded.")

    lines.extend([
        f"",
        f"## 7. AI Usage Summary",
    ])

    ai_requests = len([entry for entry in journal if entry.get("analysis_summary") or entry.get("patch_summary") or entry.get("research_summary")])
    lines.append(f"- **AI Requests Recorded**: `{ai_requests}`")
    lines.append("- **Token Usage**: `not captured by current client instrumentation`")
    if getattr(context, "ai_context_truncated", False):
        lines.append("- **AI Prompt Context Status**: `TRUNCATED` (AI prompt context size limit exceeded and was safely truncated to prevent hang)")

    lines.extend([
        f"",
        f"## 8. AI Agent Activity",
    ])
    
    # Summarize from Migration Journal
    if journal:
        for idx, entry in enumerate(journal):
            lines.append(f"### Attempt {entry.get('attempt', idx + 1)}")
            if entry.get("analysis_summary"):
                lines.append(f"- **Analysis Summary**: {entry.get('analysis_summary')}")
                lines.append(f"  - *Root Cause*: {entry.get('root_cause', '')}")
            if entry.get("patch_summary"):
                lines.append(f"- **Patch Summary**: {entry.get('patch_summary')}")
            if entry.get("research_summary"):
                lines.append(f"- **Research Summary**: {entry.get('research_summary')}")
    else:
        lines.append("- No AI Agent interactions recorded.")

    patch_audit = getattr(context, "patch_validations", None) or []
    if not patch_audit and getattr(context, "patch_validation", None):
        patch_audit = [context.patch_validation]
    if patch_audit:
        lines.extend(["", "## 8a. Patch Audit"])
        for item in patch_audit:
            lines.extend([
                f"- **Target File**: `{item.get('target_file', 'N/A')}`",
                f"  - **Accepted**: `{item.get('accepted', False)}`",
                f"  - **Reason**: {item.get('reason', '')}",
                f"  - **Changed Lines**: `{item.get('changed_lines', 0)}`",
                f"  - **Pre-patch Hash**: `{item.get('before_hash', '')}`",
                f"  - **Post-patch Hash**: `{item.get('after_hash', '')}`",
                f"  - **Architecture-sensitive Warning**: {item.get('arch_warning') or 'None'}",
                "  - **Unified Diff**:",
                f"```diff\n{item.get('diff', '').rstrip()}\n```",
            ])

    # 8b. Learning / Previous Knowledge Used
    lesson_matched = getattr(context, "lesson_matched", None)
    if lesson_matched:
        lines.extend([
            f"",
            f"## 8b. Learning / Previous Knowledge Used",
            f"- **Lesson Category**: `{lesson_matched.get('category', 'N/A')}`",
            f"- **Previously Recommended Action**: {lesson_matched.get('recommended_action', 'N/A')}",
            f"- **Patch Attempted Previously**: `{lesson_matched.get('patch_attempted', False)}`",
            f"- **Patch Skipped Reason**: {lesson_matched.get('patch_skipped_reason', 'N/A')}",
            f"- **Lesson Timestamp**: `{lesson_matched.get('timestamp', 'N/A')}`",
        ])

    # 9. Migration Metrics & Validation
    lines.extend([
        f"",
        f"## 9. Migration Metrics & Validation",
        f"- **CUDA APIs Detected**: `{getattr(context, 'cuda_apis_detected', 0)}`",
        f"- **CUDA APIs Automatically Converted**: `{getattr(context, 'cuda_apis_converted', 0)}`",
        f"- **Remaining CUDA APIs**: `{getattr(context, 'cuda_apis_remaining', 0)}`",
        f"- **Files Modified**: `{len(getattr(context, 'files_modified', []))}` files",
        f"- **Number of Patch Iterations**: `{actual_retries}`",
        f"- **Compile Success/Failure**: `{status}`",
        f"- **Error Category**: `{failure_category}`",
        f"- **Total Migration Duration**: `{duration_seconds}s`",
    ])
    
    stage_timings = getattr(context, "stage_timings", {})
    if stage_timings:
        lines.append(f"- **Stage Timings**:")
        for stage_name, stage_dur in stage_timings.items():
            lines.append(f"  - **{stage_name}**: `{stage_dur}s`")
    
    lines.extend([
        f"- **Target Architecture**: `{getattr(context, 'target_gpu_architecture', 'gfx90a')}`",
        f"- **Repair Budget**: `{getattr(context, 'retry_budget', 0)}`",
        f"- **Compile Attempts**: `{compile_attempts}`",
        f"- **AI Repair Cycles**: `{ai_repair_cycles}`",
        f"- **Failed Stage**: `{failed_stage}`",
        f"- **Main Error**: `{main_error}`",
        f"- **Skipped AI Repair Reason**: `{skipped_reason}`",
    ])

    val_confidence = getattr(context, "validation_confidence", "LOW")
    val_reason = getattr(context, "validation_confidence_reason", "")
    rt_enabled = getattr(context, "runtime_validation_enabled", False)
    rt_status = getattr(context, "runtime_validation_status", "NOT_CONFIGURED")
    rt_reason = getattr(context, "runtime_validation_reason", "")
    prof_status = getattr(context, "profiling_status", "NOT_CONFIGURED")
    
    # Launcher memory contract and hardening details
    expects_device_ptr = getattr(context, "launcher_expects_device_pointers", "N/A")
    rt_perf = "Yes" if rt_status == "PASSED" else "No"
    conf_type = "runtime-validated" if rt_status == "PASSED" else "compile-only"
    err_checks = getattr(context, "kernel_launch_error_checks", "none")
    sync_status = getattr(context, "synchronization_status", "none")

    lines.extend([
        f"",
        f"## 9b. Validation Confidence",
        f"- **Validation Confidence**: `{val_confidence}`",
        f"- **Confidence Reason**: {val_reason}",
        f"- **Compile Validation Status**: `{status}`",
        f"- **Runtime Validation Enabled**: `{'Yes' if rt_enabled else 'No'}`",
        f"- **Runtime Validation Status**: `{rt_status}`",
        f"- **Runtime Validation Reason**: {rt_reason or 'N/A'}",
        f"- **Profiling Status**: `{prof_status}`",
        f"- **Launcher Expects Device Pointers**: `{expects_device_ptr}`",
        f"- **Runtime Execution Performed**: `{rt_perf}`",
        f"- **Validation Confidence Type**: `{conf_type}`",
        f"- **Kernel Launch Error Checks**: `{err_checks}`",
        f"- **Synchronization Status**: `{sync_status}`",
    ])

    lines.extend([
        f"",
        f"## 10. Final Summary",
        f"- **Environment Summary**: `{preflight_report.get('readiness', 'n/a')}`",
        f"- **Migration Summary**: `{status}`",
        f"- **Compile Summary**: `{'PASSED' if getattr(context, 'compilation_success', False) else 'FAILED or SKIPPED'}`",
        f"- **Repair Iterations**: `{actual_retries}`",
        f"- **Elapsed Time**: `{duration_seconds}s`",
        f"- **Failure Category**: `{failure_category}`",
        f"- **Recommended Next Action**: {next_action}"
    ])
    
    initial_apis = getattr(context, 'initial_cuda_apis_detail', {})
    remaining_apis = getattr(context, 'remaining_cuda_apis_detail', {})
    if initial_apis:
        lines.append(f"  - *Initial CUDA APIs Breakdown*:")
        for api, count in initial_apis.items():
            lines.append(f"    - `{api}`: {count} occurrence(s)")
    if remaining_apis:
        lines.append(f"  - *Remaining CUDA APIs Breakdown*:")
        for api, count in remaining_apis.items():
            lines.append(f"    - `{api}`: {count} occurrence(s)")

    from app.config.settings import settings
    ai_mode = "mock" if settings.USE_MOCK_AI else "real"
    ai_repair_status = _ai_repair_status(context, ai_repair_cycles)
    final_workflow_state = _final_workflow_state(context)
    compiler_mode = getattr(context, "compiler_mode", "real")
    compile_status = getattr(context, "compile_status", "NOT_RUN")
    generated_artifact_path = f"exports/{migration_id}.zip"

    lines.extend([
        f"",
        f"## 11. Pipeline Configuration & Metadata",
        f"- **Final Workflow State**: `{final_workflow_state}`",
        f"- **Compiler Mode**: `{compiler_mode}`",
        f"- **Compile Status**: `{compile_status}`",
        f"- **AI Mode**: `{ai_mode}`",
        f"- **AI Repair Status**: `{ai_repair_status}`",
        f"- **Generated Artifact Path**: `{generated_artifact_path}`",
        f"- **Report Generated Timestamp**: `{now_str}`",
    ])

    try:
        report_file.write_text("\n".join(lines), encoding="utf-8")
        logger.info("[ReportService] Markdown report generated: %s", report_file)
    except Exception as exc:
        logger.error("[ReportService] Failed to write markdown report: %s", exc)


async def generate_json_report(migration_id: str, context: Any) -> None:
    """
    Generates reports/migration_report.json containing all structured data fields
    defined in docs/17_REPORT_GENERATOR.md.
    """
    await _recalculate_validation_confidence(context)
    workspace_path = get_workspace_path(migration_id)
    reports_dir = workspace_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_file = reports_dir / "migration_report.json"

    status = "PASSED" if getattr(context, "compilation_success", False) else "FAILED"
    actual_retries = getattr(context, "current_attempt", 0)
    preflight_report = getattr(context, "preflight_report", None) or {}
    failure_category = getattr(context, "error_category", "NONE")
    try:
        from app.diagnostics import recommended_next_action
        next_action = getattr(context, "recommended_next_action", "") or recommended_next_action(failure_category, preflight_report)
    except Exception:
        next_action = getattr(context, "recommended_next_action", "") or "Run hipforge doctor and inspect the generated diagnostics."

    import time
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    start_time = getattr(context, "start_time", now_str)
    
    start_time_secs = getattr(context, "start_time_secs", None)
    duration_seconds = 0.0
    if start_time_secs:
        duration_seconds = round(time.time() - start_time_secs, 2)

    # 1. Migration Summary
    summary = {
        "migration_id": migration_id,
        "status": status,
        "start_time": start_time,
        "end_time": now_str,
        "duration_seconds": duration_seconds,
        "input_method": "single_file",
        "target_gpu_architecture": getattr(context, "target_gpu_architecture", "gfx90a"),
        "retry_budget": getattr(context, "retry_budget", 0),
        "actual_retries": actual_retries,
        "migration_mode": getattr(context, "migration_mode", "Balanced"),
        "architecture_selection_source": getattr(context, "architecture_selection_source", "unknown"),
        "architecture_confidence": getattr(context, "architecture_confidence", "LOW"),
        "architecture_advice": getattr(context, "architecture_advice", {}),
    }

    # 2. Input Project Details
    input_dir = workspace_path / "input"
    original_files = []
    file_hashes = {}
    if input_dir.exists():
        for f in input_dir.iterdir():
            if f.is_file():
                original_files.append(f.name)
                file_hashes[f.name] = compute_file_hash(f)

    # 2b. Project Scan Summary
    project_scan_json = {}
    project_scan = getattr(context, "project_scan", None)
    if project_scan:
        project_scan_json = {
            "classification": project_scan.get("category") or "standard_cuda",
            "message": project_scan.get("message", ""),
            "input_kind": project_scan.get("input_kind", "unknown"),
            "compile_strategy": project_scan.get("compile_strategy", ""),
            "generated_build_plan": getattr(context, "generated_build_plan", False),
            "generated_makefile_path": getattr(context, "generated_makefile_path", None),
            "cu_file_count": len(project_scan.get("cu_files", [])),
            "hip_file_count": len(project_scan.get("hip_files", [])),
            "cpp_file_count": len(project_scan.get("cpp_files", [])),
            "header_file_count": len(project_scan.get("header_files", [])),
            "build_system": project_scan.get("build_system_detected", "none"),
            "project_inventory": project_scan.get("project_inventory") or getattr(context, "project_inventory", {}),
        }

    # 3. Translation Summary
    translation_summary = {
        "hipify_clang_status": "SUCCESS" if getattr(context, "hipify_output_path", None) else "FAILED",
        "sca_findings": getattr(context, "sca_result", {})
    }

    # 4. Compilation History
    logs_dir = workspace_path / "logs"
    compilation_history = []
    if logs_dir.exists():
        for idx, log_file in enumerate(sorted(logs_dir.glob("compile_attempt_*.log"))):
            try:
                content = log_file.read_text(encoding="utf-8", errors="replace")
                record = {
                    "attempt": idx + 1,
                    "log_file": log_file.name,
                    "stdout_stderr_summary": content,
                }
                command = re.search(r"^Command: (.*)$", content, re.MULTILINE)
                cache_key = re.search(r"^Cache key: (.*)$", content, re.MULTILINE)
                cache_state = re.search(r"^Cache: (hit|miss)$", content, re.MULTILINE)
                record.update({
                    "command": command.group(1) if command else "",
                    "cache_key": cache_key.group(1) if cache_key else "",
                    "cache_hit": cache_state.group(1) == "hit" if cache_state else None,
                })
                compilation_history.append(record)
            except Exception:
                pass

    recorded_history = getattr(context, "compilation_history", []) or []
    by_attempt = {record["attempt"]: record for record in compilation_history}
    for recorded in recorded_history:
        by_attempt.setdefault(recorded["attempt"], {}).update(recorded)
    compilation_history = [by_attempt[key] for key in sorted(by_attempt)]

    # 5. AI Agent Activity
    analysis_summaries = []
    patch_summaries = []
    research_summaries = []
    
    journal = getattr(context, "migration_journal", [])
    for entry in journal:
        if entry.get("analysis_summary"):
            analysis_summaries.append({
                "attempt": entry.get("attempt"),
                "summary": entry.get("analysis_summary"),
                "root_cause": entry.get("root_cause"),
                "repair_plan": entry.get("repair_plan")
            })
        if entry.get("patch_summary"):
            patch_summaries.append({
                "attempt": entry.get("attempt"),
                "summary": entry.get("patch_summary"),
                "files_modified": entry.get("files_modified", [])
            })
        if entry.get("research_summary"):
            research_summaries.append({
                "attempt": entry.get("attempt"),
                "summary": entry.get("research_summary"),
                "findings": entry.get("research_findings", []),
                "recommendations": entry.get("research_recommendations", [])
            })

    # Assemble complete structured report
    report_data = {
        "migration_summary": summary,
        "project_scan": project_scan_json,
        "file_lifecycle": getattr(context, "file_lifecycle", {}),
        "input_project_details": {
            "original_files": original_files,
            "file_hashes": file_hashes
        },
        "translation_summary": translation_summary,
        "compilation_history": compilation_history,
        "ai_agent_activity": {
            "analysis_summaries": analysis_summaries,
            "patch_summaries": patch_summaries,
            "research_summaries": research_summaries
        },
        "migration_metrics": {
            "cuda_apis_detected": getattr(context, "cuda_apis_detected", 0),
            "cuda_apis_converted": getattr(context, "cuda_apis_converted", 0),
            "cuda_apis_remaining": getattr(context, "cuda_apis_remaining", 0),
            "files_modified_count": len(getattr(context, "files_modified", [])),
            "files_modified": getattr(context, "files_modified", []),
            "patch_iterations": actual_retries,
            "compile_success": getattr(context, "compilation_success", False),
            "error_category": getattr(context, "error_category", "NONE"),
            "total_migration_duration_seconds": duration_seconds,
            "initial_cuda_apis_detail": getattr(context, "initial_cuda_apis_detail", {}),
            "remaining_cuda_apis_detail": getattr(context, "remaining_cuda_apis_detail", {}),
            "target_architecture": getattr(context, "target_gpu_architecture", "gfx90a"),
            "repair_budget": getattr(context, "retry_budget", 0),
            "compile_attempts": len(compilation_history),
            "ai_repair_cycles": len(analysis_summaries),
            "failed_stage": getattr(context, "failed_stage", None),
            "main_error": getattr(context, "main_error", None),
            "skipped_ai_repair_reason": get_skipped_ai_repair_reason(context),
            "workflow_trace": getattr(context, "workflow_trace", []),
            "stage_timings": getattr(context, "stage_timings", {}),
            "ai_context_truncated": getattr(context, "ai_context_truncated", False),
            "compile_command": getattr(context, "last_compile_command", "") or "",
            "source_files_compiled": getattr(context, "source_files", []) or [],
        },
        "migration_journal_excerpt": journal,
        "generated_artifacts": [
            "generated/",
            "patches/",
            "logs/",
            "reports/migration_report.md",
            "reports/migration_report.json",
            "reports/git_patch.diff",
            "README.txt"
        ],
        "performance_profiling": {}
    }
    if (workspace_path / "generated" / "Makefile.hipforge").exists():
        report_data["generated_artifacts"].insert(
            1, "generated/Makefile.hipforge (auto-generated build plan)"
        )

    patch_audit = getattr(context, "patch_validations", None) or []
    if not patch_audit and getattr(context, "patch_validation", None):
        patch_audit = [context.patch_validation]
    report_data["patch_audit"] = [{
        "target_file": item.get("target_file"),
        "accepted": item.get("accepted", False),
        "reason": item.get("reason", ""),
        "changed_lines": item.get("changed_lines", 0),
        "diff": item.get("diff", ""),
        "before_hash": item.get("before_hash", ""),
        "after_hash": item.get("after_hash", ""),
        "arch_warning": item.get("arch_warning"),
    } for item in patch_audit]

    # AI Mode & repair status
    from app.config.settings import settings
    ai_mode = "mock" if settings.USE_MOCK_AI else "real"
    ai_repair_status = _ai_repair_status(context, len(analysis_summaries))
    final_workflow_state = _final_workflow_state(context)
    compiler_mode = getattr(context, "compiler_mode", "real")
    compile_status = getattr(context, "compile_status", "NOT_RUN")
    generated_artifact_path = f"exports/{migration_id}.zip"

    # Inject required fields at the top-level
    report_data["final_workflow_state"] = final_workflow_state
    report_data["target_architecture"] = getattr(context, "target_gpu_architecture", "gfx90a")
    report_data["input_kind"] = project_scan_json.get("input_kind", "unknown")
    report_data["build_system"] = project_scan_json.get("build_system", "none")
    report_data["compiler_mode"] = compiler_mode
    report_data["compile_command"] = getattr(context, "last_compile_command", "")
    report_data["actual_compiled_architecture"] = _actual_compiled_architecture(context)
    report_data["compile_status"] = compile_status
    report_data["translation_status"] = "PASSED" if bool(getattr(context, "hipify_output_path", None)) else "FAILED"
    report_data["static_validation_status"] = getattr(context, "static_validation_status", "NOT_RUN")
    report_data["local_amd_hardware_required"] = False
    report_data["note"] = "Local AMD hardware is not required for translation and cross-compilation."
    report_data["validation_confidence_level"] = getattr(context, "validation_confidence", "LOW")
    report_data["runtime_validation_status_val"] = getattr(context, "runtime_validation_status", "NOT_RUN")
    report_data["ai_mode"] = ai_mode
    report_data["ai_repair_status"] = ai_repair_status
    report_data["main_error_val"] = getattr(context, "main_error", "") or getattr(context, "last_compile_stderr", "") or ""
    report_data["error_category_val"] = getattr(context, "error_category", "NONE")
    report_data["recommended_next_action_val"] = next_action
    report_data["generated_artifact_path"] = generated_artifact_path
    report_data["report_generated_timestamp"] = now_str

    report_data["environment_summary"] = {
        "preflight_status": preflight_report.get("overall_status"),
        "health_score": preflight_report.get("health_score"),
        "readiness": preflight_report.get("readiness"),
        "critical_failures": preflight_report.get("critical_failures", []),
        "warnings": preflight_report.get("warnings", []),
        "recommended_fixes": preflight_report.get("recommended_fixes", []),
    }
    lesson_matched = getattr(context, "lesson_matched", None)
    report_data["learning_summary"] = lesson_matched or {
        "lesson_matched": False,
        "message": "No previous knowledge was used for this migration."
    }

    report_data["final_summary"] = {
        "environment_summary": preflight_report.get("readiness", "n/a"),
        "migration_summary": status,
        "compile_summary": "PASSED" if getattr(context, "compilation_success", False) else "FAILED or SKIPPED",
        "ai_usage_summary": {
            "requests_recorded": len(analysis_summaries) + len(patch_summaries) + len(research_summaries),
            "token_usage": "not captured by current client instrumentation",
        },
        "repair_iterations": actual_retries,
        "elapsed_time_seconds": duration_seconds,
        "failure_category": failure_category,
        "recommended_next_action": next_action,
        "target_architecture": getattr(context, "target_gpu_architecture", "gfx90a"),
        "actual_compiled_architecture": _actual_compiled_architecture(context),
        "last_compile_command": getattr(context, "last_compile_command", "N/A"),
        "repair_budget": getattr(context, "retry_budget", 0),
        "compile_attempts": len(compilation_history),
        "ai_repair_cycles": len(analysis_summaries),
        "failed_stage": getattr(context, "failed_stage", None),
        "main_error": getattr(context, "main_error", None),
        "skipped_ai_repair_reason": get_skipped_ai_repair_reason(context),
    }

    report_data["validation_confidence"] = {
        "validation_confidence": getattr(context, "validation_confidence", "LOW"),
        "validation_confidence_reason": getattr(context, "validation_confidence_reason", ""),
        "compile_validation_status": status,
        "runtime_validation_enabled": getattr(context, "runtime_validation_enabled", False),
        "runtime_validation_status": getattr(context, "runtime_validation_status", "NOT_CONFIGURED"),
        "runtime_validation_reason": getattr(context, "runtime_validation_reason", ""),
        "profiling_status": getattr(context, "profiling_status", "NOT_CONFIGURED"),
        "launcher_expects_device_pointers": getattr(context, "launcher_expects_device_pointers", "N/A"),
        "runtime_execution_performed": "Yes" if getattr(context, "runtime_validation_status", "NOT_CONFIGURED") == "PASSED" else "No",
        "validation_confidence_type": "runtime-validated" if getattr(context, "runtime_validation_status", "NOT_CONFIGURED") == "PASSED" else "compile-only",
        "kernel_launch_error_checks": getattr(context, "kernel_launch_error_checks", "none"),
        "synchronization_status": getattr(context, "synchronization_status", "none"),
    }

    def make_serializable(obj):
        if hasattr(obj, "model_dump"):
            return make_serializable(obj.model_dump())
        if hasattr(obj, "dict") and callable(obj.dict):
            return make_serializable(obj.dict())
        if isinstance(obj, dict):
            return {k: make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [make_serializable(x) for x in obj]
        if isinstance(obj, tuple):
            return tuple(make_serializable(x) for x in obj)
        return obj

    try:
        serializable_report = make_serializable(report_data)
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(serializable_report, f, indent=2)
        logger.info("[ReportService] JSON report generated: %s", json_file)
    except Exception as exc:
        logger.error("[ReportService] Failed to write JSON report: %s", exc)


async def generate_git_patch(migration_id: str, context: Any = None) -> None:
    """
    Computes a unified diff between the original source files in input/
    and their latest translated or patched versions in the workspace,
    and writes it to reports/git_patch.diff.
    """
    workspace_path = get_workspace_path(migration_id)
    reports_dir = workspace_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    patch_file = reports_dir / "git_patch.diff"

    input_dir = workspace_path / "input"
    diff_lines = []

    patch_audit = (getattr(context, "patch_validations", None) or []) if context else []
    if not patch_audit and context is not None and getattr(context, "patch_validation", None):
        patch_audit = [context.patch_validation]
    for item in patch_audit:
        if item.get("accepted") and item.get("diff"):
            diff_lines.append(item["diff"])
            if not item["diff"].endswith("\n"):
                diff_lines.append("\n")

    if not diff_lines and input_dir.exists():
        for orig_file in input_dir.iterdir():
            if not orig_file.is_file():
                continue

            orig_name = orig_file.name
            try:
                orig_content = orig_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            final_content = _get_final_source(workspace_path, orig_name)
            if final_content is None:
                # Fallback: if no final source is generated, compare against empty or skip
                continue

            # Compute diff
            orig_list = orig_content.splitlines(keepends=True)
            final_list = final_content.splitlines(keepends=True)

            diff = difflib.unified_diff(
                orig_list,
                final_list,
                fromfile=f"a/input/{orig_name}",
                tofile=f"b/generated/{Path(orig_name).stem}.hip"
            )
            diff_lines.extend(list(diff))

    if not diff_lines:
        diff_lines = ["# No modifications made or no translated source files found.\n"]

    try:
        patch_file.write_text("".join(diff_lines), encoding="utf-8")
        logger.info("[ReportService] Git patch generated: %s", patch_file)
    except Exception as exc:
        logger.error("[ReportService] Failed to write git patch: %s", exc)


async def write_history_summary(migration_id: str, context: Any, *, failed: bool = False) -> None:
    """
    Writes a lightweight durable history summary to workspace/history/<migration_id>.json.

    Called after report generation (normal path) or on terminal failure.
    Never raises — history write must not abort report generation.

    ponytail: flat history/ dir at workspace root so list = one glob, no date-tree traversal.
    """
    root_path_str = os.getenv("WORKSPACE_PATH") or "workspace"
    history_dir = Path(root_path_str) / "history"
    try:
        history_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.error("[HistoryService] Cannot create history dir: %s", exc)
        return

    history_file = history_dir / f"{migration_id}.json"

    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    workspace_path = get_workspace_path(migration_id)
    report_md_path = str(workspace_path / "reports" / "migration_report.md")
    report_json_path = str(workspace_path / "reports" / "migration_report.json")
    artifact_path = str(workspace_path / "exports" / "HIPForge_Migration.zip")

    # Gather input file metadata without reading file contents
    input_dir = workspace_path / "input"
    input_name = None
    input_kind = "unknown"
    file_count = 0
    if input_dir.exists():
        files = [f for f in input_dir.iterdir() if f.is_file()]
        file_count = len(files)
        if files:
            input_name = files[0].name

    project_scan = getattr(context, "project_scan", None) or {}
    if not input_kind or input_kind == "unknown":
        input_kind = project_scan.get("input_kind") or project_scan.get("category") or "unknown"

    # Count generated files
    generated_dir = workspace_path / "generated"
    generated_file_count = 0
    if generated_dir.exists():
        generated_file_count = sum(1 for f in generated_dir.rglob("*") if f.is_file())

    main_error = getattr(context, "main_error", "") or ""
    if not main_error:
        main_error = (getattr(context, "failure_reason", "") or "")[:500]

    final_state = "FAILED" if (failed or getattr(context, "current_state", None) == "FAILED") else "COMPLETED"

    summary = {
        "job_id": migration_id,
        "created_at": getattr(context, "start_time", now_str),
        "finished_at": now_str,
        "input_name": input_name,
        "input_kind": input_kind,
        "target_architecture": getattr(context, "target_gpu_architecture", "gfx90a"),
        "architecture_selection_source": getattr(context, "architecture_selection_source", "unknown"),
        "final_state": final_state,
        "compile_status": getattr(context, "compile_status", "NOT_RUN"),
        "validation_confidence": getattr(context, "validation_confidence", "LOW"),
        "runtime_validation_status": getattr(context, "runtime_validation_status", "NOT_RUN"),
        "translation_analysis_status": "DONE" if getattr(context, "sca_result", None) else "NOT_RUN",
        "error_category": getattr(context, "error_category", "NONE") or "NONE",
        "main_error": main_error[:500] if main_error else None,
        "next_action": getattr(context, "recommended_next_action", "") or None,
        "report_md_path": report_md_path,
        "report_json_path": report_json_path,
        "artifact_path": artifact_path,
        "file_count": file_count,
        "generated_file_count": generated_file_count,
        # Truthful missing-file flags resolved at write time
        "report_missing": failed or not Path(report_md_path).exists(),
        "artifact_missing": failed or not Path(artifact_path).exists(),
    }

    try:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        logger.info("[HistoryService] History summary written: %s", history_file)
    except Exception as exc:
        logger.error("[HistoryService] Failed to write history summary: %s", exc)


async def build_zip(migration_id: str, context: Any = None) -> None:
    """
    Packages generated/, patches/, logs/, reports/ (with report files and git patch),
    and a root README.txt into exports/HIPForge_Migration.zip.
    """
    workspace_path = get_workspace_path(migration_id)
    exports_dir = workspace_path / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    zip_path = exports_dir / "HIPForge_Migration.zip"

    # Create root README.txt inside the workspace temporarily
    readme_file = workspace_path / "README.txt"
    status = _final_workflow_state(context) if context is not None else "UNKNOWN"
    try:
        # Check status key in Redis to include status in README
        redis_status = await redis_client.get(status_key(migration_id))
        if redis_status and context is None:
            status = redis_status
    except Exception:
        pass

    readme_content = (
        f"HIPForge Migration Export Package\n"
        f"=================================\n"
        f"Migration ID: {migration_id}\n"
        f"Status: {status}\n"
        f"Generated At: {datetime.datetime.now(datetime.timezone.utc).isoformat()} UTC\n\n"
        f"Archive Structure:\n"
        f" - generated/ : Converted and patched AMD HIP source files\n"
        f" - patches/   : Intermediary code edits generated by the Patch Agent\n"
        f" - logs/      : Sequential compilation logging attempts\n"
        f" - reports/   : PDF/Markdown/JSON migration reports and unified git patch\n"
        f" - README.txt : Package summary details\n"
    )
    
    try:
        readme_file.write_text(readme_content, encoding="utf-8")
    except Exception as exc:
        logger.error("[ReportService] Failed to create README.txt: %s", exc)

    # Folders to package into zip
    target_dirs = ["generated", "patches", "logs", "artifacts", "reports"]

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_f:
            # 1. Package targets recursively
            for dir_name in target_dirs:
                target_path = workspace_path / dir_name
                if target_path.exists():
                    for file_path in target_path.rglob("*"):
                        if file_path.is_file():
                            # Relativize path to zip file root
                            arcname = file_path.relative_to(workspace_path)
                            zip_f.write(file_path, arcname)

            # 2. Package README.txt
            if readme_file.exists():
                zip_f.write(readme_file, "README.txt")

        logger.info("[ReportService] ZIP archive successfully compiled at %s", zip_path)
    except Exception as exc:
        logger.error("[ReportService] Failed to compile ZIP archive: %s", exc)
    finally:
        # Clean up temporary README.txt from workspace root
        if readme_file.exists():
            try:
                os.remove(readme_file)
            except Exception:
                pass
