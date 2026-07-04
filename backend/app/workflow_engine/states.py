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
import json
from pathlib import Path

from app.workflow_engine.context import WorkflowContext

logger = logging.getLogger("states")

PATCH_CACHE_DIR = Path("workspace/.cache/patches")

def get_cached_patch(unpatched_content: str) -> str | None:
    try:
        import hashlib
        h = hashlib.sha256(unpatched_content.encode("utf-8")).hexdigest()
        patch_file = PATCH_CACHE_DIR / f"{h}.txt"
        if patch_file.exists():
            return patch_file.read_text(encoding="utf-8")
    except Exception:
        pass
    return None

def write_cached_patch(unpatched_content: str, patched_content: str):
    try:
        import hashlib
        h = hashlib.sha256(unpatched_content.encode("utf-8")).hexdigest()
        PATCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        patch_file = PATCH_CACHE_DIR / f"{h}.txt"
        patch_file.write_text(patched_content, encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Unchanged stub handlers (do not modify)
# ---------------------------------------------------------------------------

async def handle_queued(context: WorkflowContext) -> str:
    return "PREPARING"


async def handle_preparing(context: WorkflowContext) -> str:
    import zipfile
    workspace = Path(context.workspace_path)
    input_dir = workspace / "input"
    
    zip_files = list(input_dir.glob("*.zip"))
    for zip_path in zip_files:
        logger.info("[PREPARING] Extracting ZIP archive: %s", zip_path)
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(input_dir)
            zip_path.unlink()  # Clean up the zip file
        except Exception as e:
            logger.error("[PREPARING] Failed to extract zip: %s", e)
            raise RuntimeError(f"PREPARING failed to extract zip: {e}")
            
    return "PREFLIGHT"


async def handle_preflight(context: WorkflowContext) -> str:
    """
    Runs environment diagnostics after input preparation and before any migration
    tool is launched. Critical failures abort before HIPIFY, COMPILING, or AI.
    """
    from app.diagnostics import (
        preflight_failure_message,
        recommended_next_action,
        run_preflight,
    )

    logger.info("[PREFLIGHT] Running environment validation for %s", context.migration_id)

    try:
        from app.redis.client import redis_client
        from app.redis.keys import metadata_key

        metadata = await redis_client.hgetall(metadata_key(context.migration_id))
        target_arch = metadata.get("target_architecture") if isinstance(metadata, dict) else None
        if target_arch:
            context.target_gpu_architecture = target_arch
    except Exception as exc:
        logger.warning("[PREFLIGHT] Failed to read migration metadata: %s", exc)

    force_mock_compiler = os.getenv("USE_MOCK_COMPILER", "").strip().lower() in {"1", "true", "yes", "on"}
    force_mock_ai = os.getenv("USE_MOCK_AI", "").strip().lower() in {"1", "true", "yes", "on"}
    if force_mock_compiler or force_mock_ai:
        from app.config.settings import settings

        old_mock_compiler = settings.USE_MOCK_COMPILER
        old_mock_ai = settings.USE_MOCK_AI
        try:
            if force_mock_compiler:
                settings.USE_MOCK_COMPILER = True
            if force_mock_ai:
                settings.USE_MOCK_AI = True
            report = run_preflight(
                workspace_path=context.workspace_path,
                require_ai=True,
                run_container_checks=False,
            )
        finally:
            settings.USE_MOCK_COMPILER = old_mock_compiler
            settings.USE_MOCK_AI = old_mock_ai
    else:
        report = run_preflight(workspace_path=context.workspace_path, require_ai=True)
    context.preflight_report = report

    artifacts_dir = Path(context.workspace_path) / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    report_path = artifacts_dir / "preflight_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    critical_failures = report.get("critical_failures", [])
    if critical_failures:
        first = critical_failures[0]
        context.infrastructure_error = True
        context.compilation_success = False
        context.error_category = first.get("category") or "ENVIRONMENT_ERROR"
        context.failure_reason = preflight_failure_message(report)
        context.last_compile_stderr = context.failure_reason
        context.recommended_next_action = recommended_next_action(context.error_category, report)
        logger.error("[PREFLIGHT] Validation failed: %s", context.failure_reason)
        raise RuntimeError(context.failure_reason)

    context.error_category = "NONE"
    logger.info(
        "[PREFLIGHT] Validation passed. health_score=%s readiness=%s",
        report.get("health_score"),
        report.get("readiness"),
    )
    return "HIPIFY"


# ---------------------------------------------------------------------------
# HIPIFY — Stage 3 of the pipeline
# docs/26_JOB_LIFECYCLE.md §3: runs hipify-clang on all source files,
# writes translated output to workspace generated/ directory.
# Fails hard on error (transitions engine to GENERATING_REPORT via exception).
# ---------------------------------------------------------------------------

async def handle_hipify(context: WorkflowContext) -> str:
    """
    Runs hipify-clang (or mock) on the input CUDA source files recursively.

    Expects the source files to live at:
        workspace_path/input/...

    Writes the translated HIP files to:
        workspace_path/generated/...

    Stores the primary output path in context.hipify_output_path.
    Raises RuntimeError on hipify failure, which drives the state machine
    to the GENERATING_REPORT (failure) path.
    """
    from app.compiler.hipify_runner import run_hipify

    workspace = Path(context.workspace_path)
    input_dir = workspace / "input"
    generated_dir = workspace / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    # Locate all files recursively in the input directory.
    all_files = [p for p in input_dir.rglob("*") if p.is_file()]
    
    source_files = []
    other_files = []
    
    supported_extensions = (".cu", ".hip", ".cpp", ".cuh", ".hpp", ".h")
    for p in all_files:
        if p.suffix.lower() in supported_extensions:
            source_files.append(p)
        else:
            other_files.append(p)

    if not source_files:
        raise RuntimeError(
            f"HIPIFY: no supported source file found in {input_dir}. "
            "Expected at least one .cu / .hip / .cpp / .cuh file."
        )

    # Copy all other non-supported files directly to the generated directory
    import shutil
    for src in other_files:
        rel_path = src.relative_to(input_dir)
        dest = generated_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        logger.info("[HIPIFY] Copied non-supported file directly: %s -> %s", src, dest)
        
        # Translate CUDA references and compilers in build scripts (Makefile, CMakeLists, etc.)
        filename_lower = src.name.lower()
        if (
            filename_lower in ("makefile", "makefile.txt", "makefile.hip", "cmakelists.txt")
            or src.suffix.lower() in (".mk", ".cmake")
        ):
            try:
                import re
                content = dest.read_text(encoding="utf-8", errors="replace")
                # Replace nvcc compiler references with hipcc
                content = re.sub(r"\bnvcc\b", "hipcc", content)
                # Replace CUDA source extensions (.cu) with HIP (.hip) in build targets
                content = re.sub(r"\b([\w\-_./]+)\.cu\b", r"\1.hip", content)
                dest.write_text(content, encoding="utf-8")
                logger.info("[HIPIFY] Translated build script paths and compiler: %s", dest)
            except Exception as build_err:
                logger.warning("[HIPIFY] Failed to translate build script %s: %s", dest, build_err)

    # Process all discovered source files recursively
    primary_output_path = None
    for src in source_files:
        rel_path = src.relative_to(input_dir)
        dest = generated_dir / rel_path
        
        # Change file extension from .cu to .hip
        if dest.suffix.lower() == ".cu":
            dest = dest.with_suffix(".hip")
            
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info("[HIPIFY] Translating %s -> %s", src, dest)
        result = run_hipify(str(src), str(dest))
        
        if not result["success"]:
            error_detail = result.get("stderr") or "hipify-clang returned failure"
            logger.error("[HIPIFY] Translation failed on %s: %s", src, error_detail)
            raise RuntimeError(f"HIPIFY failed on {src.name}: {error_detail}")
            
        if primary_output_path is None:
            primary_output_path = result["output_path"]

    context.hipify_output_path = primary_output_path
    
    # Save the list of generated source files to Redis and the context
    relative_source_paths = []
    for src in source_files:
        rel_path = src.relative_to(input_dir)
        if rel_path.suffix.lower() == ".cu":
            rel_path = rel_path.with_suffix(".hip")
        relative_source_paths.append(str(rel_path).replace("\\", "/"))
        
    context.source_files = relative_source_paths
    
    try:
        from app.redis.client import redis_client
        from app.redis.keys import metadata_key
        import json
        await redis_client.hset(metadata_key(context.migration_id), "source_files", json.dumps(relative_source_paths))
        logger.info("[HIPIFY] Saved source_files to Redis metadata: %s", relative_source_paths)
    except Exception as redis_err:
        logger.warning("[HIPIFY] Failed to save source_files to Redis metadata: %s", redis_err)
    
    # Run validation and deterministic replacement step immediately after hipify completes
    try:
        from app.compiler.validator import validate_and_replace_cuda_apis
        await validate_and_replace_cuda_apis(context)
    except Exception as e:
        logger.exception("[HIPIFY] Validation stage failed: %s", e)

    logger.info("[HIPIFY] Translation succeeded. Primary path: %s", context.hipify_output_path)
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


def copy_patches_to_generated(workspace_path: Path, generated_dir: Path):
    """
    Finds all generated patch files in workspace/patches/ and copies the latest
    patch for each target file back to its respective location under generated/
    so that make or hipcc compiles the latest patched code.
    """
    patches_dir = workspace_path / "patches"
    if not patches_dir.exists():
        return
        
    import re
    patch_pattern = re.compile(r"^patch_attempt_(\d+)_(.+)$")
    
    latest_patches = {}
    for p in patches_dir.glob("patch_attempt_*"):
        if p.is_file():
            match = patch_pattern.match(p.name)
            if match:
                attempt = int(match.group(1))
                target_name = match.group(2)
                if target_name not in latest_patches or attempt > latest_patches[target_name]["attempt"]:
                    latest_patches[target_name] = {"attempt": attempt, "path": p}
                    
    for target_name, info in latest_patches.items():
        patch_file = info["path"]
        candidates = list(generated_dir.rglob(target_name))
        if candidates:
            for dest in candidates:
                import shutil
                shutil.copy2(patch_file, dest)
                logger.info("[COMPILING] Copied latest patch %s -> %s", patch_file.name, dest)
        else:
            dest = generated_dir / target_name
            import shutil
            shutil.copy2(patch_file, dest)
            logger.info("[COMPILING] Copied patch to generated root %s -> %s", patch_file.name, dest)


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

    # Ensure generated HIP files are copied into the compile workspace before make/hipcc runs
    copy_patches_to_generated(workspace, generated_dir)

    # ── Preflight check before compiling ──────────────────────────────
    import os
    logger.info("[COMPILING] Preflight check: current working directory: %s", os.getcwd())
    logger.info("[COMPILING] Listing files in generated/ recursively:")
    gen_files = list(generated_dir.rglob("*"))
    for f in gen_files:
        if f.is_file():
            logger.info("  - %s", f.relative_to(generated_dir))
            
    # Verify every source file exists
    source_files = getattr(context, "source_files", [])
    if not source_files:
        # Fallback load from Redis metadata
        try:
            from app.redis.client import redis_client
            from app.redis.keys import metadata_key
            import json
            metadata = await redis_client.hgetall(metadata_key(context.migration_id))
            sf_json = metadata.get("source_files")
            if sf_json:
                source_files = json.loads(sf_json)
                context.source_files = source_files
        except Exception as exc:
            logger.warning("[COMPILING] Failed to load source_files from Redis: %s", exc)
            
    if source_files:
        missing_files = []
        for rel_path in source_files:
            file_path = generated_dir / rel_path
            if not file_path.exists():
                missing_files.append(rel_path)
                
        if missing_files:
            error_msg = f"Missing source files: {', '.join(missing_files)}"
            logger.error("[COMPILING] Preflight check failed: %s", error_msg)
            context.compilation_success = False
            context.compiler_errors = []
            context.last_compile_stderr = error_msg
            context.infrastructure_error = True
            context.error_category = "WORKSPACE_ERROR"
            context.failure_reason = error_msg
            raise RuntimeError(error_msg)

    # Save original contents on attempt 1 (current_attempt == 0) and apply any cached successful patches
    if context.current_attempt == 0:
        context.original_contents = {}
        for rel_path in source_files:
            file_path = generated_dir / rel_path
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8", errors="replace")
                context.original_contents[rel_path] = content
                
                # Check for and apply cached patch
                cached_patch = get_cached_patch(content)
                if cached_patch:
                    file_path.write_text(cached_patch, encoding="utf-8")
                    logger.info("[Patch Cache Hit] Automatically applied cached successful patch for: %s", rel_path)

    # Determine source file: check if there's a Makefile first
    hip_source = None
    for makefile_name in ("Makefile", "makefile"):
        makefiles = list(generated_dir.rglob(makefile_name))
        if makefiles:
            hip_source = str(makefiles[0])
            break
            
    if not hip_source:
        hip_source = context.hipify_output_path
        if not hip_source or not Path(hip_source).exists():
            candidates = list(generated_dir.rglob("*.hip"))
            if candidates:
                hip_source = str(candidates[0])
            else:
                # Last resort: check input/ for .hip files
                candidates = list((workspace / "input").rglob("*.hip"))
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

    result = run_hipcc(hip_source, binary_path, target_arch=target_arch, workspace_path=context.workspace_path)

    # Stream compile output to client over WebSocket via compiler_channel Redis channel
    try:
        from app.redis.keys import compiler_channel, compiler_log_key
        from app.redis.client import redis_client
        import json
        from datetime import datetime, timezone
        
        channel = compiler_channel(context.migration_id)
        log_list_key = compiler_log_key(context.migration_id)
        
        # Publish and store compilation attempt header
        header_payload = {
            "type": "compiler_log",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "INFO",
            "content": f"=== HIPForge Compile Attempt {attempt_num} ==="
        }
        await redis_client.publish(channel, json.dumps(header_payload))
        await redis_client.rpush(log_list_key, json.dumps(header_payload))

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
                await redis_client.rpush(log_list_key, json.dumps(payload))
                
        for line in stderr.splitlines():
            if line.strip():
                payload = {
                    "type": "compiler_log",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "ERROR",
                    "content": line
                }
                await redis_client.publish(channel, json.dumps(payload))
                await redis_client.rpush(log_list_key, json.dumps(payload))
    except Exception as exc:
        logger.warning("[COMPILING] Failed to publish and store compilation stream: %s", exc)

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
    comp_ok = result["success"]
    compiler_errors = result.get("errors", [])
    last_stderr = result.get("stderr", "")

    if comp_ok:
        logger.info("[COMPILING] Compilation succeeded on attempt %d. Commencing Semantic Post-Validation...", attempt_num)
        try:
            from app.compiler.sca import analyze
            from app.models.compiler_error import CompilerError
            
            sca_result = analyze(hip_source)
            issues = sca_result.get("issues", [])
            high_severity_issues = [iss for iss in issues if iss.severity == "high"]
            
            if high_severity_issues:
                logger.warning(
                    "[COMPILING] Semantic Post-Validation failed: %d High-severity semantic compatibility issue(s) detected.",
                    len(high_severity_issues)
                )
                comp_ok = False
                
                # Convert CompatibilityIssue objects to CompilerError models
                semantic_errors = []
                for iss in high_severity_issues:
                    # Construct clean CompilerError
                    sem_err = CompilerError(
                        file=iss.file or hip_source,
                        line=iss.line if iss.line is not None else 1,
                        column=iss.column if iss.column is not None else 1,
                        message=f"Semantic Validation Error: {iss.description} Recommendation: {iss.recommendation}",
                        code=iss.pattern_id
                    )
                    semantic_errors.append(sem_err)
                
                compiler_errors = semantic_errors
                last_stderr = "Semantic Post-Validation failed: " + "; ".join([e.message for e in semantic_errors])
                
                # Stream these errors to the client compiler logs over websocket so they see the semantic errors!
                try:
                    from app.redis.keys import compiler_channel, compiler_log_key
                    from app.redis.client import redis_client
                    import json
                    from datetime import datetime, timezone
                    
                    channel = compiler_channel(context.migration_id)
                    log_list_key = compiler_log_key(context.migration_id)
                    
                    for err in semantic_errors:
                        payload = {
                            "type": "compiler_log",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "level": "ERROR",
                            "content": f"Semantic Validation Error [{err.code}]: {err.message} at line {err.line}"
                        }
                        await redis_client.publish(channel, json.dumps(payload))
                        await redis_client.rpush(log_list_key, json.dumps(payload))
                except Exception as ws_exc:
                    logger.warning("[COMPILING] Failed to stream semantic errors: %s", ws_exc)
            else:
                logger.info("[COMPILING] Semantic Post-Validation succeeded.")
        except Exception as sca_exc:
            logger.error("[COMPILING] Semantic Post-Validation failed with exception: %s", sca_exc)

    context.compilation_success = comp_ok
    context.compiler_errors = compiler_errors
    context.last_compile_stderr = last_stderr

    # Check for infrastructure/system compilation failures to prevent calling AI agents
    if not comp_ok:
        from app.compiler.error_parser import classify_compiler_error
        category = classify_compiler_error(last_stderr)
        context.error_category = category
        if category not in {"USER_CODE_ERROR", "UNSUPPORTED_FEATURE", "COMPILATION_ERROR"}:
            logger.error("[COMPILING] Non-code compile error detected: %s. Aborting to report generation.", category)
            context.infrastructure_error = True
    else:
        context.error_category = "NONE"

    if context.compilation_success:
        logger.info("[COMPILING] Compilation succeeded on attempt %d.", attempt_num)
        # If compilation succeeded and we had patches, save the patches to cache
        if attempt_num > 1 and getattr(context, "original_contents", None):
            for rel_path, original_content in context.original_contents.items():
                file_path = generated_dir / rel_path
                if file_path.exists():
                    patched_content = file_path.read_text(encoding="utf-8", errors="replace")
                    if patched_content != original_content:
                        write_cached_patch(original_content, patched_content)
                        logger.info("[Patch Cache Write] Successfully cached successful patch for: %s", rel_path)
    else:
        error_count = len(context.compiler_errors)
        logger.warning(
            "[COMPILING] Compilation and/or Semantic Validation failed on attempt %d: %d structured error(s).",
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
    """
    # ── Safeguards ──────────────────────────────────────────────────────────
    stderr_val = context.last_compile_stderr or ""
    
    from app.compiler.error_parser import classify_compiler_error
    classification = classify_compiler_error(stderr_val)
    context.error_category = classification

    # Safeguard 1: Stop immediately on non-code errors
    if classification not in {"USER_CODE_ERROR", "UNSUPPORTED_FEATURE", "COMPILATION_ERROR"}:
        logger.error("[ANALYZING] Non-code/toolchain error detected: %s. Stopping immediately.", classification)
        context.infrastructure_error = True
        context.analysis_result = {
            "confidence": 0.0,
            "root_cause": f"Compilation failed due to a {classification} issue: {stderr_val}",
            "repair_plan": []
        }
        raise RuntimeError(f"Compilation failed due to environment/toolchain issue: {classification}")

    # Safeguard 2: Detect repeated errors
    def are_compiler_errors_identical(errors1, errors2) -> bool:
        if not errors1 and not errors2:
            return False
        if len(errors1) != len(errors2):
            return False
        for e1, e2 in zip(errors1, errors2):
            msg1 = e1.message if hasattr(e1, "message") else e1.get("message", "") if isinstance(e1, dict) else str(e1)
            msg2 = e2.message if hasattr(e2, "message") else e2.get("message", "") if isinstance(e2, dict) else str(e2)
            line1 = e1.line if hasattr(e1, "line") else e1.get("line", 0) if isinstance(e1, dict) else 0
            line2 = e2.line if hasattr(e2, "line") else e2.get("line", 0) if isinstance(e2, dict) else 0
            col1 = e1.column if hasattr(e1, "column") else e1.get("column", 0) if isinstance(e1, dict) else 0
            col2 = e2.column if hasattr(e2, "column") else e2.get("column", 0) if isinstance(e2, dict) else 0
            if msg1 != msg2 or line1 != line2 or col1 != col2:
                return False
        return True

    prev_errors = getattr(context, "previous_compiler_errors", None)
    errors_are_identical = False
    if prev_errors is not None:
        errors_are_identical = are_compiler_errors_identical(context.compiler_errors, prev_errors)

    if (getattr(context, "previous_compile_stderr", None) == context.last_compile_stderr and stderr_val != "") or errors_are_identical:
        logger.warning("[ANALYZING] Same compiler error detected twice in a row. Aborting pipeline.")
        context.infrastructure_error = True
        context.error_category = "MIGRATION_ERROR"
        context.analysis_result = {
            "confidence": 0.0,
            "root_cause": "Compilation failed with the exact same error twice in a row. Infinite loop prevented.",
            "repair_plan": []
        }
        raise RuntimeError("Compilation failed with the exact same error twice in a row. Infinite loop prevented.")

    # Save current stderr/errors to detect repetitions in future iterations
    context.previous_compile_stderr = context.last_compile_stderr
    context.previous_compiler_errors = context.compiler_errors
    # ────────────────────────────────────────────────────────────────────────

    from app.agents.analysis_agent import analyze

    # Read optimized semantic slice around the compiler error
    hip_source_path = context.hipify_output_path
    source_code = ""
    if hip_source_path:
        try:
            # Determine line number of the first compiler error
            error_line = 1
            if context.compiler_errors:
                first_error = context.compiler_errors[0]
                if hasattr(first_error, "line"):
                    error_line = getattr(first_error, "line")
                elif isinstance(first_error, dict) and "line" in first_error:
                    error_line = first_error["line"]
            
            from app.compiler.ast_slicing import get_optimized_error_context
            source_code = get_optimized_error_context(hip_source_path, error_line)
            logger.info("[ANALYZING] Extracted semantic slice around line %d for token optimization.", error_line)
        except Exception as exc:
            logger.warning("[ANALYZING] Could not get semantic context, falling back to full source: %s", exc)
            try:
                source_code = Path(hip_source_path).read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

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

    # Prevent infinite loop if the patch agent doesn't modify the source code
    if patched_source.strip() == source_code.strip():
        logger.warning("[PATCHING] Patch Agent returned unchanged source code. Infinite loop prevented.")
        context.infrastructure_error = True
        context.error_category = "AI_ERROR"
        raise RuntimeError("Patch Agent returned unchanged source code. Infinite loop prevented.")

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
    context.patch_metadata = metadata

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
        context.current_attempt += 1
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
    context.current_attempt += 1
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
