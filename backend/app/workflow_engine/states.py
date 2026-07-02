"""
backend/app/workflow_engine/states.py

State handler functions for the HIPForge Workflow Engine.

Each handler receives a WorkflowContext, performs its work, mutates context
fields as needed, and returns the string name of the next state.

Rule (per AGENT_RULES.md Rule 10):
  Only HIPIFY, SCA, and COMPILING are implemented here (Session 8.4).
  All other handlers remain as stubs — do NOT wire AI agents yet.
"""

import logging
import os
from pathlib import Path

from app.workflow_engine.context import WorkflowContext

logger = logging.getLogger("states")


# ---------------------------------------------------------------------------
# Unchanged stub handlers (do not modify)
# ---------------------------------------------------------------------------

async def handle_queued(context: WorkflowContext) -> str:
    return "PREPARING"


async def handle_preparing(context: WorkflowContext) -> str:
    return "HIPIFY"


# ---------------------------------------------------------------------------
# HIPIFY — Stage 3 of the pipeline
# docs/26_JOB_LIFECYCLE.md §3: runs hipify-clang on all source files,
# writes translated output to workspace generated/ directory.
# Fails hard on error (transitions engine to GENERATING_REPORT via exception).
# ---------------------------------------------------------------------------

async def handle_hipify(context: WorkflowContext) -> str:
    """
    Runs hipify-clang (or mock) on the input CUDA source file.

    Expects the source file to live at:
        workspace_path/input/<any .cu file>

    Writes the translated HIP file to:
        workspace_path/generated/<stem>.hip

    Stores the output path in context.hipify_output_path.
    Raises RuntimeError on hipify failure, which drives the state machine
    to the GENERATING_REPORT (failure) path.
    """
    from app.compiler.hipify_runner import run_hipify

    workspace = Path(context.workspace_path)
    input_dir = workspace / "input"
    generated_dir = workspace / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    # Locate the first .cu or .hip file in the input directory.
    source_file: Path | None = None
    for ext in (".cu", ".hip", ".cpp", ".cuh"):
        candidates = list(input_dir.glob(f"*{ext}"))
        if candidates:
            source_file = candidates[0]
            break

    if source_file is None:
        raise RuntimeError(
            f"HIPIFY: no supported source file found in {input_dir}. "
            "Expected at least one .cu / .hip / .cpp / .cuh file."
        )

    output_path = generated_dir / (source_file.stem + ".hip")

    logger.info(
        "[HIPIFY] Translating %s -> %s", source_file, output_path
    )

    result = run_hipify(str(source_file), str(output_path))

    if not result["success"]:
        error_detail = result.get("stderr") or "hipify-clang returned failure"
        logger.error("[HIPIFY] Translation failed: %s", error_detail)
        raise RuntimeError(f"HIPIFY failed: {error_detail}")

    context.hipify_output_path = result["output_path"]
    logger.info("[HIPIFY] Translation succeeded: %s", context.hipify_output_path)
    return "SCA"


# ---------------------------------------------------------------------------
# SCA — Semantic Compatibility Analyzer (Stage 2.5 of the pipeline)
# docs/26_JOB_LIFECYCLE.md §4: scans translated HIP source for migration risks,
# writes migration_risks.json to workspace artifacts/ directory.
# SCA never fails the pipeline — issues are informational context for AI agents.
# ---------------------------------------------------------------------------

