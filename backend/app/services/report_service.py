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
from typing import Any, Dict, List, Optional
from pathlib import Path

from app.workspace.manager import get_workspace_path
from app.redis.client import redis_client
from app.redis.keys import status_key

logger = logging.getLogger("report_service")


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


async def generate_markdown_report(migration_id: str, context: Any) -> None:
    """
    Generates reports/migration_report.md summarizing the migration session,
    metrics, compiler history, and AI activities.
    """
    workspace_path = get_workspace_path(migration_id)
    reports_dir = workspace_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / "migration_report.md"

    status = "SUCCESS" if getattr(context, "compilation_success", False) else "FAILED"
    actual_retries = getattr(context, "current_attempt", 0)

    # Calculate timestamps
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    start_time = getattr(context, "start_time", now_str)
    
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
                snippet = content[-400:] if len(content) > 400 else content
                log_summaries.append(f"**{log_file.name}**:\n```\n{snippet.strip()}\n```")
            except Exception:
                pass

    # Build markdown report content
    lines = [
        f"# HIPForge Migration Report",
        f"",
        f"## 1. Migration Summary",
        f"- **Migration ID**: `{migration_id}`",
        f"- **Status**: `{status}`",
        f"- **Start Time**: `{start_time}`",
        f"- **End Time**: `{now_str}`",
        f"- **Target GPU Architecture**: `{getattr(context, 'target_gpu_architecture', 'gfx90a')}`",
        f"- **Retry Budget**: `{getattr(context, 'retry_budget', 0)}`",
        f"- **Actual Retries**: `{actual_retries}`",
        f"",
        f"## 2. Input Project Details",
        f"- **Original Files Uploaded**:"
    ]
    
    for f in original_files:
        h = compute_file_hash(input_dir / f)
        lines.append(f"  - `{f}` (SHA-256: `{h}`)")

    lines.extend([
        f"",
        f"## 3. Translation Summary",
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
        f"## 4. Compilation History",
    ])
    if log_summaries:
        lines.extend(log_summaries)
    else:
        lines.append("- No compilation logs recorded.")

    lines.extend([
        f"",
        f"## 5. AI Agent Activity",
    ])
    
    # Summarize from Migration Journal
    journal = getattr(context, "migration_journal", [])
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
    workspace_path = get_workspace_path(migration_id)
    reports_dir = workspace_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_file = reports_dir / "migration_report.json"

    status = "SUCCESS" if getattr(context, "compilation_success", False) else "FAILED"
    actual_retries = getattr(context, "current_attempt", 0)

    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    start_time = getattr(context, "start_time", now_str)

    # 1. Migration Summary
    summary = {
        "migration_id": migration_id,
        "status": status,
        "start_time": start_time,
        "end_time": now_str,
        "duration_seconds": 0.0,  # can calculate in future
        "input_method": "single_file",
        "target_gpu_architecture": getattr(context, "target_gpu_architecture", "gfx90a"),
        "retry_budget": getattr(context, "retry_budget", 0),
        "actual_retries": actual_retries,
        "migration_mode": getattr(context, "migration_mode", "Balanced")
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
                compilation_history.append({
                    "attempt": idx + 1,
                    "log_file": log_file.name,
                    "stdout_stderr_summary": content[-400:] if len(content) > 400 else content
                })
            except Exception:
                pass

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

    try:
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
        logger.info("[ReportService] JSON report generated: %s", json_file)
    except Exception as exc:
        logger.error("[ReportService] Failed to write JSON report: %s", exc)


async def generate_git_patch(migration_id: str) -> None:
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

    if input_dir.exists():
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


async def build_zip(migration_id: str) -> None:
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
    status = "UNKNOWN"
    try:
        # Check status key in Redis to include status in README
        redis_status = await redis_client.get(status_key(migration_id))
        if redis_status:
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
    target_dirs = ["generated", "patches", "logs", "reports"]

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
