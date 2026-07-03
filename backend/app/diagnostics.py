import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.config.settings import settings


ERROR_ENVIRONMENT = "ENVIRONMENT_ERROR"
ERROR_CONFIGURATION = "CONFIGURATION_ERROR"
ERROR_DEPENDENCY = "DEPENDENCY_ERROR"
ERROR_TOOLCHAIN = "TOOLCHAIN_ERROR"
ERROR_COMPILATION = "COMPILATION_ERROR"
ERROR_MIGRATION = "MIGRATION_ERROR"
ERROR_AI = "AI_ERROR"
ERROR_NETWORK = "NETWORK_ERROR"
ERROR_USER_CODE = "USER_CODE_ERROR"
ERROR_UNSUPPORTED = "UNSUPPORTED_FEATURE"

PASS = "pass"
FAIL = "fail"
WARN = "warn"
SKIP = "skip"

REQUIRED_WORKSPACE_DIRS = (
    "input",
    "generated",
    "patches",
    "logs",
    "artifacts",
    "reports",
    "exports",
)


@dataclass
class DiagnosticCheck:
    id: str
    name: str
    status: str
    critical: bool
    category: str
    message: str
    recommendation: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _placeholder_api_key(value: Optional[str]) -> bool:
    return not value or value.strip() in {"", "your_fireworks_api_key"}


def _timed_check(
    checks: List[DiagnosticCheck],
    check_id: str,
    name: str,
    critical: bool,
    category: str,
    fn,
) -> DiagnosticCheck:
    start = time.time()
    try:
        status, message, recommendation, details = fn()
    except Exception as exc:
        status = FAIL
        message = f"{name} check failed unexpectedly: {exc}"
        recommendation = "Review the diagnostic details and retry hipforge doctor."
        details = {"exception": str(exc)}
    check = DiagnosticCheck(
        id=check_id,
        name=name,
        status=status,
        critical=critical,
        category=category,
        message=message,
        recommendation=recommendation or "",
        details=details or {},
        duration_ms=round((time.time() - start) * 1000, 2),
    )
    checks.append(check)
    return check


def _add_check(
    checks: List[DiagnosticCheck],
    check_id: str,
    name: str,
    status: str,
    critical: bool,
    category: str,
    message: str,
    recommendation: str = "",
    details: Optional[Dict[str, Any]] = None,
) -> DiagnosticCheck:
    check = DiagnosticCheck(
        id=check_id,
        name=name,
        status=status,
        critical=critical,
        category=category,
        message=message,
        recommendation=recommendation,
        details=details or {},
        duration_ms=0.0,
    )
    checks.append(check)
    return check


def _writable_path(path: Path) -> Tuple[bool, str]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".hipforge_write_probe"
        probe.write_text("ok", encoding="utf-8")
        if probe.read_text(encoding="utf-8") != "ok":
            return False, "write probe content mismatch"
        probe.unlink(missing_ok=True)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _walk_project_entries(workspace_path: Optional[str]) -> Iterable[str]:
    if not workspace_path:
        return []

    root = Path(workspace_path)
    input_dir = root / "input"
    scan_root = input_dir if input_dir.exists() else root
    entries: List[str] = []

    if scan_root.exists():
        for path in scan_root.rglob("*"):
            if path.is_file():
                try:
                    entries.append(str(path.relative_to(scan_root)).replace("\\", "/"))
                except ValueError:
                    entries.append(path.name)

                if path.suffix.lower() == ".zip":
                    try:
                        import zipfile

                        with zipfile.ZipFile(path, "r") as archive:
                            entries.extend(archive.namelist())
                    except Exception:
                        entries.append(path.name)
    return entries


def detect_project_requirements(workspace_path: Optional[str]) -> Dict[str, bool]:
    entries = [entry.lower().replace("\\", "/") for entry in _walk_project_entries(workspace_path)]
    return {
        "uses_cmake": any(entry.endswith("cmakelists.txt") for entry in entries),
        "requires_ninja": settings.REQUIRE_NINJA or any(entry.endswith("build.ninja") for entry in entries),
    }


