import os
import subprocess
import logging
import hashlib
import json
import shutil
import re
from pathlib import Path
from typing import Dict, Any, List
from app.models.compiler_error import CompilerError
from app.compiler.error_parser import parse_compiler_errors

logger = logging.getLogger("hipcc_runner")

CACHE_DIR = Path("workspace/.cache")

def detect_compiled_architecture(binary_path: str) -> str | None:
    """Scan the binary bytes for gfx architectures (e.g. gfx906, gfx942)."""
    if not binary_path or not os.path.exists(binary_path):
        return None
    try:
        with open(binary_path, "rb") as f:
            content = f.read(10 * 1024 * 1024) # Read up to 10MB
        matches = re.findall(rb"gfx[0-9]+[a-zA-Z]?", content)
        if matches:
            arches = sorted(set(m.decode("ascii", errors="ignore") for m in matches))
            valid_arches = [a for a in arches if re.match(r"^gfx\d{2,4}[a-z]?$", a)]
            if valid_arches:
                logger.info(f"[Arch Detection] Detected gfx architectures in binary: {valid_arches}")
                return valid_arches[0]
    except Exception as e:
        logger.warning(f"Failed to detect compiled architecture from binary: {e}")
    return None

_ROCM_VERSION_CACHE = None

def get_rocm_compiler_version() -> str:
    global _ROCM_VERSION_CACHE
    if _ROCM_VERSION_CACHE is not None:
        return _ROCM_VERSION_CACHE
    hipcc_path = shutil.which("hipcc")
    if hipcc_path:
        try:
            res = subprocess.run([hipcc_path, "--version"], capture_output=True, text=True, timeout=3)
            if res.returncode == 0:
                _ROCM_VERSION_CACHE = res.stdout.strip()
                return _ROCM_VERSION_CACHE
        except Exception:
            pass
    _ROCM_VERSION_CACHE = os.getenv("ROCM_VERSION_DEFAULT", "ROCm 6.0.0 (mock/fallback)")
    return _ROCM_VERSION_CACHE

def compute_compilation_cache_key(
    source_path: str,
    target_arch: str,
    workspace_path: str = None,
    cmd_str: str = None,
    evidence: dict = None,
) -> str:
    """
    Computes a cache key that includes:
    - hashes of all compiled source files
    - build-file hashes
    - exact compiler command
    - target architecture
    - compiler/ROCm version
    - relevant compiler flags
    """
    components = []
    components.append(f"arch:{target_arch or 'default'}")
    if cmd_str:
        components.append(f"cmd:{cmd_str}")
    components.append(f"rocm_version:{get_rocm_compiler_version()}")

    if not workspace_path and source_path:
        source_abs = os.path.abspath(source_path).replace("\\", "/")
        if "/migration_" in source_abs:
            parts = source_abs.split("/migration_")
            subparts = parts[1].split("/")
            workspace_path = parts[0] + "/migration_" + subparts[0]
        else:
            workspace_path = str(Path(source_path).parent.parent)

    files_to_hash = []
    if workspace_path:
        generated_dir = Path(workspace_path) / "generated"
        if generated_dir.exists():
            for p in generated_dir.rglob("*"):
                if p.is_file():
                    name_lower = p.name.lower()
                    suffix_lower = p.suffix.lower()
                    if suffix_lower in (".hip", ".cpp", ".cc", ".cxx", ".cu", ".h", ".hpp", ".cuh"):
                        files_to_hash.append(p)
                    elif name_lower in ("makefile", "makefile.hipforge", "makefile.txt", "makefile.hip", "cmakelists.txt") or suffix_lower in (".mk", ".cmake"):
                        files_to_hash.append(p)

    if source_path:
        source_p = Path(source_path)
        if source_p.exists() and source_p not in files_to_hash:
            files_to_hash.append(source_p)

    for p in sorted(set(files_to_hash)):
        try:
            rel = str(p.relative_to(Path(workspace_path))) if workspace_path else p.name
            content = p.read_bytes()
            h = hashlib.sha256(content).hexdigest()
            components.append(f"file:{rel}:{h}")
            if evidence is not None:
                evidence.setdefault("input_hashes", {})[rel] = h
        except Exception:
            pass

    full_key = "\n".join(components)
    return hashlib.sha256(full_key.encode("utf-8")).hexdigest()