async def handle_sca(context: WorkflowContext) -> str:
    """
    Runs the Semantic Compatibility Analyzer on the translated HIP file.

    Reads from context.hipify_output_path (set by handle_hipify).
    Writes migration_risks.json to workspace_path/artifacts/.
    Stores the full result in context.sca_result.

    The SCA is purely informational — it never aborts the pipeline.
    """
    from app.compiler.sca import analyze, write_migration_risks

    hip_source = context.hipify_output_path
    if not hip_source:
        # Defensive: if HIPIFY was skipped somehow, scan input directly
        workspace = Path(context.workspace_path)
        candidates = list((workspace / "input").glob("*.cu")) + \
                     list((workspace / "input").glob("*.hip"))
        if candidates:
            hip_source = str(candidates[0])
        else:
            logger.warning("[SCA] No source file to scan; skipping SCA.")
            context.sca_result = {"issues": [], "score": 1.0}
            return "COMPILING"

    logger.info("[SCA] Scanning %s for compatibility issues", hip_source)

    result = analyze(hip_source)
    context.sca_result = result

    issue_count = len(result["issues"])
    score = result["score"]
    logger.info(
        "[SCA] Scan complete: %d issue(s) detected, compatibility score=%.4f",
        issue_count, score,
    )

    # Write migration_risks.json to artifacts directory (per spec §2.5)
    artifacts_dir = Path(context.workspace_path) / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    risks_path = artifacts_dir / "migration_risks.json"
    write_migration_risks(result, str(risks_path))
    logger.info("[SCA] migration_risks.json written to %s", risks_path)

    return "COMPILING"


# ---------------------------------------------------------------------------
# COMPILING — Stage 3 of the pipeline
# docs/26_JOB_LIFECYCLE.md §5: runs hipcc on the translated HIP file.
# Stores structured errors in context; sets context.compilation_success.
# state_machine.py reads context.compilation_success to drive branching.
# ---------------------------------------------------------------------------

async def handle_compiling(context: WorkflowContext) -> str:
    """
    Runs hipcc (or mock) on the translated HIP source file.

    Reads from context.hipify_output_path as the primary source.
    Falls back to the first .hip file in generated/ if not set.

    Stores results in:
        context.compilation_success  — True if exit code == 0
        context.compiler_errors      — List[CompilerError] on failure
        context.last_compile_stderr  — Raw stderr string

    Does NOT raise on compilation failure. The failure is communicated
    through context.compilation_success=False, which state_machine.py
    reads to determine the next transition (ANALYZING vs GENERATING_REPORT).
    """
    from app.compiler.hipcc_runner import run_hipcc

    workspace = Path(context.workspace_path)
    generated_dir = workspace / "generated"
    logs_dir = workspace / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Determine source file: prefer hipify output, fall back to generated/
    hip_source = context.hipify_output_path
    if not hip_source or not Path(hip_source).exists():
        candidates = list(generated_dir.glob("*.hip"))
        if candidates:
            hip_source = str(candidates[0])
        else:
            # Last resort: check input/ for .hip files
            candidates = list((workspace / "input").glob("*.hip"))
            hip_source = str(candidates[0]) if candidates else None

    if not hip_source:
        logger.error("[COMPILING] No HIP source file found to compile.")
        context.compilation_success = False
        context.compiler_errors = []
        context.last_compile_stderr = "No HIP source file found for compilation."
        return "ANALYZING"

    # Compile attempt number (1-indexed for human-readable log names)
    attempt_num = context.current_attempt + 1
    binary_path = str(generated_dir / f"output_attempt_{attempt_num:03d}")
    log_path = logs_dir / f"compile_attempt_{attempt_num:03d}.log"

    logger.info(
        "[COMPILING] hipcc on %s (attempt %d of %d)",
        hip_source, attempt_num, context.retry_budget,
    )

    from app.redis.client import redis_client
    from app.redis.keys import metadata_key
    
    target_arch = None
    try:
        metadata = await redis_client.hgetall(metadata_key(context.migration_id))
        target_arch = metadata.get("target_architecture")
    except Exception as exc:
        logger.warning("[COMPILING] Failed to read target architecture from Redis: %s", exc)

    result = run_hipcc(hip_source, binary_path, target_arch=target_arch)

    # Stream compile output to client over WebSocket via compiler_channel Redis channel
    try:
        from app.redis.keys import compiler_channel
        from app.redis.client import redis_client
        import json
        from datetime import datetime, timezone
        
        channel = compiler_channel(context.migration_id)
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        
        for line in stdout.splitlines():
            if line.strip():
                payload = {
                    "type": "compiler_log",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "INFO",
                    "content": line
                }
                await redis_client.publish(channel, json.dumps(payload))
                
        for line in stderr.splitlines():
            if line.strip():
                payload = {
                    "type": "compiler_log",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "ERROR",
                    "content": line
                }
                await redis_client.publish(channel, json.dumps(payload))
    except Exception as exc:
        logger.warning("[COMPILING] Failed to publish compilation stream: %s", exc)

    # Persist compiler log (logs are never overwritten per spec)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"=== HIPForge Compile Attempt {attempt_num} ===\n")
        f.write(f"Source: {hip_source}\n")
        f.write(f"Binary: {binary_path}\n\n")
        f.write("--- stdout ---\n")
        f.write(result.get("stdout", ""))
        f.write("\n--- stderr ---\n")
        f.write(result.get("stderr", ""))
    logger.info("[COMPILING] Log written to %s", log_path)

    # Store results in context
    context.compilation_success = result["success"]
    context.compiler_errors = result.get("errors", [])
    context.last_compile_stderr = result.get("stderr", "")

    if result["success"]:
        logger.info("[COMPILING] Compilation succeeded on attempt %d.", attempt_num)
    else:
        error_count = len(context.compiler_errors)
        logger.warning(
            "[COMPILING] Compilation failed on attempt %d: %d structured error(s).",
            attempt_num, error_count,
        )

    # Return value is not used for COMPILING — state_machine reads
    # context.compilation_success directly to determine the next state.
    return "COMPILING"


