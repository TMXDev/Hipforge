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
import re
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


def is_amd_gpu_available() -> bool:
    """Detects whether AMD GPU hardware is available locally."""
    import os
    import shutil
    import subprocess

    if os.path.exists("/dev/kfd"):
        return True

    for cmd in ("rocminfo", "rocm-smi"):
        if shutil.which(cmd):
            try:
                res = subprocess.run([cmd], capture_output=True, timeout=5)
                if res.returncode == 0:
                    return True
            except Exception:
                pass

    if os.name == "nt":
        try:
            res = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "name"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    line_l = line.lower()
                    if "amd" in line_l or "radeon" in line_l or "rdna" in line_l:
                        return True
        except Exception:
            pass

    return False


async def _run_runtime_validation(context: WorkflowContext) -> None:
    """
    v0 runtime validation hook.

    - Disabled by default (RUNTIME_VALIDATION_ENABLED=false).
    - When disabled: marks context.runtime_validation_status = NOT_RUN.
    - When enabled but compilation failed: marks SKIPPED.
    - When enabled and compile succeeded: runs binary if AMD GPU is available, else marks SKIPPED.
    """
    from app.config.settings import settings
    import subprocess
    import shutil

    enabled = settings.RUNTIME_VALIDATION_ENABLED
    context.runtime_validation_enabled = enabled

    # Determine GPU availability
    gpu_available = is_amd_gpu_available()
    context.gpu_hardware_available = gpu_available

    if not enabled:
        context.runtime_validation_status = "NOT_RUN"
        context.runtime_validation_reason = (
            "Runtime validation is disabled (RUNTIME_VALIDATION_ENABLED=false). "
            "HIPForge v0 reports compile-validated migrations only."
        )
        return

    if not getattr(context, "compilation_success", False):
        context.runtime_validation_status = "SKIPPED"
        context.runtime_validation_reason = "Compilation did not succeed; runtime validation was not run."
        return

    if not gpu_available:
        context.runtime_validation_status = "SKIPPED"
        context.runtime_validation_reason = "Runtime validation skipped because no AMD GPU is available."
        logger.info("[RUNTIME_VALIDATION] Skipped because no AMD GPU is available.")
        return

    # AMD hardware is available — run the binary!
    workspace = Path(context.workspace_path)
    generated_dir = workspace / "generated"
    binaries = sorted(generated_dir.glob("output_attempt_*"))
    if not binaries:
        context.runtime_validation_status = "FAILED"
        context.runtime_validation_reason = "Runtime validation failed: compiled binary not found on disk."
        return

    latest_binary = binaries[-1]
    logger.info("[RUNTIME_VALIDATION] AMD GPU detected. Running binary: %s", latest_binary)

    # Determine if running on host or inside container sandbox
    if shutil.which("hipcc"):
        try:
            res = subprocess.run([str(latest_binary)], capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                context.runtime_validation_status = "PASSED"
                context.runtime_validation_reason = f"Runtime validation passed: binary executed successfully on host AMD GPU. Output:\n{res.stdout}"
            else:
                context.runtime_validation_status = "FAILED"
                context.runtime_validation_reason = f"Runtime validation failed with exit code {res.returncode}. Stderr:\n{res.stderr}"
        except Exception as exc:
            context.runtime_validation_status = "FAILED"
            context.runtime_validation_reason = f"Runtime validation failed: execution exception: {exc}"
    else:
        # Run inside Docker container with GPU access
        try:
            import docker
            client = docker.from_env()
            volumes = {
                os.path.abspath(generated_dir): {"bind": "/workspace", "mode": "rw"}
            }
            container_command = ["/workspace/" + latest_binary.name]
            devices = []
            if os.path.exists("/dev/kfd"):
                devices.append("/dev/kfd:/dev/kfd:rwm")
            if os.path.exists("/dev/dri"):
                devices.append("/dev/dri:/dev/dri:rwm")

            stdout_bytes = client.containers.run(
                image=settings.SANDBOX_IMAGE,
                command=container_command,
                network_mode="none",
                devices=devices,
                volumes=volumes,
                working_dir="/workspace",
                stdout=True,
                stderr=True,
                remove=True,
                timeout=15
            )
            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            context.runtime_validation_status = "PASSED"
            context.runtime_validation_reason = f"Runtime validation passed: binary executed successfully inside Docker AMD GPU. Output:\n{stdout_str}"
        except Exception as exc:
            context.runtime_validation_status = "FAILED"
            context.runtime_validation_reason = f"Runtime validation failed inside Docker: {exc}"


# ---------------------------------------------------------------------------
# Unchanged stub handlers (do not modify)
# ---------------------------------------------------------------------------

async def handle_queued(context: WorkflowContext) -> str:
    return "PREPARING"


async def handle_preparing(context: WorkflowContext) -> str:
    import zipfile
    from app.compiler.project_scanner import check_nested_zip, NESTED_ARCHIVE_INPUT

    workspace = Path(context.workspace_path)
    input_dir = workspace / "input"

    zip_files = list(input_dir.glob("*.zip"))

    # Check for nested ZIPs before extraction
    if check_nested_zip(input_dir):
        msg = "Uploaded archive appears to contain another archive instead of project files."
        logger.error("[PREPARING] %s", msg)
        context.infrastructure_error = True
        context.compilation_success = False
        context.error_category = NESTED_ARCHIVE_INPUT
        context.failure_reason = msg
        raise RuntimeError(msg)

    for zip_path in zip_files:
        logger.info("[PREPARING] Extracting ZIP archive: %s", zip_path)
        # ponytail: record archive size
        archive_size = zip_path.stat().st_size
        context.archive_size_bytes = getattr(context, "archive_size_bytes", 0) + archive_size
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                for info in z.infolist():
                    name = info.filename
                    if ".." in name.split("/") or ".." in name.split("\\"):
                        raise RuntimeError(f"Zip-slip detected: entry '{name}' contains path traversal.")
                    if name.startswith("/") or name.startswith("\\"):
                        raise RuntimeError(f"Absolute path detected in ZIP entry: '{name}'")
                    if len(name) >= 2 and name[1] == ":":
                        raise RuntimeError(f"Absolute Windows path detected in ZIP entry: '{name}'")
                z.extractall(input_dir)
            zip_path.unlink()
        except RuntimeError:
            raise
        except Exception as e:
            logger.error("[PREPARING] Failed to extract zip: %s", e)
            raise RuntimeError(f"PREPARING failed to extract zip: {e}")

    return "PREFLIGHT"


async def handle_preflight(context: WorkflowContext) -> str:
    """
    Runs environment diagnostics AND project scanning before any migration
    tool is launched. Critical failures (env or project) abort before HIPIFY,
    COMPILING, or AI.
    """
    from app.diagnostics import (
        preflight_failure_message,
        recommended_next_action,
        run_preflight,
    )
    from app.workflow_engine.state_machine import publish_event
    await publish_event(context.migration_id, "PREFLIGHT", "started", "Preflight started.")

    # Load target architecture from Redis metadata before build system generation
    try:
        from app.redis.client import redis_client
        from app.redis.keys import metadata_key

        metadata = await redis_client.hgetall(metadata_key(context.migration_id))
        target_arch = metadata.get("target_architecture") if isinstance(metadata, dict) else None
        if target_arch:
            context.target_gpu_architecture = target_arch
    except Exception as exc:
        logger.warning("[PREFLIGHT] Failed to read migration metadata: %s", exc)

    # ── Architecture advisor ──────────────────────────────────────────────────
    # Runs after user arch is loaded from Redis; never overrides user selection.
    from app.compiler.architecture_advisor import advise as _advise_arch
    from app.config.settings import settings as _settings
    _configured_default = getattr(_settings, "DEFAULT_TARGET_ARCH", None)
    _user_arch = context.target_gpu_architecture if context.target_gpu_architecture != "gfx90a" else None
    try:
        _advice = _advise_arch(
            user_arch=_user_arch,
            configured_default=_configured_default,
            workspace_path=context.workspace_path,
        )
        # Only update arch from advisor if user did not provide one
        if _user_arch is None:
            context.target_gpu_architecture = _advice.selected_arch
        context.architecture_advice = _advice.to_dict()
        context.architecture_confidence = _advice.confidence
        context.architecture_warnings = _advice.risk_warnings + _advice.recommended_actions
        context.architecture_selection_source = _advice.selection_source
        logger.info(
            "[PREFLIGHT] Architecture advisor: arch=%s source=%s confidence=%s hints=%s risks=%d",
            _advice.selected_arch, _advice.selection_source, _advice.confidence,
            _advice.cuda_arch_hints, len(_advice.risk_warnings),
        )
    except Exception as _adv_exc:
        logger.warning("[PREFLIGHT] Architecture advisor failed (non-fatal): %s", _adv_exc)
    # ── End architecture advisor ──────────────────────────────────────────────

    logger.info("[PREFLIGHT] Running project scan and environment validation for %s", context.migration_id)

    # ── Project scan (early, before arch check — project issues take priority) ──
    from app.compiler.project_scanner import (
        scan_project,
        project_summary_line,
        NO_PROJECT_FILES,
        NON_CUDA_CPP_PROJECT,
        HEADER_ONLY_INPUT,
        MIXED_CUDA_HIP_PROJECT,
    )

    workspace = Path(context.workspace_path)
    input_dir = workspace / "input"
    scan = scan_project(input_dir)
    summary = project_summary_line(scan)
    await publish_event(context.migration_id, "PREFLIGHT", "project_scanned", f"Project scanned: {summary}")
    context.project_scan = scan
    # Populate structured inventory for reporting
    context.project_inventory = scan.get("project_inventory") or {
        "input_kind": scan.get("input_kind", "unknown"),
        "cuda_source_files": scan.get("cu_files", []),
        "hip_source_files": scan.get("hip_files", []),
        "header_files": scan.get("header_files", []),
        "build_system_detected": scan.get("build_system_detected", "none"),
        "generated_makefile_fallback": scan.get("compile_strategy", "").startswith("generated_"),
    }

    # ponytail: Large-project preflight guard
    from app.config.settings import settings

    archive_size = getattr(context, "archive_size_bytes", 0)
    extracted_size = sum(p.stat().st_size for p in input_dir.rglob("*") if p.is_file())

    cuda_files = scan.get("cu_files", []) + scan.get("cuh_files", [])
    cuda_files_count = len(cuda_files)
    total_files_count = scan.get("file_count", 0)

    distinct_cu_dirs = {Path(p).parent for p in scan.get("cu_files", [])}
    independent_folders_count = len(distinct_cu_dirs)

    # Check candidates (relative paths containing CUDA files)
    candidate_folders = []
    for d in distinct_cu_dirs:
        try:
            rel = Path(d).relative_to(input_dir)
            if str(rel) and str(rel) != ".":
                candidate_folders.append(str(rel))
        except ValueError:
            candidate_folders.append(str(d))

    is_cuda_samples_layout = (independent_folders_count > 5) or any("samples" in Path(d).name.lower() or "0_simple" in Path(d).name.lower() for d in distinct_cu_dirs)

    too_large = False
    large_reasons = []

    if archive_size > settings.max_upload_bytes:
        too_large = True
        large_reasons.append(f"archive size {archive_size} bytes exceeds limit of {settings.max_upload_bytes} bytes")
    if extracted_size > settings.MAX_EXTRACTED_BYTES_FOR_AUTO_MIGRATION:
        too_large = True
        large_reasons.append(f"extracted size {extracted_size} bytes exceeds limit of {settings.MAX_EXTRACTED_BYTES_FOR_AUTO_MIGRATION} bytes")
    if cuda_files_count > settings.MAX_CUDA_FILES_FOR_AUTO_MIGRATION:
        too_large = True
        large_reasons.append(f"number of CUDA files ({cuda_files_count}) exceeds limit of {settings.MAX_CUDA_FILES_FOR_AUTO_MIGRATION}")
    if total_files_count > settings.MAX_TOTAL_FILES_FOR_AUTO_MIGRATION:
        too_large = True
        large_reasons.append(f"number of total files ({total_files_count}) exceeds limit of {settings.MAX_TOTAL_FILES_FOR_AUTO_MIGRATION}")
    if is_cuda_samples_layout:
        too_large = True
        large_reasons.append(f"cuda-samples style layout detected with {independent_folders_count} likely independent project folders")

    if too_large:
        context.infrastructure_error = True
        context.compilation_success = False
        context.error_category = "PROJECT_TOO_LARGE"
        reason_msg = f"Project is too large to auto-migrate. Reasons: {', '.join(large_reasons)}."
        context.failure_reason = reason_msg
        context.last_compile_stderr = reason_msg

        action = "Extract the archive and migrate one CUDA sample/project folder at a time."
        if candidate_folders:
            action += f" Candidate folders containing .cu files: {', '.join(candidate_folders)}."
        context.recommended_next_action = action
        logger.error("[PREFLIGHT] Guard triggered: %s %s", reason_msg, action)
        raise RuntimeError(reason_msg)

    summary = project_summary_line(scan)
    logger.info("[PREFLIGHT] %s", summary)
    logger.info("[PREFLIGHT] Project classification: %s category=%s", scan["message"], scan["category"] or "standard_cuda")
    logger.info("[PREFLIGHT] Compile strategy: %s", scan["compile_strategy"])

    # Fail early for project-level issues that don't need env diagnostics
    category = scan["category"]
    if category == NO_PROJECT_FILES:
        context.infrastructure_error = True
        context.compilation_success = False
        context.error_category = NO_PROJECT_FILES
        context.failure_reason = scan["message"]
        context.last_compile_stderr = scan["message"]
        context.recommended_next_action = "Upload a CUDA project folder or ZIP containing .cu, .hip, .cpp, or Makefile/CMakeLists.txt files."
        logger.error("[PREFLIGHT] %s Summary: %s", scan["message"], summary)
        raise RuntimeError(scan["message"])

    if category == NON_CUDA_CPP_PROJECT:
        context.infrastructure_error = True
        context.compilation_success = False
        context.error_category = NON_CUDA_CPP_PROJECT
        context.failure_reason = scan["message"]
        context.last_compile_stderr = scan["message"]
        context.recommended_next_action = "No CUDA/HIP migration is needed for this project."
        logger.info("[PREFLIGHT] %s Summary: %s", scan["message"], summary)
        raise RuntimeError(scan["message"])

    if category == HEADER_ONLY_INPUT:
        context.infrastructure_error = True
        context.compilation_success = False
        context.error_category = HEADER_ONLY_INPUT
        context.failure_reason = scan["message"]
        context.last_compile_stderr = scan["message"]
        context.recommended_next_action = "Upload a source file (.cu, .hip, .cpp) or a build system for compile validation."
        logger.info("[PREFLIGHT] %s Summary: %s", scan["message"], summary)
        raise RuntimeError(scan["message"])

    # Mixed CUDA/HIP — log it but don't fail, handle_hipify will sort it out
    if category == MIXED_CUDA_HIP_PROJECT:
        logger.info("[PREFLIGHT] %s", scan["message"])

    # ── Compile strategy routing ──────────────────────────────────────────
    strategy = scan["compile_strategy"]

    if strategy == "fail_preflight":
        ep_count = scan.get("entrypoint_count", 0)
        if ep_count > 1:
            ctx_error = "MULTIPLE_ENTRYPOINTS"
            msg = (
                "Multiple possible entry points were found, but no build system was provided. "
                "Add a Makefile/CMakeLists.txt or specify the entry point."
            )
            action = "Add a Makefile/CMakeLists.txt that defines the project build targets, or upload a single .cu file for direct compilation."
        elif ep_count == 0 and scan.get("has_multiple_source_files", False):
            ctx_error = "NO_ENTRYPOINT"
            msg = (
                "No executable entry point was found. "
                "Upload a build system (Makefile/CMakeLists.txt) or specify how this library should be compiled."
            )
            action = "Add a Makefile or CMakeLists.txt to the project root, or upload a single .cu file for direct compilation."
        else:
            # Fallback for single-file strategies that became fail_preflight
            ctx_error = "MISSING_BUILD_SYSTEM"
            msg = "Multiple source files were found, but no build system was provided."
            action = "Add a Makefile or CMakeLists.txt to the project root."
        context.infrastructure_error = True
        context.compilation_success = False
        context.error_category = ctx_error
        context.failure_reason = msg
        context.last_compile_stderr = msg
        context.recommended_next_action = action
        logger.error("[PREFLIGHT] %s Summary: %s", msg, summary)
        raise RuntimeError(msg)

    if strategy.startswith("generated_"):
        from app.compiler.makefile_generator import write_generated_makefile
        target_arch = getattr(context, "target_gpu_architecture", "gfx90a")
        makefile_path = write_generated_makefile(
            workspace_path=workspace,
            scan=scan,
            target_arch=target_arch,
            input_dir=input_dir,
        )
        if makefile_path:
            context.generated_build_plan = True
            context.generated_makefile_path = str(makefile_path)
            logger.info("[PREFLIGHT] Generated build plan: %s", makefile_path)
        logger.info("[PREFLIGHT] Build plan: %s", strategy)
    # ── End project scan ─────────────────────────────────────────────────

    import re
    arch = getattr(context, "target_gpu_architecture", None) or "unknown"
    if not re.match(r'^gfx\d{2,4}[a-z]?$', arch):
        msg = f"Target architecture '{arch}' has an unsupported format. Expected a name like gfx90a, gfx908, gfx906, gfx942, gfx1100."
        logger.error("[PREFLIGHT] %s", msg)
        context.infrastructure_error = True
        context.compilation_success = False
        context.error_category = "UNSUPPORTED_FEATURE"
        context.failure_reason = msg
        context.last_compile_stderr = msg
        context.recommended_next_action = "Select a supported architecture: gfx906, gfx908, gfx90a, gfx940, gfx941, gfx942, gfx1030, gfx1100"
        raise RuntimeError(msg)

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

    # Merge project scan into saved preflight report
    report_with_scan = dict(report)
    report_with_scan["project_scan"] = scan
    report_path.write_text(json.dumps(report_with_scan, indent=2), encoding="utf-8")

    critical_failures = report.get("critical_failures", [])
    if critical_failures:
        first = critical_failures[0]
        context.infrastructure_error = True
        context.compilation_success = False
        context.error_category = first.get("category") or "ENVIRONMENT_ERROR"
        context.failure_reason = preflight_failure_message(report)
        context.last_compile_stderr = context.failure_reason
        context.recommended_next_action = recommended_next_action(context.error_category, report)

        has_compiler_fail = any(
            cf.get("id") in ("hipcc", "docker_sdk", "docker_daemon", "docker_image", "docker_container_start")
            for cf in critical_failures
        )
        if has_compiler_fail:
            context.compiler_mode = "unavailable"
            context.compile_status = "FAILED_SETUP"
        else:
            context.compiler_mode = "test-only" if settings.USE_MOCK_COMPILER else "real"
            context.compile_status = "NOT_RUN"

        from app.compiler.validation_confidence import compute_confidence
        level, reason = compute_confidence(
            hipify_ok=False,
            compile_ok=False,
            compiler_mocked=settings.USE_MOCK_COMPILER,
            tools_missing=(context.compiler_mode == "unavailable")
        )
        context.validation_confidence = level
        context.validation_confidence_reason = reason

        # Publish preflight failed event
        await publish_event(
            context.migration_id,
            "PREFLIGHT",
            "failed",
            f"Preflight validation failed: {context.failure_reason}",
            error_category=context.error_category,
            main_error=context.failure_reason
        )
        logger.error("[PREFLIGHT] Validation failed: %s", context.failure_reason)
        raise RuntimeError(context.failure_reason)

    context.compiler_mode = "test-only" if settings.USE_MOCK_COMPILER else "real"
    context.compile_status = "NOT_RUN"
    context.error_category = "NONE"

    # Publish preflight completed event
    await publish_event(
        context.migration_id,
        "PREFLIGHT",
        "completed",
        f"Preflight validation passed. health_score={report.get('health_score')} readiness={report.get('readiness')}"
    )
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
    from app.compiler.hipify_runner import run_hipify, discover_include_dirs, detect_cuda_arch, detect_cuda_toolkit_path
    from app.workflow_engine.state_machine import publish_event
    from app.config.settings import settings

    workspace = Path(context.workspace_path)
    input_dir = workspace / "input"

    # ponytail: discover include paths, cuda target arch, and cuda toolkit path
    extra_includes = discover_include_dirs(input_dir)
    detected_arch = detect_cuda_arch(input_dir)
    cuda_arch = detected_arch or settings.CUDA_PARSER_ARCH
    cuda_path = detect_cuda_toolkit_path()

    await publish_event(context.migration_id, "HIPIFY", "started", "HIP generation started.")

    generated_dir = workspace / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    # ponytail: apply semantic patches to generated migration workspace
    copy_patches_to_generated(workspace, generated_dir)

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

    # ponytail: compute invocation fingerprint
    import hashlib
    import json
    source_files_hashes = []
    for src in source_files:
        try:
            h = hashlib.sha256(src.read_bytes()).hexdigest()
        except Exception:
            h = "unknown"
        source_files_hashes.append((str(src.relative_to(input_dir)), h))
    fingerprint_data = {
        "sources": sorted(source_files_hashes),
        "extra_includes": sorted(list(extra_includes)),
        "cuda_arch": str(cuda_arch),
        "cuda_path": str(cuda_path)
    }
    fingerprint_str = json.dumps(fingerprint_data, sort_keys=True)
    context.current_hipify_fingerprint = hashlib.sha256(fingerprint_str.encode("utf-8")).hexdigest()


    await publish_event(
        context.migration_id,
        "HIPIFY",
        "file_discovered",
        f"Discovered {len(source_files)} source files for translation.",
        file_paths=[str(p.relative_to(input_dir)).replace("\\", "/") for p in source_files]
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
                # Propagate target architecture if specified
                target_arch = getattr(context, "target_gpu_architecture", None)
                if target_arch:
                    content = re.sub(r"\bhipcc\b(?! --offload-arch=)", f"hipcc --offload-arch={target_arch}", content)
                dest.write_text(content, encoding="utf-8")
                logger.info("[HIPIFY] Translated build script paths and compiler: %s", dest)
            except Exception as build_err:
                logger.warning("[HIPIFY] Failed to translate build script %s: %s", dest, build_err)

    # ponytail: preserve existing .hip files, skip hipify on them
    project_scan = getattr(context, "project_scan", None)
    has_existing_hip = project_scan and project_scan.get("category") in ("EXISTING_HIP_PROJECT", "MIXED_CUDA_HIP_PROJECT")
    hipify_source_count = 0
    copied_hip_count = 0

    # Initialize file lifecycle tracking
    import hashlib
    from app.workflow_engine.state_machine import publish_log
    context.file_lifecycle = {}

    primary_output_path = None

    async def process_file(src):
        nonlocal hipify_source_count, copied_hip_count, primary_output_path
        rel_path = src.relative_to(input_dir)
        dest = generated_dir / rel_path

        # Change file extension from .cu to .hip
        if dest.suffix.lower() == ".cu":
            dest = dest.with_suffix(".hip")

        rel_src_str = str(rel_path).replace("\\", "/")
        rel_dest_str = str(dest.relative_to(workspace)).replace("\\", "/")

        try:
            orig_hash = hashlib.sha256(src.read_bytes()).hexdigest()
        except Exception:
            orig_hash = "unknown"

        context.file_lifecycle[rel_src_str] = {
            "original_path": rel_src_str,
            "generated_path": rel_dest_str,
            "converted": False,
            "modified_by_ai": False,
            "included_in_compile": True,
            "compile_status": "NOT_RUN",
            "failure_reason": None,
            "skipped_reason": None,
            "original_hash": orig_hash,
            "generated_hash": None,
        }

        await publish_log(
            migration_id=context.migration_id,
            message=f"[HIPIFY] Discovered source file: {rel_src_str} (SHA-256: {orig_hash})",
            original_path=rel_src_str,
            stage="HIPIFY",
            status="discovered"
        )

        # ponytail: check if a patch exists for this target file
        has_patch = False
        patches_dir = workspace / "patches"
        if patches_dir.exists():
            patch_files = list(patches_dir.glob(f"patch_attempt_*_{dest.name}"))
            if patch_files:
                has_patch = True

        if has_patch and dest.exists():
            logger.info("[HIPIFY] Consuming patched source for %s from generated workspace: %s", src, dest)
            patched_content = dest.read_text(encoding="utf-8", errors="replace")
            if primary_output_path is None:
                primary_output_path = str(dest)

            try:
                from datetime import datetime, timezone
                provenance_comment = (
                    f"// =========================================================================\n"
                    f"// Generated by HIPForge (AI repaired)\n"
                    f"// Source File: {dest.name}\n"
                    f"// Target Architecture: {getattr(context, 'target_gpu_architecture', 'gfx90a')}\n"
                    f"// Timestamp: {datetime.now(timezone.utc).isoformat()}\n"
                    f"// Validation Status: Refer to final report for compile status\n"
                    f"// =========================================================================\n\n"
                )
                if "Generated by HIPForge" not in patched_content:
                    dest.write_text(provenance_comment + patched_content, encoding="utf-8")
            except Exception as e:
                logger.warning("[HIPIFY] Failed to prepend provenance comments to patched file %s: %s", dest, e)

            context.file_lifecycle[rel_src_str]["converted"] = True
            context.file_lifecycle[rel_src_str]["modified_by_ai"] = True
            try:
                context.file_lifecycle[rel_src_str]["generated_hash"] = hashlib.sha256(dest.read_bytes()).hexdigest()
            except Exception:
                context.file_lifecycle[rel_src_str]["generated_hash"] = orig_hash

            await publish_log(
                migration_id=context.migration_id,
                message=f"[HIPIFY] Consumed patched source from generated workspace: {rel_src_str}",
                original_path=rel_src_str,
                generated_path=rel_dest_str,
                stage="HIPIFY",
                status="generated"
            )
            await publish_event(
                context.migration_id,
                "HIPIFY",
                "hipify_completed",
                f"HIP file written (patched): {rel_dest_str}",
                file_path=rel_dest_str
            )
            return

        # Skip hipify for existing .hip files — copy directly
        if src.suffix.lower() == ".hip":
            dest.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(src, dest)
            logger.info("[HIPIFY] Preserved existing HIP file (no translation): %s -> %s", src, dest)
            copied_hip_count += 1
            if primary_output_path is None:
                primary_output_path = str(dest)

            # Prepend provenance comments to the copied HIP file
            try:
                from datetime import datetime, timezone
                provenance_comment = (
                    f"// =========================================================================\n"
                    f"// Preserved by HIPForge\n"
                    f"// Source File: {rel_src_str}\n"
                    f"// Target Architecture: {getattr(context, 'target_gpu_architecture', 'gfx90a')}\n"
                    f"// Timestamp: {datetime.now(timezone.utc).isoformat()}\n"
                    f"// Validation Status: Refer to final report for compile status\n"
                    f"// =========================================================================\n\n"
                )
                content = dest.read_text(encoding="utf-8", errors="replace")
                if "Preserved by HIPForge" not in content and "Generated by HIPForge" not in content:
                    dest.write_text(provenance_comment + content, encoding="utf-8")
            except Exception as e:
                logger.warning("[HIPIFY] Failed to prepend provenance comments to preserved file %s: %s", dest, e)

            context.file_lifecycle[rel_src_str]["converted"] = True
            context.file_lifecycle[rel_src_str]["skipped_reason"] = "existing_hip_file"
            try:
                context.file_lifecycle[rel_src_str]["generated_hash"] = hashlib.sha256(dest.read_bytes()).hexdigest()
            except Exception:
                context.file_lifecycle[rel_src_str]["generated_hash"] = orig_hash

            await publish_log(
                migration_id=context.migration_id,
                message=f"[HIPIFY] Skipped translation (existing HIP file copied directly): {rel_src_str}",
                original_path=rel_src_str,
                generated_path=rel_dest_str,
                stage="HIPIFY",
                status="skipped",
                reason="existing_hip_file"
            )
            await publish_event(
                context.migration_id,
                "HIPIFY",
                "hipify_completed",
                f"HIP file written (preserved): {rel_dest_str}",
                file_path=rel_dest_str
            )
            return

        dest.parent.mkdir(parents=True, exist_ok=True)

        logger.info("[HIPIFY] Translating %s -> %s", src, dest)
        import asyncio
        result = await asyncio.to_thread(
            run_hipify,
            str(src),
            str(dest),
            extra_include_dirs=extra_includes,
            cuda_parser_arch=cuda_arch,
            cuda_toolkit_path=cuda_path,
        )

        if not result["success"]:
            error_detail = result.get("stderr") or "hipify-clang returned failure"
            context.last_hipify_stderr = error_detail
            logger.error("[HIPIFY] Translation failed on %s: %s", src, error_detail)

            context.file_lifecycle[rel_src_str]["converted"] = False
            context.file_lifecycle[rel_src_str]["failure_reason"] = error_detail

            await publish_log(
                migration_id=context.migration_id,
                message=f"[HIPIFY] File translation failed: {rel_src_str} (Error: {error_detail})",
                original_path=rel_src_str,
                generated_path=rel_dest_str,
                stage="HIPIFY",
                status="failed",
                reason=error_detail
            )

            # ponytail: handle hipify timeout
            if result.get("timeout"):
                from app.config.settings import settings
                context.infrastructure_error = True
                context.compilation_success = False
                context.error_category = "TIMEOUT_ERROR"
                context.failure_reason = error_detail
                context.recommended_next_action = f"The hipify stage timed out after {settings.TIMEOUT_HIPIFY} seconds. Reduce the number of source files or split the project."
            raise RuntimeError(f"HIPIFY failed on {src.name}: {error_detail}")

        if primary_output_path is None:
            primary_output_path = result["output_path"]
        hipify_source_count += 1

        # Prepend honest provenance comments to the generated HIP file
        try:
            from datetime import datetime, timezone
            provenance_comment = (
                f"// =========================================================================\n"
                f"// Generated by HIPForge\n"
                f"// Source File: {rel_src_str}\n"
                f"// Target Architecture: {getattr(context, 'target_gpu_architecture', 'gfx90a')}\n"
                f"// Timestamp: {datetime.now(timezone.utc).isoformat()}\n"
                f"// Validation Status: Refer to final report for compile status\n"
                f"// =========================================================================\n\n"
            )
            content = dest.read_text(encoding="utf-8", errors="replace")
            if "Generated by HIPForge" not in content:
                dest.write_text(provenance_comment + content, encoding="utf-8")
        except Exception as e:
            logger.warning("[HIPIFY] Failed to prepend provenance comments to %s: %s", dest, e)

        context.file_lifecycle[rel_src_str]["converted"] = True
        try:
            context.file_lifecycle[rel_src_str]["generated_hash"] = hashlib.sha256(dest.read_bytes()).hexdigest()
        except Exception:
            pass

        await publish_log(
            migration_id=context.migration_id,
            message=f"[HIPIFY] Successfully generated HIP file: {rel_src_str} -> {rel_dest_str}",
            original_path=rel_src_str,
            generated_path=rel_dest_str,
            stage="HIPIFY",
            status="generated"
        )
        await publish_event(
            context.migration_id,
            "HIPIFY",
            "hipify_completed",
            f"HIP file written: {rel_dest_str}",
            file_path=rel_dest_str
        )

    # Process all files concurrently
    import asyncio
    tasks = [process_file(src) for src in source_files]
    await asyncio.gather(*tasks)

    context.hipify_output_path = primary_output_path

    if copied_hip_count > 0:
        logger.info("[HIPIFY] Preserved %d existing HIP file(s) without re-translation.", copied_hip_count)
    if hipify_source_count > 0:
        logger.info("[HIPIFY] Translated %d CUDA source file(s).", hipify_source_count)

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
            dest.parent.mkdir(parents=True, exist_ok=True)
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
    from app.workflow_engine.state_machine import publish_event
    await publish_event(context.migration_id, "COMPILING", "started", "Compile validation started.")

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
        cmake_lists = list(generated_dir.rglob("CMakeLists.txt"))
        if cmake_lists:
            hip_source = str(cmake_lists[0])
            logger.info("[COMPILING] Using CMakeLists.txt: %s", hip_source)

    if not hip_source:
        makefile_hipforge = generated_dir / "Makefile.hipforge"
        if makefile_hipforge.exists():
            import shutil
            shutil.copy2(makefile_hipforge, generated_dir / "Makefile")
            hip_source = str(generated_dir / "Makefile")
            logger.info("[COMPILING] Using generated build plan: Makefile.hipforge -> Makefile")

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

    # Log files included in compilation
    try:
        from app.workflow_engine.state_machine import publish_log
        for orig_rel_path, f_meta in getattr(context, "file_lifecycle", {}).items():
            await publish_log(
                migration_id=context.migration_id,
                message=f"[COMPILING] Including file in compilation: {f_meta['original_path']} -> {f_meta['generated_path']}",
                original_path=f_meta["original_path"],
                generated_path=f_meta["generated_path"],
                stage="COMPILING",
                status="compiling"
            )
    except Exception as e:
        logger.warning("[COMPILING] Failed to log compiling event: %s", e)

    from app.redis.client import redis_client
    from app.redis.keys import metadata_key

    target_arch = None
    try:
        metadata = await redis_client.hgetall(metadata_key(context.migration_id))
        target_arch = metadata.get("target_architecture") or getattr(context, "target_gpu_architecture", "gfx90a")
    except Exception as exc:
        logger.warning("[COMPILING] Failed to read target architecture from Redis: %s", exc)

    is_makefile = Path(hip_source).name.lower() in ("makefile", "makefile.hipforge")
    is_cmake = Path(hip_source).name.lower() == "cmakelists.txt"
    if is_makefile:
        cmd_str = "make"
        if target_arch:
            cmd_str += f" ARCH={target_arch} AMDGPU_TARGETS={target_arch} GPU_TARGETS={target_arch} HIP_ARCH={target_arch}"
    elif is_cmake:
        cmd_str = "cmake -B build ... && cmake --build build"
    else:
        cmd_str = f"hipcc {hip_source} -o {binary_path} --offload-arch={target_arch or 'gfx90a'}"
        
    await publish_event(
        context.migration_id,
        "COMPILING",
        "compile_command_generated",
        "Compile command generated.",
        compile_command=cmd_str
    )

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
        if "command" in result:
            f.write(f"Command: {result['command']}\n")
        if "returncode" in result:
            f.write(f"Return code: {result['returncode']}\n")
        f.write(f"Cache key: {result.get('cache_key', '')}\n")
        f.write(f"Cache: {'hit' if result.get('cache_hit', False) else 'miss'}\n")
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
    context.last_compile_command = result.get("command", "")
    actual_arch = result.get("actual_arch", "")
    if result.get("success") and not actual_arch:
        arch_match = re.search(r"--offload-arch(?:=|\s+)(gfx\w+)", context.last_compile_command)
        actual_arch = arch_match.group(1) if arch_match else ""
    context.actual_compiled_architecture = actual_arch if result.get("success") else ""
    context.compilation_history = getattr(context, "compilation_history", [])
    context.compilation_history.append({
        "attempt": attempt_num,
        "log_file": log_path.name,
        "command": context.last_compile_command,
        "success": bool(result.get("success")),
        "cache_key": result.get("cache_key", ""),
        "cache_hit": bool(result.get("cache_hit", False)),
        "input_hashes": result.get("input_hashes", {}),
    })

    try:
        from app.redis.client import redis_client
        from app.redis.keys import metadata_key
        await redis_client.hset(
            metadata_key(context.migration_id),
            mapping={
                "actual_compiled_architecture": context.actual_compiled_architecture or "N/A",
                "last_compile_command": context.last_compile_command or ""
            }
        )
    except Exception as redis_err:
        logger.warning("[COMPILING] Failed to save actual_compiled_architecture/last_compile_command to Redis: %s", redis_err)

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
    context.compile_status = "PASSED" if comp_ok else "FAILED"
    context.static_validation_status = "PASSED" if comp_ok else "FAILED"

    # ── Update file lifecycle metadata & publish log events ─────────────
    try:
        from app.workflow_engine.state_machine import publish_log
        for orig_rel_path, f_meta in getattr(context, "file_lifecycle", {}).items():
            f_meta["compile_status"] = "PASSED" if comp_ok else "FAILED"
            if not comp_ok:
                f_meta["failure_reason"] = last_stderr[:500]

            await publish_log(
                migration_id=context.migration_id,
                message=f"[COMPILING] Compile status for {orig_rel_path}: {f_meta['compile_status']}" + (f" (Error: {f_meta['failure_reason']})" if not comp_ok else ""),
                generated_path=f_meta["generated_path"],
                stage="COMPILING",
                status="completed" if comp_ok else "failed",
                reason=None if comp_ok else f_meta["failure_reason"]
            )
    except Exception as e:
        logger.warning("[COMPILING] Failed to update lifecycle/log: %s", e)

    # ── Validation confidence ────────────────────────────────────────────
    from app.compiler.validation_confidence import compute_confidence
    from app.config.settings import settings
    hipify_ok = bool(context.hipify_output_path)
    level, reason = compute_confidence(
        hipify_ok=hipify_ok,
        compile_ok=comp_ok,
        compiler_mocked=settings.USE_MOCK_COMPILER,
        tools_missing=(getattr(context, "compiler_mode", "real") == "unavailable")
    )
    context.validation_confidence = level
    context.validation_confidence_reason = reason

    # ── Runtime validation hook (v0: opt-in only, no binary execution by default) ─
    await _run_runtime_validation(context)

    # Check for infrastructure/system compilation failures to prevent calling AI agents
    if not comp_ok:
        from app.compiler.error_parser import classify_compiler_error
        is_timeout = "timed out" in last_stderr.lower() or any(getattr(e, "code", "") == "TIMEOUT" for e in compiler_errors)
        if is_timeout:
            context.infrastructure_error = True
            context.error_category = "TIMEOUT_ERROR"
            context.failure_reason = last_stderr
            from app.config.settings import settings
            context.recommended_next_action = f"The compile stage timed out after {settings.TIMEOUT_COMPILE} seconds. Check build system dependencies, optimize include paths, or compile files individually."
        else:
            category = classify_compiler_error(last_stderr)
            context.error_category = category
            if category not in {"USER_CODE_ERROR", "UNSUPPORTED_FEATURE", "COMPILATION_ERROR"}:
                logger.error("[COMPILING] Non-code compile error detected: %s. Aborting to report generation.", category)
                context.infrastructure_error = True
                is_missing_dep = (
                    category == "DEPENDENCY_ERROR"
                    or "undefined symbol" in last_stderr.lower()
                    or "undefined reference" in last_stderr.lower()
                    or "cannot find" in last_stderr.lower()
                    or "no such file" in last_stderr.lower()
                )
                if is_missing_dep:
                    context.error_category = "DEPENDENCY_ERROR"
                    from app.compiler.error_parser import extract_missing_symbol
                    missing = extract_missing_symbol(last_stderr)
                    missing_hint = f" Missing: '{missing}'." if missing else ""
                    context.recommended_next_action = (
                        f"AI repair skipped because this appears to be a missing project dependency.{missing_hint} "
                        "Upload the full project folder or include the file/library that defines the missing symbol."
                    )
    else:
        context.error_category = "NONE"

    # Publish compilation outcome events
    if comp_ok:
        await publish_event(
            context.migration_id,
            "COMPILING",
            "compile_passed",
            "Compile validation passed successfully."
        )
    else:
        await publish_event(
            context.migration_id,
            "COMPILING",
            "compile_failed",
            f"Compile validation failed: {last_stderr[:200]}",
            main_error=last_stderr,
            error_category=context.error_category
        )
        if context.error_category == "DEPENDENCY_ERROR":
            await publish_event(
                context.migration_id,
                "COMPILING",
                "dependency_error_detected",
                f"Dependency error: {context.recommended_next_action}",
                error_category="DEPENDENCY_ERROR",
                main_error=last_stderr
            )

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
    from app.workflow_engine.state_machine import publish_event
    await publish_event(context.migration_id, "ANALYZING", "started", "AI repair loop started.")

    # ── Safeguards ──────────────────────────────────────────────────────────
    stderr_val = context.last_compile_stderr or ""

    from app.compiler.error_parser import classify_compiler_error
    classification = classify_compiler_error(stderr_val)
    context.error_category = classification

    # Lesson check: have we seen this error before?
    from app.redis.client import redis_client
    from app.learning.lesson_storage import find_lesson, store_lesson

    lesson = await find_lesson(redis_client, stderr_val)
    if lesson:
        cat = lesson["category"]
        logger.info("[ANALYZING] Lesson matched: %s — skipping AI analysis", cat)
        context.lesson_matched = lesson
        context.infrastructure_error = True
        context.error_category = cat
        context.analysis_result = {
            "confidence": 0.0,
            "root_cause": f"Previous lesson ({cat}): {lesson.get('main_error_text', '')[:200]}",
            "repair_plan": []
        }
        context.recommended_next_action = lesson.get("recommended_action", "See previous lesson.")
        logger.info(
            "[ANALYZING] Lesson matched: %s — AI analysis skipped. Reason: %s",
            cat, lesson.get("patch_skipped_reason", "previous lesson found")
        )
        return

    # Safeguard 1: Stop immediately on non-code errors
    if classification not in {"USER_CODE_ERROR", "UNSUPPORTED_FEATURE", "COMPILATION_ERROR"}:
        logger.error("[ANALYZING] Non-code/toolchain error detected: %s. Stopping immediately.", classification)
        context.infrastructure_error = True
        context.analysis_result = {
            "confidence": 0.0,
            "root_cause": f"Compilation failed due to a {classification} issue: {stderr_val}",
            "repair_plan": []
        }
        # Check if the failure is a missing symbol or missing library/object/source dependency
        is_missing_dep = (
            classification == "DEPENDENCY_ERROR"
            or "undefined symbol" in stderr_val.lower()
            or "undefined reference" in stderr_val.lower()
            or "cannot find" in stderr_val.lower()
            or "no such file" in stderr_val.lower()
        )

        if is_missing_dep:
            classification = "DEPENDENCY_ERROR"
            context.error_category = "DEPENDENCY_ERROR"
            from app.compiler.error_parser import extract_missing_symbol
            missing = extract_missing_symbol(stderr_val)
            missing_hint = f" Missing: '{missing}'." if missing else ""
            context.failure_reason = f"Compilation failed due to missing dependency or symbol: {stderr_val[:300]}"
            context.recommended_next_action = (
                f"AI repair skipped because this appears to be a missing project dependency.{missing_hint} "
                "Upload the full project folder or include the file/library that defines the missing symbol."
            )

        # Publish AI repair skipped event
        await publish_event(
            context.migration_id,
            "ANALYZING",
            "ai_repair_skipped",
            f"AI repair skipped: {context.recommended_next_action or 'Non-code error detected.'}",
            error_category=classification,
            main_error=stderr_val
        )

        # Store lesson so future runs skip faster
        await store_lesson(
            redis_client,
            category=classification,
            stderr=stderr_val,
            target_architecture=getattr(context, "target_gpu_architecture", ""),
            recommended_action=context.recommended_next_action,
            patch_attempted=False,
            patch_skipped_reason=f"{classification} is not a user-code error",
        )
        raise RuntimeError(f"Compilation failed due to environment/toolchain issue: {classification}")

    # Safeguard 1b: UNSUPPORTED_FEATURE with arch pattern → not patchable by AI
    if classification == "UNSUPPORTED_FEATURE":
        import re
        if not context.compiler_errors and re.search(r'gfx\d{4}', stderr_val):
            logger.error("[ANALYZING] Unsupported GPU architecture detected. Skipping AI patching.")
            context.infrastructure_error = True
            context.analysis_result = {
                "confidence": 0.0,
                "root_cause": f"Unsupported GPU architecture: {stderr_val[:200]}",
                "repair_plan": []
            }
            # Publish AI repair skipped event
            await publish_event(
                context.migration_id,
                "ANALYZING",
                "ai_repair_skipped",
                "AI repair skipped: Unsupported GPU architecture.",
                error_category=classification,
                main_error=stderr_val
            )
            await store_lesson(
                redis_client,
                category=classification,
                stderr=stderr_val,
                target_architecture=getattr(context, "target_gpu_architecture", ""),
                recommended_action="Select a supported architecture: gfx906, gfx908, gfx90a, gfx940, gfx941, gfx942, gfx1030, gfx1100",
                patch_attempted=False,
                patch_skipped_reason=f"Architecture {stderr_val} is not supported by ROCm compiler",
            )
            raise RuntimeError(f"Unsupported GPU architecture detected: {stderr_val[:300]}")

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
        # Publish AI repair failed event
        await publish_event(
            context.migration_id,
            "ANALYZING",
            "ai_repair_failed",
            "AI repair failed: Identical compile error repeated twice in a row.",
            error_category="MIGRATION_ERROR",
            main_error=stderr_val
        )
        # Store lesson so future runs immediately skip
        from app.redis.client import redis_client
        from app.learning.lesson_storage import store_lesson
        await store_lesson(
            redis_client,
            category="MIGRATION_ERROR",
            stderr=stderr_val,
            target_architecture=getattr(context, "target_gpu_architecture", ""),
            recommended_action="The same error repeated after a patch attempt. Manual review required.",
            patch_attempted=True,
            patch_skipped_reason="Identical error persisted after patching",
        )
        raise RuntimeError("Compilation failed with the exact same error twice in a row. Infinite loop prevented.")

    # Save current stderr/errors to detect repetitions in future iterations
    context.previous_compile_stderr = context.last_compile_stderr
    context.previous_compiler_errors = context.compiler_errors
    # ────────────────────────────────────────────────────────────────────────

    from app.agents.analysis_agent import analyze

    # Read optimized semantic slice around the compiler error
    hip_source_path = context.hipify_output_path
    if context.compiler_errors:
        workspace = Path(context.workspace_path)
        generated_dir = workspace / "generated"
        for err in context.compiler_errors:
            err_file = err.file
            resolved_path = Path(err_file)
            if not resolved_path.is_absolute():
                resolved_path = generated_dir / err_file
            if resolved_path.exists():
                hip_source_path = str(resolved_path)
                logger.info("[ANALYZING] Target file for analysis selected from compiler error: %s", hip_source_path)
                break
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

    # ── Build focused repair-context packet (req #1) ─────────────────────────
    import hashlib
    import shutil

    # Detect ROCm and compiler versions lazily (best-effort, no subprocess on CI)
    rocm_version: str | None = None
    compiler_version: str | None = None
    try:
        rocm_smi = shutil.which("rocminfo") or shutil.which("rocm-smi")
        if rocm_smi:
            import subprocess
            rv = subprocess.run([rocm_smi, "--version"], capture_output=True, text=True, timeout=3)
            rocm_version = (rv.stdout or rv.stderr).strip().splitlines()[0][:80] if rv.returncode == 0 else None
    except Exception:
        pass
    try:
        hipcc_path = shutil.which("hipcc")
        if hipcc_path:
            import subprocess
            cv = subprocess.run([hipcc_path, "--version"], capture_output=True, text=True, timeout=3)
            compiler_version = (cv.stdout or cv.stderr).strip().splitlines()[0][:80] if cv.returncode == 0 else None
    except Exception:
        pass

    repair_context = {
        "failed_stage": "COMPILING",
        "compile_command": getattr(context, "last_compile_command", ""),
        "raw_stderr": context.last_compile_stderr or "",
        "target_arch": getattr(context, "target_gpu_architecture", "gfx90a"),
        "rocm_version": rocm_version,
        "compiler_version": compiler_version,
        "source_file": hip_source_path or "",
        "remaining_budget": getattr(context, "retry_budget", 0) - context.current_attempt,
    }
    context.repair_context = repair_context

    # ── Patch fingerprint dedup (req #6) ─────────────────────────────────────
    # Skip AI if we've already tried this exact (stderr, source, attempt) combo.
    stderr_hash = hashlib.sha256((context.last_compile_stderr or "").encode()).hexdigest()[:16]
    source_hash = hashlib.sha256(source_code.encode()).hexdigest()[:16]
    fingerprint = (stderr_hash, source_hash, context.current_attempt)
    seen = getattr(context, "seen_patch_fingerprints", set())
    if fingerprint in seen:
        logger.warning(
            "[ANALYZING] Duplicate patch fingerprint detected (attempt %d). Skipping AI to prevent loop.",
            context.current_attempt,
        )
        context.infrastructure_error = True
        context.error_category = "AI_ERROR"
        context.analysis_result = {
            "confidence": 0.0,
            "diagnosis": "Duplicate patch fingerprint — same error and source seen before at this attempt index.",
            "root_cause": "Duplicate patch attempt detected. Identical error and source observed before.",
            "summary": "Duplicate patch fingerprint — stopping to prevent infinite loop.",
            "affected_files": [], "affected_lines": [], "repair_plan": [], "requires_human": True,
            "blocker": "Same (stderr, source, attempt) fingerprint repeated.",
        }
        raise RuntimeError("Duplicate patch fingerprint — infinite loop prevented.")
    seen.add(fingerprint)
    context.seen_patch_fingerprints = seen
    # ─────────────────────────────────────────────────────────────────────────

    # ponytail: call analyze with timeout
    import asyncio
    from app.config.settings import settings
    timeout = getattr(settings, "TIMEOUT_AI_ANALYSIS", 60)
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                analyze,
                compiler_errors=context.compiler_errors,
                source_code=source_code,
                attempt=context.current_attempt,
                migration_journal=context.migration_journal,
                repair_context=repair_context,
                context=context,
            ),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        error_msg = f"AI analysis stage timed out after {timeout} seconds."
        logger.error(error_msg)
        context.infrastructure_error = True
        context.compilation_success = False
        context.error_category = "TIMEOUT_ERROR"
        context.failure_reason = error_msg
        context.recommended_next_action = f"The AI analysis stage timed out after {timeout} seconds. Check your Fireworks API key, network latency, or try a smaller source file."
        raise RuntimeError(error_msg)

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
    if context.compiler_errors:
        workspace = Path(context.workspace_path)
        generated_dir = workspace / "generated"
        for err in context.compiler_errors:
            err_file = err.file
            resolved_path = Path(err_file)
            if not resolved_path.is_absolute():
                resolved_path = generated_dir / err_file
            if resolved_path.exists():
                hip_source_path = str(resolved_path)
                logger.info("[PATCHING] Target file for patch selected from compiler error: %s", hip_source_path)
                break
    if hip_source_path:
        try:
            source_code = Path(hip_source_path).read_text(encoding="utf-8", errors="replace")
            if "Generated by HIPForge" in source_code:
                source_code = re.sub(
                    r"^// =+.*?// =+\s*", "", source_code, flags=re.DOTALL
                )
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
        filename = Path(hip_source_path).name
    else:
        filename = "kernel.hip"

    patch_path = patches_dir / f"patch_attempt_{attempt_num:03d}_{filename}"

    # ── Workspace path containment check (req #4) ─────────────────────────────
    # Ensure patch_path resolves inside workspace/patches/ — never modifies
    # uploaded source files or anything outside the generated workspace.
    try:
        resolved_patch = patch_path.resolve()
        resolved_patches_dir = patches_dir.resolve()
        resolved_patch.relative_to(resolved_patches_dir)  # raises ValueError if outside
    except ValueError:
        raise RuntimeError(
            f"[PATCHING] Security: patch path {patch_path} is outside workspace patches dir {patches_dir}"
        )
    # ──────────────────────────────────────────────────────────

    logger.info(
        "[PATCHING] Generating patch for attempt %d. Output: %s",
        attempt_num, patch_path,
    )

    # ── Call Patch Agent ────────────────────────────────────────────────
    analysis = context.analysis_result or {}

    # ponytail: call patch with timeout
    import asyncio
    from app.config.settings import settings
    timeout = getattr(settings, "TIMEOUT_AI_PATCHING", 60)
    try:
        patched_source = await asyncio.wait_for(
            asyncio.to_thread(
                patch,
                source_code=source_code,
                analysis=analysis,
                compiler_errors=context.compiler_errors,
                migration_journal=context.migration_journal,
                previous_patches=context.patch_history,
                context=context,
            ),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        error_msg = f"AI patching stage timed out after {timeout} seconds."
        logger.error(error_msg)
        context.infrastructure_error = True
        context.compilation_success = False
        context.error_category = "TIMEOUT_ERROR"
        context.failure_reason = error_msg
        context.recommended_next_action = f"The AI patching stage timed out after {timeout} seconds. Check your Fireworks API key, network latency, or try a smaller source file."
        raise RuntimeError(error_msg)

    # Prevent infinite loop if the patch agent doesn't modify the source code
    if patched_source.strip() == source_code.strip():
        logger.warning("[PATCHING] Patch Agent returned unchanged source code. Infinite loop prevented.")
        context.infrastructure_error = True
        context.error_category = "AI_ERROR"
        # Store lesson so future runs skip this error
        from app.redis.client import redis_client
        from app.learning.lesson_storage import store_lesson
        await store_lesson(
            redis_client,
            category="PATCH_NOOP",
            stderr=context.last_compile_stderr,
            target_architecture=getattr(context, "target_gpu_architecture", ""),
            recommended_action="The patch agent was unable to modify the source. Manual intervention required.",
            patch_attempted=True,
            patch_skipped_reason="Patch Agent returned unchanged source code (no-op)",
        )
        raise RuntimeError("Patch Agent returned unchanged source code. Infinite loop prevented.")

    # ── Safety-validate the AI patch before accepting it ─────────────────
    from app.agents.patch_agent import validate_patch
    vr = validate_patch(
        original=source_code,
        patched=patched_source,
        workspace_root=context.workspace_path,
        patch_file_path=str(patch_path),
        analysis=analysis,
        runtime_validated=(
            getattr(context, "runtime_validation_status", None) == "PASSED"
        ),
    )
    vr["target_file"] = filename
    logger.info(
        "[PATCHING] Safety validation: accepted=%s reason=%s changed_lines=%d "
        "before_hash=%.8s after_hash=%.8s",
        vr["accepted"], vr["reason"], vr["changed_lines"],
        vr["before_hash"], vr["after_hash"],
    )
    if vr["arch_warning"]:
        logger.warning("[PATCHING] ARCH WARNING: %s", vr["arch_warning"])
    # Persist validation record for the report / audit trail
    context.patch_validation = vr
    context.patch_validations = getattr(context, "patch_validations", [])
    context.patch_validations.append(vr)

    if not vr["accepted"]:
        logger.error("[PATCHING] Patch REJECTED: %s", vr["reason"])
        context.error_category = "AI_ERROR"
        context.failure_reason = f"Patch rejected by safety gate: {vr['reason']}"
        raise RuntimeError(f"[PATCHING] Patch safety gate rejected patch: {vr['reason']}")

    # ── Write patched file to workspace ─────────────────────────────────
    # Run launcher safety checks post-processing on the patched source to ensure safety guards are preserved/added
    try:
        from app.compiler.validator import harden_hip_content
        hardened_source, _ = harden_hip_content(patched_source, validation_enabled=context.runtime_validation_enabled)
        patched_source = hardened_source
    except Exception as e:
        logger.warning("[PATCHING] Failed to post-process patched source: %s", e)

    # Prepend provenance comments to the patched file
    try:
        from datetime import datetime, timezone
        provenance_comment = (
            f"// =========================================================================\n"
            f"// Generated by HIPForge (AI repaired)\n"
            f"// Source File: {filename}\n"
            f"// Target Architecture: {getattr(context, 'target_gpu_architecture', 'gfx90a')}\n"
            f"// Timestamp: {datetime.now(timezone.utc).isoformat()}\n"
            f"// Validation Status: Refer to final report for compile status\n"
            f"// =========================================================================\n\n"
        )
        if "Generated by HIPForge" in patched_source:
            # Strip previous provenance comment block to avoid duplication
            patched_source = re.sub(
                r"^// =+.*?// =+\s*", "", patched_source, flags=re.DOTALL
            )
        patched_source = provenance_comment + patched_source
    except Exception as e:
        logger.warning("[PATCHING] Failed to prepend provenance comments: %s", e)

    patch_path.write_text(patched_source, encoding="utf-8")

    logger.info("[PATCHING] Patched source written to %s", patch_path)

    # ── Compile-validate-rollback (req #5) ───────────────────────────────────
    # Run a quick compile-check on the patch before committing it.
    # If it produces more errors than before, roll back to the pre-patch source.
    try:
        from app.compiler.sca import analyze as sca_analyze
        import tempfile

        if patch_path.suffix.lower() in (".h", ".cuh", ".hpp", ".hxx"):
            logger.info("[PATCHING] Patched file is a header. Skipping compile probe.")
            probe_ok = True
            probe_errors = []
            new_error_count = 0
            prev_error_count = 0
        else:
            from app.compiler.hipcc_runner import run_hipcc
            binary_tmp = str(workspace / "generated" / f"_patch_probe_{attempt_num:03d}")
            target_arch = getattr(context, "target_gpu_architecture", "gfx90a")
            probe_result = await asyncio.to_thread(
                run_hipcc,
                str(patch_path),
                binary_tmp,
                target_arch,
                context.workspace_path,
            )
            probe_errors = probe_result.get("errors", [])
            probe_ok = probe_result.get("success", False)

            prev_error_count = len(context.compiler_errors or [])
            new_error_count = len(probe_errors)

        if probe_ok:
            logger.info("[PATCHING] Compile probe PASSED on patched source. Keeping patch.")
            # Run static validation too
            try:
                sca_result = await asyncio.to_thread(sca_analyze, str(patch_path))
                high_sev = [i for i in sca_result.get("issues", []) if i.severity == "high"]
                if high_sev:
                    logger.warning(
                        "[PATCHING] Compile probe passed but SCA found %d high-severity issue(s). Keeping patch (SCA handled in COMPILING).",
                        len(high_sev),
                    )
            except Exception as sca_exc:
                logger.debug("[PATCHING] SCA probe skipped: %s", sca_exc)
        elif new_error_count > prev_error_count:
            logger.warning(
                "[PATCHING] Compile probe FAILED with MORE errors (%d > %d). Rolling back patch.",
                new_error_count, prev_error_count,
            )
            # Restore the pre-patch source
            patch_path.write_text(source_code, encoding="utf-8")
            patched_source = source_code
            logger.info("[PATCHING] Rolled back to pre-patch source.")
        else:
            logger.info(
                "[PATCHING] Compile probe failed but error count did not increase (%d ≤ %d). Keeping patch.",
                new_error_count, prev_error_count,
            )
    except Exception as probe_exc:
        # ponytail: probe failure is non-fatal — COMPILING will be the authoritative check
        logger.warning("[PATCHING] Compile probe skipped due to exception: %s", probe_exc)
    # ──────────────────────────────────────────────────────────

    # Update file lifecycle metadata for the patched file
    try:
        import hashlib
        import os
        from app.workflow_engine.state_machine import publish_log
        for orig_rel_path, f_meta in getattr(context, "file_lifecycle", {}).items():
            if os.path.basename(f_meta["generated_path"]) == filename:
                f_meta["modified_by_ai"] = True
                f_meta["generated_hash"] = hashlib.sha256(patched_source.encode("utf-8")).hexdigest()
                break
        await publish_log(
            migration_id=context.migration_id,
            message=f"[PATCHING] Updated generated file via AI repair: {filename}",
            generated_path=str(patch_path.relative_to(workspace)).replace("\\", "/"),
            stage="PATCHING",
            status="modified",
            reason=f"attempt_{context.current_attempt + 1}"
        )
    except Exception as e:
        logger.warning("[PATCHING] Failed to update lifecycle/log for patched file: %s", e)

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

    # ── COMPILE_VALIDATED_WITH_WARNING when arch warnings remain unresolved ──
    if (
        getattr(context, "patch_validation", {}).get("arch_warning")
        and getattr(context, "runtime_validation_status", None) != "PASSED"
    ):
        context.compile_status = "COMPILE_VALIDATED_WITH_WARNING"
        logger.warning(
            "[PATCHING] compile_status set to COMPILE_VALIDATED_WITH_WARNING "
            "due to unresolved architecture-sensitive semantic warning."
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
        build_zip,
        write_history_summary,
    )
    from app.workflow_engine.state_machine import publish_event
    await publish_event(context.migration_id, "GENERATING_REPORT", "started", "Report generation started.")

    logger.info("[GENERATING_REPORT] Commencing report generation...")
    migration_id = context.migration_id

    try:
        # Publish AI repair failed if compilation failed and budget was exhausted
        if not getattr(context, "compilation_success", False):
            from app.services.report_service import get_skipped_ai_repair_reason
            skipped_reason = get_skipped_ai_repair_reason(context)
            if not skipped_reason and getattr(context, "current_attempt", 0) >= getattr(context, "retry_budget", 5):
                await publish_event(
                    context.migration_id,
                    "ANALYZING",
                    "ai_repair_failed",
                    "AI repair failed. Budget exhausted.",
                    error_category=getattr(context, "error_category", "COMPILATION_ERROR"),
                    main_error=getattr(context, "last_compile_stderr", "")
                )

        await generate_markdown_report(migration_id, context)
        await generate_json_report(migration_id, context)
        await generate_git_patch(migration_id, context)
        await build_zip(migration_id, context)
        await write_history_summary(migration_id, context)

        await publish_event(context.migration_id, "GENERATING_REPORT", "completed", "Report generated successfully.")

        from app.workflow_engine.state_machine import publish_log
        await publish_log(
            migration_id=context.migration_id,
            message="[REPORT] Migration report and export package generated successfully.",
            stage="GENERATING_REPORT",
            status="completed"
        )
        logger.info("[GENERATING_REPORT] Report generation complete.")
    except Exception as exc:
        logger.exception("[GENERATING_REPORT] Failed to generate reports: %s", exc)

    return "COMPLETED"


async def handle_completed(context: WorkflowContext) -> str:
    from app.workflow_engine.state_machine import publish_event
    await publish_event(context.migration_id, "COMPLETED", "completed", "Workflow completed successfully.")
    return None


async def handle_failed(context: WorkflowContext) -> str:
    from app.workflow_engine.state_machine import publish_event
    from app.services.report_service import write_history_summary
    await publish_event(
        context.migration_id,
        "FAILED",
        "failed",
        f"Workflow failed: {getattr(context, 'failure_reason', 'unknown error')}",
        error_category=getattr(context, "error_category", "UNKNOWN_ERROR"),
        main_error=getattr(context, "failure_reason", "")
    )
    await write_history_summary(context.migration_id, context, failed=True)
    return None