def _docker_client():
    try:
        import docker

        return docker.from_env(), None
    except Exception as exc:
        return None, exc


def _container_runtime(docker_info: Optional[Dict[str, Any]]) -> Tuple[Optional[str], bool]:
    runtimes = (docker_info or {}).get("Runtimes", {}) or {}
    has_runsc = "runsc" in runtimes
    if has_runsc:
        return "runsc", True
    if settings.ALLOW_RUNSC_FALLBACK:
        return None, False
    return "runsc", False


def _run_container_command(client, image: str, command: List[str], runtime: Optional[str] = None, timeout_sec: int = 20) -> Tuple[int, str]:
    container = None
    try:
        container = client.containers.run(
            image=image,
            command=command,
            runtime=runtime,
            network_mode="none",
            detach=True,
            stdout=True,
            stderr=True,
        )
        result = container.wait(timeout=timeout_sec)
        logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
        return int(result.get("StatusCode", -1)), logs
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass


def _parse_sandbox_probe(output: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def _sandbox_probe_command() -> List[str]:
    return [
        "sh",
        "-lc",
        (
            "echo HIPIFY=$(command -v hipify-clang || true); "
            "echo HIPCC=$(command -v hipcc || true); "
            "echo CMAKE=$(command -v cmake || true); "
            "echo NINJA=$(command -v ninja || true); "
            "if [ -d /usr/local/cuda ] || command -v nvcc >/dev/null 2>&1; then echo CUDA=present; else echo CUDA=; fi; "
            "echo CUDA_RUNTIME=$(find /usr/local/cuda /usr/include /opt -name cuda_runtime.h -print -quit 2>/dev/null || true); "
            "echo LIBDEVICE=$(find /usr/local/cuda /usr/lib /opt -name 'libdevice*.bc' -print -quit 2>/dev/null || true); "
            "if [ -d /opt/rocm/include ]; then echo ROCM_INCLUDE=/opt/rocm/include; "
            "elif [ -d /usr/include/hip ]; then echo ROCM_INCLUDE=/usr/include/hip; "
            "else echo ROCM_INCLUDE=; fi"
        ),
    ]


def _check_host_binary(name: str) -> Optional[str]:
    return shutil.which(name)


def _fireworks_request(url: str, api_key: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None, timeout: int = 10) -> Dict[str, Any]:
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read().decode("utf-8")
        return json.loads(data) if data else {}


def _compiler_cache_dir() -> Path:
    try:
        from app.compiler.hipcc_runner import CACHE_DIR

        return Path(CACHE_DIR)
    except Exception:
        return Path(settings.WORKSPACE_PATH) / ".cache"


def _cache_integrity(cache_dir: Path) -> Tuple[bool, str, Dict[str, Any]]:
    corrupt_files: List[str] = []
    if cache_dir.exists():
        for meta in cache_dir.glob("*.json"):
            try:
                json.loads(meta.read_text(encoding="utf-8"))
            except Exception:
                corrupt_files.append(str(meta))
    if corrupt_files:
        return False, "Compiler cache contains unreadable metadata.", {"corrupt_files": corrupt_files}
    return True, "Compiler cache is writable and metadata is readable.", {"cache_dir": str(cache_dir)}


def _status_icon(status: str) -> str:
    return {
        PASS: "OK",
        WARN: "WARN",
        FAIL: "FAIL",
        SKIP: "SKIP",
    }.get(status, status.upper())


def summarize_report(checks: List[DiagnosticCheck]) -> Dict[str, Any]:
    applicable = [check for check in checks if check.status != SKIP]
    weighted_total = sum(2 if check.critical else 1 for check in applicable) or 1
    weighted_ok = sum(
        2 if check.critical else 1
        for check in applicable
        if check.status == PASS
    )
    weighted_ok += sum(
        0.5
        for check in applicable
        if check.status == WARN and not check.critical
    )
    health_score = int(max(0, min(100, round((weighted_ok / weighted_total) * 100))))

    critical_failures = [check for check in checks if check.critical and check.status == FAIL]
    warnings = [check for check in checks if check.status == WARN]
    missing_components = [check.name for check in checks if check.status == FAIL]
    installed_components = [check.name for check in checks if check.status == PASS]
    recommended_fixes = []
    seen_fixes = set()
    for check in checks:
        if check.status in {FAIL, WARN} and check.recommendation and check.recommendation not in seen_fixes:
            recommended_fixes.append(check.recommendation)
            seen_fixes.add(check.recommendation)

    mock_mode = settings.USE_MOCK_AI or settings.USE_MOCK_COMPILER
    if critical_failures:
        readiness = "NOT_READY"
        overall_status = "unhealthy"
    elif warnings:
        readiness = "MOCK_READY" if mock_mode else "READY_WITH_WARNINGS"
        overall_status = "degraded"
    else:
        readiness = "MOCK_READY" if mock_mode else "READY"
        overall_status = "healthy"

    return {
        "overall_status": overall_status,
        "health_score": health_score,
        "readiness": readiness,
        "critical_failures": [check.to_dict() for check in critical_failures],
        "installed_components": installed_components,
        "missing_components": missing_components,
        "warnings": [check.to_dict() for check in warnings],
        "recommended_fixes": recommended_fixes,
    }


def run_preflight(
    workspace_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    require_ai: bool = True,
    run_container_checks: bool = True,
) -> Dict[str, Any]:
    checks: List[DiagnosticCheck] = []
    workspace_root = Path(workspace_path or settings.WORKSPACE_PATH)
    output_path = Path(output_dir) if output_dir else workspace_root / "exports"
    project_requirements = detect_project_requirements(workspace_path)
    compiler_is_mocked = settings.USE_MOCK_COMPILER
    ai_is_mocked = settings.USE_MOCK_AI or not require_ai
    needs_sandbox_toolchain = not compiler_is_mocked

    docker_state: Dict[str, Any] = {
        "client": None,
        "info": None,
        "image_ok": False,
        "container_ok": False,
        "runtime": None,
        "runsc_available": False,
        "sandbox_probe": {},
    }

    def docker_sdk_check():
        client, exc = _docker_client()
        if exc:
            return (
                FAIL,
                f"Docker SDK could not connect: {exc}",
                "Install Docker Desktop/Engine and ensure the Python docker package can reach it.",
                {"error": str(exc)},
            )
        docker_state["client"] = client
        return PASS, "Docker SDK client initialized.", "", {}

    _timed_check(
        checks,
        "docker_sdk",
        "Docker SDK Connectivity",
        needs_sandbox_toolchain,
        ERROR_DEPENDENCY,
        docker_sdk_check,
    )

    def docker_daemon_check():
        client = docker_state["client"]
        if client is None:
            return FAIL, "Docker daemon was not checked because SDK initialization failed.", "Start Docker and rerun hipforge doctor.", {}
        client.ping()
        docker_state["info"] = client.info()
        return PASS, "Docker daemon is running.", "", {"server_version": docker_state["info"].get("ServerVersion")}

    _timed_check(
        checks,
        "docker_daemon",
        "Docker Daemon",
        needs_sandbox_toolchain,
        ERROR_ENVIRONMENT,
        docker_daemon_check,
    )

    image_name = settings.SANDBOX_IMAGE

    def docker_image_check():
        client = docker_state["client"]
        if client is None:
            return FAIL, f"Docker image {image_name} cannot be checked without Docker.", f"Pull the sandbox image with: docker pull {image_name}", {}
        image = client.images.get(image_name)
        docker_state["image_ok"] = True
        tags = getattr(image, "tags", [])
        return PASS, f"Docker image {image_name} exists.", "", {"tags": tags}

    if docker_state["client"] is not None:
        _timed_check(
            checks,
            "docker_image",
            "Docker Image",
            needs_sandbox_toolchain,
            ERROR_DEPENDENCY,
            docker_image_check,
        )
    else:
        _add_check(
            checks,
            "docker_image",
            "Docker Image",
            FAIL if needs_sandbox_toolchain else WARN,
            needs_sandbox_toolchain,
            ERROR_DEPENDENCY,
            f"Docker image {image_name} cannot be verified because Docker is unavailable.",
            f"Start Docker and pull the sandbox image with: docker pull {image_name}",
        )

    runtime, runsc_available = _container_runtime(docker_state["info"])
    docker_state["runtime"] = runtime
    docker_state["runsc_available"] = runsc_available
    if runsc_available:
        _add_check(
            checks,
            "runsc",
            "gVisor runsc",
            PASS,
            False,
            ERROR_ENVIRONMENT,
            "gVisor runsc runtime is installed.",
            details={"fallback_allowed": settings.ALLOW_RUNSC_FALLBACK},
        )
    elif settings.ALLOW_RUNSC_FALLBACK:
        _add_check(
            checks,
            "runsc",
            "gVisor runsc",
            WARN,
            False,
            ERROR_ENVIRONMENT,
            "gVisor runsc runtime is not installed; Docker default runtime fallback is allowed.",
            "Install gVisor runsc and register it with Docker for stronger sandbox isolation.",
            {"fallback_allowed": True},
        )
    else:
        _add_check(
            checks,
            "runsc",
            "gVisor runsc",
            FAIL,
            needs_sandbox_toolchain,
            ERROR_ENVIRONMENT,
            "gVisor runsc runtime is not installed and fallback is disabled.",
            "Install gVisor runsc or set ALLOW_RUNSC_FALLBACK=true.",
            {"fallback_allowed": False},
        )

    if run_container_checks and docker_state["client"] is not None and docker_state["image_ok"]:
        def container_start_check():
            code, output = _run_container_command(
                docker_state["client"],
                image_name,
                ["sh", "-lc", "true"],
                runtime=docker_state["runtime"],
            )
            docker_state["container_ok"] = code == 0
            if code == 0:
                return PASS, "Sandbox container can start.", "", {"runtime": docker_state["runtime"] or "default"}
            return FAIL, f"Sandbox container exited with {code}.", "Verify Docker can run the ROCm sandbox image.", {"output": output}

        _timed_check(
            checks,
            "docker_container_start",
            "Docker Container Startup",
            needs_sandbox_toolchain,
            ERROR_ENVIRONMENT,
            container_start_check,
        )
    else:
        _add_check(
            checks,
            "docker_container_start",
            "Docker Container Startup",
            SKIP if compiler_is_mocked else FAIL,
            needs_sandbox_toolchain,
            ERROR_ENVIRONMENT,
            "Sandbox container startup was skipped because Docker image or daemon is unavailable.",
            "Fix Docker daemon and image availability first.",
        )

    host_hipify = _check_host_binary("hipify-clang")
    host_hipify_required = settings.REQUIRE_HOST_HIPIFY
    _add_check(
        checks,
        "host_hipify_clang",
        "Host hipify-clang",
        PASS if host_hipify else (FAIL if host_hipify_required else WARN),
        host_hipify_required,
        ERROR_TOOLCHAIN,
        f"Host hipify-clang found at {host_hipify}." if host_hipify else "Host hipify-clang is not on PATH.",
        "Install ROCm HIPIFY tools or rely on the sandboxed hipify-clang path." if not host_hipify else "",
        {"path": host_hipify, "required": host_hipify_required},
    )

    sandbox_probe: Dict[str, str] = {}
    if run_container_checks and docker_state["container_ok"]:
        def sandbox_tool_probe():
            code, output = _run_container_command(
                docker_state["client"],
                image_name,
                _sandbox_probe_command(),
                runtime=docker_state["runtime"],
            )
            sandbox_probe.update(_parse_sandbox_probe(output))
            docker_state["sandbox_probe"] = sandbox_probe
            if code != 0:
                return FAIL, "Sandbox toolchain probe failed.", "Verify the sandbox image includes ROCm and CUDA compatibility tools.", {"output": output}
            return PASS, "Sandbox toolchain probe completed.", "", sandbox_probe

        _timed_check(
            checks,
            "sandbox_probe",
            "Sandbox Toolchain Probe",
            needs_sandbox_toolchain,
            ERROR_TOOLCHAIN,
            sandbox_tool_probe,
        )
    else:
        sandbox_probe = {}

    def sandbox_value(key: str) -> str:
        return (sandbox_probe.get(key) or "").strip()

    sandbox_checks = [
        ("sandbox_hipify_clang", "Sandbox hipify-clang", "HIPIFY", ERROR_TOOLCHAIN, "Install hipify-clang inside the sandbox image."),
        ("hipcc", "HIPCC", "HIPCC", ERROR_TOOLCHAIN, "Install ROCm HIP SDK/hipcc inside the sandbox image."),
        ("cuda_toolkit", "CUDA Toolkit", "CUDA", ERROR_DEPENDENCY, "Install CUDA toolkit compatibility packages required by hipify-clang."),
        ("cuda_runtime_header", "cuda_runtime.h", "CUDA_RUNTIME", ERROR_DEPENDENCY, "Install CUDA headers so cuda_runtime.h can be found."),
        ("libdevice", "libdevice", "LIBDEVICE", ERROR_DEPENDENCY, "Install CUDA libdevice bitcode files."),
        ("required_include_dirs", "Required Include Directories", "ROCM_INCLUDE", ERROR_DEPENDENCY, "Install ROCm include directories in the sandbox image."),
    ]
    for check_id, name, key, category, recommendation in sandbox_checks:
        value = sandbox_value(key)
        if compiler_is_mocked:
            status = SKIP
            message = f"{name} check skipped because USE_MOCK_COMPILER=true."
            critical = False
        else:
            status = PASS if value else FAIL
            message = f"{name} found at {value}." if value else f"{name} was not found in the sandbox."
            critical = True
        _add_check(
            checks,
            check_id,
            name,
            status,
            critical,
            category,
            message,
            "" if status == PASS else recommendation,
            {"value": value},
        )

    cmake_path = _check_host_binary("cmake") or sandbox_value("CMAKE")
    if project_requirements["uses_cmake"]:
        _add_check(
            checks,
            "cmake",
            "CMake",
            PASS if cmake_path else FAIL,
            True,
            ERROR_TOOLCHAIN,
            f"CMake found at {cmake_path}." if cmake_path else "Project uses CMake, but cmake was not found.",
            "Install CMake or remove the CMake-based build requirement.",
            {"project_uses_cmake": True, "path": cmake_path},
        )
    else:
        _add_check(
            checks,
            "cmake",
            "CMake",
            SKIP,
            False,
            ERROR_TOOLCHAIN,
            "Project does not appear to use CMake.",
            details={"project_uses_cmake": False},
        )

    ninja_path = _check_host_binary("ninja") or sandbox_value("NINJA")
    if project_requirements["requires_ninja"]:
        _add_check(
            checks,
            "ninja",
            "Ninja",
            PASS if ninja_path else FAIL,
            True,
            ERROR_TOOLCHAIN,
            f"Ninja found at {ninja_path}." if ninja_path else "Ninja is required, but ninja was not found.",
            "Install Ninja or configure HIPForge to use a different generator.",
            {"required": True, "path": ninja_path},
        )
    else:
        _add_check(
            checks,
            "ninja",
            "Ninja",
            SKIP,
            False,
            ERROR_TOOLCHAIN,
            "Ninja is not required for this project.",
            details={"required": False},
        )

    api_key = settings.FIREWORKS_API_KEY
    api_key_missing = _placeholder_api_key(api_key)
    if ai_is_mocked:
        _add_check(
            checks,
            "fireworks_api_key",
            "Fireworks API Key",
            SKIP,
            False,
            ERROR_CONFIGURATION,
            "Fireworks API key check skipped because AI is mocked or not required.",
            details={"use_mock_ai": settings.USE_MOCK_AI, "require_ai": require_ai},
        )
        _add_check(
            checks,
            "fireworks_endpoint",
            "Fireworks Endpoint",
            SKIP,
            False,
            ERROR_NETWORK,
            "Fireworks endpoint check skipped because AI is mocked or not required.",
        )
        _add_check(
            checks,
            "fireworks_model",
            "Fireworks Model",
            SKIP,
            False,
            ERROR_AI,
            "Fireworks model check skipped because AI is mocked or not required.",
            details={"model": settings.FIREWORKS_MODEL},
        )
    else:
        _add_check(
            checks,
            "fireworks_api_key",
            "Fireworks API Key",
            PASS if not api_key_missing else FAIL,
            True,
            ERROR_CONFIGURATION,
            "Fireworks API key is configured." if not api_key_missing else "FIREWORKS_API_KEY is missing or still set to the placeholder.",
            "Set FIREWORKS_API_KEY in .env or set USE_MOCK_AI=true for offline development.",
        )

        if not api_key_missing:
            def fireworks_endpoint_check():
                data = _fireworks_request(f"{settings.FIREWORKS_API_BASE}/models", api_key, timeout=10)
                model_count = len(data.get("data", [])) if isinstance(data, dict) else 0
                return PASS, "Fireworks endpoint is reachable.", "", {"model_count": model_count}

            _timed_check(
                checks,
                "fireworks_endpoint",
                "Fireworks Endpoint",
                True,
                ERROR_NETWORK,
                fireworks_endpoint_check,
            )

            def fireworks_model_check():
                payload = {
                    "model": settings.FIREWORKS_MODEL,
                    "messages": [{"role": "user", "content": "Return OK."}],
                    "max_tokens": 4,
                }
                data = _fireworks_request(
                    f"{settings.FIREWORKS_API_BASE}/chat/completions",
                    api_key,
                    method="POST",
                    payload=payload,
                    timeout=20,
                )
                if data.get("choices"):
                    return PASS, "Selected Fireworks model returned successfully.", "", {"model": settings.FIREWORKS_MODEL}
                return FAIL, "Selected Fireworks model did not return a completion.", "Verify FIREWORKS_MODEL and account access.", {"response": data}

            _timed_check(
                checks,
                "fireworks_model",
                "Fireworks Model",
                True,
                ERROR_AI,
                fireworks_model_check,
            )
        else:
            _add_check(
                checks,
                "fireworks_endpoint",
                "Fireworks Endpoint",
                SKIP,
                False,
                ERROR_NETWORK,
                "Fireworks endpoint check skipped because API key is missing.",
            )
            _add_check(
                checks,
                "fireworks_model",
                "Fireworks Model",
                SKIP,
                False,
                ERROR_AI,
                "Fireworks model check skipped because API key is missing.",
                details={"model": settings.FIREWORKS_MODEL},
            )

    def workspace_dirs_check():
        missing_or_unwritable: List[str] = []
        for subdir in REQUIRED_WORKSPACE_DIRS:
            ok, reason = _writable_path(workspace_root / subdir)
            if not ok:
                missing_or_unwritable.append(f"{subdir}: {reason}")
        if missing_or_unwritable:
            return FAIL, "One or more required workspace directories are not writable.", "Fix permissions on WORKSPACE_PATH.", {"problems": missing_or_unwritable}
        return PASS, "Required workspace directories are writable.", "", {"workspace": str(workspace_root)}

    _timed_check(
        checks,
        "workspace_directories",
        "Workspace Directories",
        True,
        ERROR_ENVIRONMENT,
        workspace_dirs_check,
    )

    def output_dir_check():
        ok, reason = _writable_path(output_path)
        if ok:
            return PASS, "Output directory is writable.", "", {"output_dir": str(output_path)}
        return FAIL, "Output directory is not writable.", "Fix output directory permissions.", {"output_dir": str(output_path), "reason": reason}

    _timed_check(
        checks,
        "output_permissions",
        "Output Directory Permissions",
        True,
        ERROR_ENVIRONMENT,
        output_dir_check,
    )

    def temp_workspace_check():
        workspace_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="hipforge_preflight_", dir=str(workspace_root)) as temp_dir:
            probe = Path(temp_dir) / "probe.txt"
            probe.write_text("ok", encoding="utf-8")
        return PASS, "Temporary workspace can be created and removed.", "", {"workspace": str(workspace_root)}

    _timed_check(
        checks,
        "temporary_workspace",
        "Temporary Workspace Creation",
        True,
        ERROR_ENVIRONMENT,
        temp_workspace_check,
    )

    def compiler_cache_check():
        cache_dir = _compiler_cache_dir()
        ok, reason = _writable_path(cache_dir)
        if not ok:
            return FAIL, "Compiler cache directory is not writable.", "Fix permissions or set DISABLE_COMPILER_CACHE=true.", {"cache_dir": str(cache_dir), "reason": reason}
        cache_ok, message, details = _cache_integrity(cache_dir)
        if not cache_ok:
            return FAIL, message, "Delete corrupted files in the compiler cache or set DISABLE_COMPILER_CACHE=true.", details
        return PASS, message, "", details

    _timed_check(
        checks,
        "compiler_cache",
        "Compiler Cache Directory",
        True,
        ERROR_ENVIRONMENT,
        compiler_cache_check,
    )

    def disk_space_check():
        workspace_root.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(str(workspace_root))
        if usage.free < settings.MIN_FREE_DISK_BYTES:
            return (
                FAIL,
                "Available disk space is below the HIPForge sanity threshold.",
                "Free disk space or lower HIPFORGE_MIN_FREE_DISK_BYTES for constrained test environments.",
                {"free_bytes": usage.free, "required_bytes": settings.MIN_FREE_DISK_BYTES},
            )
        return PASS, "Disk space sanity check passed.", "", {"free_bytes": usage.free, "required_bytes": settings.MIN_FREE_DISK_BYTES}

    _timed_check(
        checks,
        "disk_space",
        "Disk Space",
        True,
        ERROR_ENVIRONMENT,
        disk_space_check,
    )

    summary = summarize_report(checks)
    report = {
        "generated_at": _utc_now(),
        "mode": {
            "use_mock_ai": settings.USE_MOCK_AI,
            "use_mock_compiler": settings.USE_MOCK_COMPILER,
            "require_ai": require_ai,
            "sandbox_image": settings.SANDBOX_IMAGE,
            "allow_runsc_fallback": settings.ALLOW_RUNSC_FALLBACK,
        },
        "workspace_path": str(workspace_root),
        "output_dir": str(output_path),
        "project_requirements": project_requirements,
        "checks": [check.to_dict() for check in checks],
        **summary,
    }
    report["healthy"] = not report["critical_failures"]
    report["summary_table"] = [
        f"{_status_icon(check.status)} {check.name}: {check.message}"
        for check in checks
    ]
    return report