# ---------------------------------------------------------------------------
# Stub handlers — not implemented in this session
# ---------------------------------------------------------------------------

async def handle_analyzing(context: WorkflowContext) -> str:
    """
    Runs the Analysis Agent on the most recent compilation failure.

    Reads from context:
        hipify_output_path  — the HIP source file to analyse
        compiler_errors     — structured errors from handle_compiling
        last_compile_stderr — raw stderr for additional context
        current_attempt     — zero-indexed attempt counter
        migration_journal   — prior attempt records (may be empty)

    Writes to context:
        analysis_result     — structured Analysis Agent output dict
        migration_journal   — appends a new journal entry for this attempt

    On success: transitions to PATCHING.
    On failure (invalid JSON / API exhausted): raises RuntimeError so the
    state machine drives the job to GENERATING_REPORT via the failure path.
    """
    from app.agents.analysis_agent import analyze

    # Read source code from the translated HIP file
    hip_source_path = context.hipify_output_path
    source_code = ""
    if hip_source_path:
        try:
            source_code = Path(hip_source_path).read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.warning("[ANALYZING] Could not read HIP source: %s", exc)

    logger.info(
        "[ANALYZING] Starting analysis for attempt %d with %d error(s)",
        context.current_attempt + 1,
        len(context.compiler_errors),
    )

    result = analyze(
        compiler_errors=context.compiler_errors,
        source_code=source_code,
        attempt=context.current_attempt,
        migration_journal=context.migration_journal,
    )

    context.analysis_result = result

    # Append a journal entry so future agents can avoid repeating this strategy
    context.migration_journal.append({
        "attempt": context.current_attempt + 1,
        "compiler_errors": [
            (e.model_dump() if hasattr(e, "model_dump") else e)
            for e in context.compiler_errors
        ],
        "analysis_summary": result.get("summary", ""),
        "root_cause": result.get("root_cause", ""),
        "repair_plan": result.get("repair_plan", []),
    })

    logger.info(
        "[ANALYZING] Analysis complete. confidence=%.2f, repair_steps=%d",
        result.get("confidence", 0.0),
        len(result.get("repair_plan", [])),
    )

    return "PATCHING"