def get_compilation_cache(source_path: str, target_arch: str, workspace_path: str = None, cmd_str: str = None) -> dict | None:
    """Loads a cached compile result if available."""
    if os.getenv("DISABLE_COMPILER_CACHE", "false").lower() == "true":
        return None
    try:
        h = compute_compilation_cache_key(source_path, target_arch, workspace_path, cmd_str)
        meta_file = CACHE_DIR / f"{h}.json"
        bin_file = CACHE_DIR / f"{h}.bin"
        
        if meta_file.exists():
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("success") and not bin_file.exists():
                return None
            return {
                "hash": h,
                "meta": meta,
                "bin_file": str(bin_file) if bin_file.exists() else None
            }
    except Exception as e:
        logger.warning(f"Error reading compilation cache: {e}")
    return None

def write_compilation_cache(source_path: str, target_arch: str, result: dict, binary_path: str = None, workspace_path: str = None, cmd_str: str = None):
    """Writes a compile result to cache."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        h = compute_compilation_cache_key(source_path, target_arch, workspace_path, cmd_str)
        meta_file = CACHE_DIR / f"{h}.json"
        bin_file = CACHE_DIR / f"{h}.bin"
        
        serializable_errors = []
        for err in result.get("errors", []):
            if hasattr(err, "model_dump"):
                serializable_errors.append(err.model_dump())
            elif isinstance(err, dict):
                serializable_errors.append(err)
            else:
                serializable_errors.append(str(err))
                
        meta = {
            "success": result["success"],
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "errors": serializable_errors,
            "command": result.get("command", ""),
            "actual_arch": result.get("actual_arch", "")
        }
        
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
            
        if result["success"] and binary_path and Path(binary_path).exists():
            shutil.copy2(binary_path, bin_file)
            
        logger.info(f"[Cache] Successfully cached compilation result under key: {h}")
    except Exception as e:
        logger.warning(f"Failed to write to compilation cache: {e}")


def check_makefile_filenames_differ(makefile_path: Path, generated_dir: Path) -> bool:
    """
    Checks if the Makefile references source files (like .cu or .hip)
    that do not exist in the generated directory.
    """
    try:
        if not makefile_path.exists():
            return True
        content = makefile_path.read_text(encoding="utf-8", errors="replace")
        import re
        # Find all words ending with .cu, .hip, .cpp, .cc, .cuh, .h, .hpp
        referenced_files = re.findall(r"\b([\w\-_./]+)\.(cu|hip|cpp|cc|cuh|h|hpp)\b", content)
        makefile_dir = makefile_path.parent
        for name, ext in referenced_files:
            filename = f"{name}.{ext}"
            
            # Skip compiler names or phony/make targets
            if filename.lower() in ("makefile", "clean", "all", "cuda", "hip", "nvcc", "hipcc", "clang", "gcc", "g++"):
                continue
                
            # Check relative to Makefile directory
            file_path = makefile_dir / filename
            if not file_path.exists():
                # Check recursively in generated_dir
                base = os.path.basename(filename)
                matches = list(generated_dir.rglob(base))
                if not matches:
                    logger.info("[COMPILING] Makefile references non-existent file: %s (base: %s)", filename, base)
                    return True
    except Exception as e:
        logger.warning("Error checking Makefile filenames: %s", e)
    return False


def find_and_copy_cmake_binary(working_dir: str, output_path: str):
    """Search working_dir/build recursively for the compiled binary and copy it to output_path."""
    build_dir = Path(working_dir) / "build"
    if not build_dir.exists():
        return
    candidates = []
    for p in build_dir.rglob("*"):
        if p.is_file():
            name_lower = p.name.lower()
            if name_lower.endswith((".o", ".a", ".so", ".txt", ".cmake", ".make", ".ninja", ".json", ".ninja_deps", ".ninja_log")):
                continue
            if name_lower in ("makefile", "cmakecache.txt"):
                continue
            if os.name != 'nt':
                try:
                    if os.access(p, os.X_OK):
                        candidates.append(p)
                except Exception:
                    pass
            else:
                if name_lower.endswith(".exe") or "." not in p.name:
                    candidates.append(p)
    if candidates:
        candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        try:
            shutil.copy2(candidates[0], output_path)
            logger.info("[CMake] Copied built binary %s to %s", candidates[0], output_path)
        except Exception as e:
            logger.warning("[CMake] Failed to copy built binary %s to %s: %s", candidates[0], output_path, e)


class HipccRunner:
    """Real runner that executes the actual hipcc compiler tool."""
    
    def _get_compilation_command(self, source_path: str, output_path: str, target_arch: str = None, workspace_path: str = None) -> tuple[list[str], bool, bool]:
        name_lower = os.path.basename(source_path).lower()
        is_makefile = name_lower in ("makefile", "makefile.txt", "makefile.hip")
        is_cmake = name_lower == "cmakelists.txt"
        
        filenames_differ = False
        if is_makefile and workspace_path:
            generated_dir = Path(workspace_path) / "generated"
            filenames_differ = check_makefile_filenames_differ(Path(source_path), generated_dir)
            
        if is_makefile and not filenames_differ:
            cmd = ["make"]
            if target_arch:
                cmd.extend([
                    f"ARCH={target_arch}",
                    f"AMDGPU_TARGETS={target_arch}",
                    f"GPU_TARGETS={target_arch}",
                    f"HIP_ARCH={target_arch}"
                ])
        elif is_cmake:
            arch_flag = target_arch or "gfx90a"
            cmd = ["cmake", "-B", "build", "-S", ".", f"-DCMAKE_HIP_ARCHITECTURES={arch_flag}", f"-DCMAKE_CUDA_ARCHITECTURES={arch_flag}"]
        else:
            compile_sources = []
            include_dirs = []
            if workspace_path:
                generated_dir = Path(workspace_path) / "generated"
                generated_include = generated_dir / "include"
                if generated_dir.exists():
                    project_sources = []
                    for suffix in ("*.hip", "*.cpp", "*.cc", "*.cxx"):
                        project_sources.extend(str(p) for p in generated_dir.rglob(suffix))
                    
                    project_sources = sorted(set(project_sources))
                    if project_sources:
                        source_basename = os.path.basename(source_path)
                        for p in project_sources:
                            if source_basename.endswith(os.path.basename(p)):
                                compile_sources.append(source_path)
                            else:
                                compile_sources.append(p)
                    else:
                        compile_sources = [source_path]
                    
                    include_dirs.append(str(generated_dir))
                    if generated_include.exists():
                        include_dirs.append(str(generated_include))
            else:
                compile_sources = [source_path]

            # ponytail: added -Werror to trigger self-healing on warnings to ensure code cleanliness
            cmd = ["hipcc", "-Werror", *compile_sources]
            for include_dir in include_dirs:
                cmd.extend(["-I", include_dir])
            cmd.extend(["-o", output_path])
            if target_arch:
                cmd.append(f"--offload-arch={target_arch}")
            working_dir = None
            
        return cmd, is_makefile, is_cmake

    def run_hipcc(self, source_path: str, output_path: str, target_arch: str = None, workspace_path: str = None) -> Dict[str, Any]:
        """
        Wrapper that checks the compilation cache before executing compilation.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        cmd, is_makefile, is_cmake = self._get_compilation_command(source_path, output_path, target_arch, workspace_path)
        cmd_str = " ".join(cmd)
        if is_cmake:
            cmd_str = "cmake -B build ... && cmake --build build"

        cache_evidence = {}
        cache_key = compute_compilation_cache_key(
            source_path, target_arch, workspace_path, cmd_str, cache_evidence
        )

        # Check cache
        cached = get_compilation_cache(source_path, target_arch, workspace_path, cmd_str)
        if cached:
            meta = cached["meta"]
            logger.info(f"[Cache Hit] Using cached compilation result (hash: {cached['hash']}, success: {meta['success']})")
            if meta["success"] and cached["bin_file"]:
                try:
                    shutil.copy2(cached["bin_file"], output_path)
                except Exception as cp_err:
                    logger.warning(f"[Cache Hit] Failed to copy cached binary: {cp_err}")
            
            # Map cached errors back to CompilerError models
            from app.models.compiler_error import CompilerError
            errors = []
            for e in meta.get("errors", []):
                if isinstance(e, dict):
                    errors.append(CompilerError(**e))
                else:
                    errors.append(e)
            
            return {
                "success": meta["success"],
                "binary_path": output_path if meta["success"] else "",
                "errors": errors,
                "stdout": meta.get("stdout", "") + "\n[Cache Hit] Output loaded from compilation cache.",
                "stderr": meta.get("stderr", ""),
                "command": meta.get("command", ""),
                "actual_arch": meta.get("actual_arch", ""),
                "cache_key": cache_key,
                "cache_hit": True,
                "input_hashes": cache_evidence.get("input_hashes", {}),
            }

        # Cache miss: compile
        result = self._run_hipcc_uncached(source_path, output_path, target_arch, workspace_path)
        result["cache_key"] = cache_key
        result["cache_hit"] = False
        result["input_hashes"] = cache_evidence.get("input_hashes", {})
        
        # Write to cache
        write_compilation_cache(source_path, target_arch, result, output_path, workspace_path, cmd_str)
        
        return result

    def _run_hipcc_uncached(self, source_path: str, output_path: str, target_arch: str = None, workspace_path: str = None) -> Dict[str, Any]:
        """
        Runs the real hipcc compiler as a subprocess (or mock compiler if USE_MOCK_COMPILER=true).
        Parses output errors if compiling fails.
        """
        logger.info(f"Running hipcc compiler (uncached) on {source_path} -> {output_path} target_arch={target_arch}")
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        if os.getenv("USE_MOCK_COMPILER", "false").lower() == "true":
            logger.info("USE_MOCK_COMPILER=true. Running mock hipcc logic.")
            try:
                with open(source_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if "HIPFORGE_MOCK_COMPILE_ERROR" in content:
                    stderr = (
                        f"{os.path.basename(source_path)}:42:8: error: no matching function for call to 'hipMemcpyAsync' [E0308]\n"
                        f"{os.path.basename(source_path)}:67:12: error: use of undeclared identifier 'hipStreamNonBlocking' [E0020]\n"
                    )
                    return {
                        "success": False,
                        "returncode": 1,
                        "binary_path": "",
                        "errors": parse_compiler_errors(stderr),
                        "stdout": "",
                        "stderr": stderr,
                        "command": f"hipcc {source_path} -o {output_path} --offload-arch={target_arch or 'gfx90a'}",
                        "actual_arch": ""
                    }
                # Successful mock compile
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(f"/* HIPForge compiled mock binary: {target_arch or 'gfx90a'} */\n")
                return {
                    "success": True,
                    "returncode": 0,
                    "binary_path": output_path,
                    "errors": [],
                    "stdout": "Compiled successfully (mock)",
                    "stderr": "",
                    "command": f"hipcc {source_path} -o {output_path} --offload-arch={target_arch or 'gfx90a'}",
                    "actual_arch": target_arch or "gfx90a"
                }
            except Exception as e:
                err_msg = f"Mock compiler error: {str(e)}"
                fallback_err = CompilerError(
                    file=source_path,
                    line=1,
                    column=1,
                    message=err_msg,
                    code="E999"
                )
                return {
                    "success": False,
                    "returncode": -1,
                    "binary_path": "",
                    "errors": [fallback_err],
                    "stdout": "",
                    "stderr": err_msg,
                    "command": f"hipcc {source_path} -o {output_path} --offload-arch={target_arch or 'gfx90a'}",
                    "actual_arch": ""
                }

        # ── Real sandboxed compilation mode ────────────────────────────────
        from app.compiler.sandbox import run_sandboxed_compiler

        if not workspace_path:
            source_abs = os.path.abspath(source_path).replace("\\", "/")
            if "/migration_" in source_abs:
                parts = source_abs.split("/migration_")
                subparts = parts[1].split("/")
                workspace_path = parts[0] + "/migration_" + subparts[0]
            else:
                workspace_path = str(Path(source_path).parent.parent)

        cmd, is_makefile, is_cmake = self._get_compilation_command(source_path, output_path, target_arch, workspace_path)
        working_dir = os.path.dirname(os.path.abspath(source_path))

        from app.config.settings import settings
        timeout_sec = getattr(settings, "TIMEOUT_COMPILE", 60)
        
        # 1. Native compile path
        if shutil.which("hipcc") and (not is_makefile or shutil.which("make")) and (not is_cmake or shutil.which("cmake")):
            try:
                if is_cmake:
                    res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout_sec, cwd=working_dir)
                    if res.returncode == 0:
                        res_build = subprocess.run(["cmake", "--build", "build"], capture_output=True, text=True, check=False, timeout=timeout_sec, cwd=working_dir)
                        success = res_build.returncode == 0
                        stdout_text = res.stdout + "\n" + res_build.stdout
                        stderr_text = res.stderr + "\n" + res_build.stderr
                        returncode = res_build.returncode
                        if success:
                            find_and_copy_cmake_binary(working_dir, output_path)
                    else:
                        success = False
                        stdout_text = res.stdout
                        stderr_text = res.stderr
                        returncode = res.returncode
                else:
                    result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout_sec, cwd=working_dir)
                    success = result.returncode == 0
                    stdout_text = result.stdout
                    stderr_text = result.stderr
                    returncode = result.returncode

                errors = [] if success else parse_compiler_errors(stderr_text)
                if not success and not errors:
                    errors = [CompilerError(file=source_path, line=1, column=1, message=stderr_text or stdout_text or "Compilation failed with unknown error.", code="E999")]
                
                # Extract exact compile command
                actual_cmd_str = " ".join(cmd)
                if is_makefile or is_cmake:
                    for line in stdout_text.splitlines():
                        if "hipcc " in line or line.strip().startswith("hipcc"):
                            actual_cmd_str = line.strip()
                            break

                actual_arch = detect_compiled_architecture(output_path) if success else ""
                
                return {
                    "success": success,
                    "returncode": returncode,
                    "binary_path": output_path if success else "",
                    "errors": errors,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "command": actual_cmd_str,
                    "actual_arch": actual_arch
                }
            except subprocess.TimeoutExpired as exc:
                return {
                    "success": False,
                    "returncode": -1,
                    "binary_path": "",
                    "errors": [CompilerError(file=source_path, line=1, column=1, message=f"Compilation timed out after {timeout_sec} seconds.", code="TIMEOUT")],
                    "stdout": exc.stdout or "",
                    "stderr": f"Compilation timed out after {timeout_sec} seconds.",
                    "command": " ".join(cmd),
                    "actual_arch": ""
                }

        # 2. Sandboxed compile path
        try:
            if is_cmake:
                arch_flag = target_arch or "gfx90a"
                sandbox_cmd = ["sh", "-c", f"cmake -B build -S /workspace/generated -DCMAKE_HIP_ARCHITECTURES={arch_flag} -DCMAKE_CUDA_ARCHITECTURES={arch_flag} && cmake --build build"]
            else:
                sandbox_cmd = cmd

            sandbox_res = run_sandboxed_compiler(workspace_path, sandbox_cmd, timeout_sec=timeout_sec, working_dir=working_dir)
            timed_out = sandbox_res.get("timeout", False)
            success = (sandbox_res["returncode"] == 0) and not timed_out
            errors = []
            if timed_out:
                msg = f"Compilation timed out after {timeout_sec} seconds."
                errors.append(CompilerError(
                    file=source_path,
                    line=1,
                    column=1,
                    message=msg,
                    code="TIMEOUT"
                ))
                sandbox_res["stderr"] = msg
            elif not success:
                errors = parse_compiler_errors(sandbox_res["stderr"])
                if not errors:
                    errors.append(CompilerError(
                        file=source_path,
                        line=1,
                        column=1,
                        message=sandbox_res["stderr"] or sandbox_res["stdout"] or "Compilation failed with unknown error.",
                        code="E999"
                    ))
            
            if success and is_cmake:
                find_and_copy_cmake_binary(working_dir, output_path)

            actual_cmd_str = " ".join(cmd)
            if is_makefile or is_cmake:
                for line in sandbox_res.get("stdout", "").splitlines():
                    if "hipcc " in line or line.strip().startswith("hipcc"):
                        actual_cmd_str = line.strip()
                        break

            actual_arch = detect_compiled_architecture(output_path) if success else ""

            return {
                "success": success,
                "returncode": sandbox_res["returncode"],
                "binary_path": output_path if success else "",
                "errors": errors,
                "stdout": sandbox_res["stdout"],
                "stderr": sandbox_res["stderr"],
                "command": actual_cmd_str,
                "actual_arch": actual_arch
            }
        except Exception as e:
            err_msg = f"Sandboxed compiler launch failed: {str(e)}"
            logger.exception(err_msg)
            fallback_err = CompilerError(
                file=source_path,
                line=1,
                column=1,
                message=err_msg,
                code="E999"
            )
            return {
                "success": False,
                "returncode": -1,
                "binary_path": "",
                "errors": [fallback_err],
                "stdout": "",
                "stderr": err_msg,
                "command": " ".join(cmd) if 'cmd' in locals() else "",
                "actual_arch": ""
            }


def run_hipcc(source_path: str, output_path: str, target_arch: str = None, workspace_path: str = None) -> Dict[str, Any]:
    """
    Top-level helper function to run hipcc.
    Instantiates and executes the real HipccRunner tool.
    """
    return HipccRunner().run_hipcc(source_path, output_path, target_arch, workspace_path)