def preflight_failure_message(report: Dict[str, Any]) -> str:
    failures = report.get("critical_failures") or []
    if not failures:
        return "Pre-flight validation passed."
    lines = ["Pre-flight validation failed. HIPForge will not start migration tools."]
    for failure in failures:
        lines.append(f"- {failure.get('name')}: {failure.get('message')}")
        recommendation = failure.get("recommendation")
        if recommendation:
            lines.append(f"  Fix: {recommendation}")
    return "\n".join(lines)


def recommended_next_action(category: str, report: Optional[Dict[str, Any]] = None) -> str:
    if report and report.get("critical_failures"):
        first = report["critical_failures"][0]
        if first.get("recommendation"):
            return first["recommendation"]

    actions = {
        ERROR_ENVIRONMENT: "Fix local permissions, Docker, disk space, or sandbox runtime availability, then rerun hipforge doctor.",
        ERROR_CONFIGURATION: "Update .env configuration and rerun hipforge doctor.",
        ERROR_DEPENDENCY: "Install the missing runtime dependency and rerun hipforge doctor.",
        ERROR_TOOLCHAIN: "Install or repair the ROCm/CUDA toolchain components and rerun hipforge self-test.",
        ERROR_COMPILATION: "Review compiler logs and rerun with a smaller reproducer.",
        ERROR_MIGRATION: "Review the migration report and retry after the reported pipeline issue is fixed.",
        ERROR_AI: "Verify Fireworks model access or set USE_MOCK_AI=true for offline testing.",
        ERROR_NETWORK: "Verify network connectivity to external APIs and retry.",
        ERROR_USER_CODE: "Review the reported compiler diagnostics or allow another repair iteration.",
        ERROR_UNSUPPORTED: "Rewrite or isolate unsupported CUDA features before retrying.",
    }
    return actions.get(category, "Run hipforge doctor and inspect the generated diagnostics.")