async def handle_patching(context: WorkflowContext) -> str:
    """
    Runs the Patch Agent to produce and persist a corrected HIP source file.

    Reads from context:
        analysis_result     — structured Analysis Agent output (repair_plan, etc.)
        hipify_output_path  — current HIP source file to be patched
        compiler_errors     — structured errors from handle_compiling
        current_attempt     — zero-indexed attempt counter
        migration_journal   — prior attempt records
        patch_history       — raw source strings from prior patches

    Writes to context:
        hipify_output_path  — updated to point at the new patched file
        patched_source_path — same path (kept for audit trail)
        patch_history       — appended with the new patched source string
        current_attempt     — incremented so COMPILING logs attempt N+1

    On success: transitions to COMPILING.
    On failure (empty response / API exhausted): raises RuntimeError so the
    state machine drives the job to GENERATING_REPORT via the failure path.
    """
    from app.agents.patch_agent import patch, _build_patch_metadata

    # ── Read current source ─────────────────────────────────────────────
    source_code = ""
    hip_source_path = context.hipify_output_path
    if hip_source_path:
        try:
            source_code = Path(hip_source_path).read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.warning("[PATCHING] Could not read HIP source: %s", exc)

    if not source_code.strip():
        logger.error("[PATCHING] No source code available to patch.")
        raise RuntimeError(
            "PATCHING: hipify_output_path is unset or points to an empty file."
        )

    # ── Determine filename for patch output ─────────────────────────────
    workspace = Path(context.workspace_path)
    patches_dir = workspace / "patches"
    patches_dir.mkdir(parents=True, exist_ok=True)

    attempt_num = context.current_attempt + 1
    if hip_source_path:
        stem = Path(hip_source_path).stem
        filename = f"{stem}.hip"
    else:
        filename = "kernel.hip"

    patch_path = patches_dir / f"patch_attempt_{attempt_num:03d}_{filename}"

    logger.info(
        "[PATCHING] Generating patch for attempt %d. Output: %s",
        attempt_num, patch_path,
    )

    # ── Call Patch Agent ────────────────────────────────────────────────
    analysis = context.analysis_result or {}

    patched_source = patch(
        source_code=source_code,
        analysis=analysis,
        compiler_errors=context.compiler_errors,
        migration_journal=context.migration_journal,
        previous_patches=context.patch_history,
    )

    # ── Write patched file to workspace ─────────────────────────────────
    patch_path.write_text(patched_source, encoding="utf-8")

    logger.info("[PATCHING] Patched source written to %s", patch_path)

    # ── Build and log patch metadata ─────────────────────────────────────
    metadata = _build_patch_metadata(
        original_source=source_code,
        patched_source=patched_source,
        filename=filename,
        analysis=analysis,
    )
    changed_count = len(metadata["changes"][0]["lines"]) if metadata["changes"] else 0
    logger.info(
        "[PATCHING] Patch metadata: %d line(s) changed. Summary: %s",
        changed_count,
        metadata.get("summary", "")[:120],
    )

    # ── Update context ────────────────────────────────────────────────────
    # Point the next COMPILING stage at the patched file
    context.hipify_output_path = str(patch_path)
    context.patched_source_path = str(patch_path)

    # Track patch history so future Patch Agent calls can avoid repeating changes
    context.patch_history.append(patched_source)

    # Increment attempt counter (COMPILING uses this for log naming)
    context.current_attempt += 1

    return "COMPILING"


async def handle_researching(context: WorkflowContext) -> str:
    """
    Runs the Research Agent to query ROCm/HIP documentation when repair loops are exhausted.

    Reads from context:
        hipify_output_path  - the source code context (to read source strings)
        compiler_errors     - structured compiler errors
        sca_result          - semantic compatibility analyzer result
        migration_journal   - history of attempts

    Writes to context:
        research_context    - formatted summary/findings string
        migration_journal   - appends research findings or updates the latest entry

    On success: transitions to COMPILING (for a final attempt, per transitions.py).
    """
    from app.agents.research_agent import research

    logger.info("[RESEARCHING] Initiating documentation research...")

    # 1. Read current source code
    source_code = ""
    if context.hipify_output_path:
        try:
            source_code = Path(context.hipify_output_path).read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.warning("[RESEARCHING] Could not read HIP source: %s", exc)

    # 2. Formulate query
    query = "general CUDA-to-HIP migration compatibility"
    if context.compiler_errors:
        first_err = context.compiler_errors[0]
        if hasattr(first_err, "message"):
            query = first_err.message
        elif isinstance(first_err, dict) and "message" in first_err:
            query = first_err["message"]
        else:
            query = str(first_err)
    elif context.sca_result and context.sca_result.get("issues"):
        first_issue = context.sca_result["issues"][0]
        if isinstance(first_issue, dict):
            query = first_issue.get("description", first_issue.get("message", "API incompatibility"))
        else:
            query = str(first_issue)

    logger.info("[RESEARCHING] Formulated query: '%s'", query)

    # 3. Invoke Research Agent
    try:
        result = research(
            query=query,
            source_code=source_code,
            compiler_errors=context.compiler_errors,
            migration_journal=context.migration_journal,
        )
    except Exception as exc:
        logger.error("[RESEARCHING] Research Agent invocation failed: %s", exc)
        # Per docs/11_RESEARCH_AGENT.md Failure Handling:
        # "Record the failure. Continue according to the Workflow Engine. Research failure must never corrupt the migration process."
        context.research_context = "Research failed to complete."
        return "COMPILING"

    # 4. Format findings to store in context.research_context
    findings_str = "\n".join(f"- {f}" for f in result.get("findings", []))
    actions_str = "\n".join(f"- {a}" for a in result.get("recommended_actions", []))

    research_summary = (
        f"Research Findings for query '{query}':\n"
        f"Summary: {result.get('summary', '')}\n"
        f"Findings:\n{findings_str}\n"
        f"Recommended Actions:\n{actions_str}"
    )

    context.research_context = research_summary

    # 5. Append research findings to the latest journal entry (if exists) or create a new entry
    # According to docs/12_MIGRATION_JOURNAL.md, the journal has a research_summary field.
    # We can update the last entry in the migration_journal list to include it.
    if context.migration_journal:
        # Update the last entry with the research findings
        context.migration_journal[-1]["research_summary"] = result.get("summary", "")
        context.migration_journal[-1]["research_findings"] = result.get("findings", [])
        context.migration_journal[-1]["research_recommendations"] = result.get("recommended_actions", [])
    else:
        # Fallback: create a new entry if journal is empty
        context.migration_journal.append({
            "attempt": context.current_attempt + 1,
            "research_summary": result.get("summary", ""),
            "research_findings": result.get("findings", []),
            "research_recommendations": result.get("recommended_actions", []),
        })

    logger.info("[RESEARCHING] Research stored in context and migration journal.")
    return "COMPILING"


async def handle_generating_report(context: WorkflowContext) -> str:
    """
    Executes the report generation logic.
    Compiles markdown and JSON reports, generates unified git diffs,
    and packages the resulting workspace into a ZIP archive under exports/.
    """
    from app.services.report_service import (
        generate_markdown_report,
        generate_json_report,
        generate_git_patch,
        build_zip
    )
    
    logger.info("[GENERATING_REPORT] Commencing report generation...")
    migration_id = context.migration_id
    
    try:
        await generate_markdown_report(migration_id, context)
        await generate_json_report(migration_id, context)
        await generate_git_patch(migration_id)
        await build_zip(migration_id)
        logger.info("[GENERATING_REPORT] Report generation complete.")
    except Exception as exc:
        logger.exception("[GENERATING_REPORT] Failed to generate reports: %s", exc)
        
    return "COMPLETED"


async def handle_completed(context: WorkflowContext) -> str:
    return None


async def handle_failed(context: WorkflowContext) -> str:
    return None