def _minimal_cuda_source() -> str:
    return """#include <cuda_runtime.h>
#include <stdio.h>

__global__ void add_one(int *data) {
    int i = threadIdx.x;
    data[i] += 1;
}

int main() {
    int *data = nullptr;
    cudaMalloc(&data, sizeof(int) * 4);
    add_one<<<1, 4>>>(data);
    cudaDeviceSynchronize();
    cudaFree(data);
    return 0;
}
"""


def run_self_test(target_arch: Optional[str] = None, cleanup: bool = True) -> Dict[str, Any]:
    workspace_root = Path(settings.WORKSPACE_PATH)
    workspace_root.mkdir(parents=True, exist_ok=True)
    temp_dir = tempfile.mkdtemp(prefix="hipforge_self_test_", dir=str(workspace_root))
    workspace = Path(temp_dir)
    for subdir in REQUIRED_WORKSPACE_DIRS:
        (workspace / subdir).mkdir(parents=True, exist_ok=True)

    report: Dict[str, Any] = {
        "generated_at": _utc_now(),
        "workspace_path": str(workspace),
        "target_arch": target_arch or "default",
        "success": False,
        "steps": [],
    }

    try:
        preflight = run_preflight(
            workspace_path=str(workspace),
            require_ai=False,
            run_container_checks=not settings.USE_MOCK_COMPILER,
        )
        report["preflight"] = preflight
        if preflight.get("critical_failures"):
            report["steps"].append({"name": "preflight", "success": False, "message": preflight_failure_message(preflight)})
            report["failure_category"] = preflight["critical_failures"][0]["category"]
            return report

        source = workspace / "input" / "self_test.cu"
        source.write_text(_minimal_cuda_source(), encoding="utf-8")
        report["steps"].append({"name": "generate_project", "success": True, "message": str(source)})

        from app.compiler.hipify_runner import run_hipify

        hip_output = workspace / "generated" / "self_test.hip"
        hipify_result = run_hipify(str(source), str(hip_output))
        report["steps"].append({"name": "hipify", "success": bool(hipify_result.get("success")), "message": hipify_result.get("stderr") or hipify_result.get("stdout", "")})
        if not hipify_result.get("success"):
            report["failure_category"] = ERROR_TOOLCHAIN
            return report

        from app.compiler.hipcc_runner import run_hipcc

        binary = workspace / "generated" / "self_test"
        compile_result = run_hipcc(str(hip_output), str(binary), target_arch=target_arch, workspace_path=str(workspace))
        report["steps"].append({"name": "compile", "success": bool(compile_result.get("success")), "message": compile_result.get("stderr") or compile_result.get("stdout", "")})
        if not compile_result.get("success"):
            report["failure_category"] = ERROR_COMPILATION
            return report

        output_exists = Path(compile_result.get("binary_path") or binary).exists()
        report["steps"].append({"name": "verify_output", "success": output_exists, "message": "Output binary exists." if output_exists else "Output binary was not produced."})
        report["success"] = output_exists
        report["failure_category"] = "NONE" if output_exists else ERROR_COMPILATION
        return report
    finally:
        if cleanup:
            shutil.rmtree(workspace, ignore_errors=True)
