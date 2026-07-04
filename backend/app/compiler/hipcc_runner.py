import os
import subprocess
import logging
import hashlib
import json
import shutil
from pathlib import Path
from typing import Dict, Any, List
from app.models.compiler_error import CompilerError
from app.compiler.error_parser import parse_compiler_errors

logger = logging.getLogger("hipcc_runner")

CACHE_DIR = Path("workspace/.cache")

def get_compilation_cache(source_path: str, target_arch: str) -> dict | None:
    """Loads a cached compile result if available."""
    if os.getenv("DISABLE_COMPILER_CACHE", "false").lower() == "true":
        return None
    try:
        if not Path(source_path).exists():
            return None
        with open(source_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        
        # Unique hash based on content and target architecture
        key = f"{content}\n{target_arch or 'default'}"
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
        
        meta_file = CACHE_DIR / f"{h}.json"
        bin_file = CACHE_DIR / f"{h}.bin"
        
        if meta_file.exists():
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            
            # If it was successful, ensure binary file also exists
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

def write_compilation_cache(source_path: str, target_arch: str, result: dict, binary_path: str = None):
    """Writes a compile result to cache."""
    try:
        if not Path(source_path).exists():
            return
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(source_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
            
        key = f"{content}\n{target_arch or 'default'}"
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
        
        meta_file = CACHE_DIR / f"{h}.json"
        bin_file = CACHE_DIR / f"{h}.bin"
        
        # Serialize errors if they are Pydantic objects
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
            "errors": serializable_errors
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


class HipccRunner:
    """Real runner that executes the actual hipcc compiler tool."""
    
    def run_hipcc(self, source_path: str, output_path: str, target_arch: str = None, workspace_path: str = None) -> Dict[str, Any]:
        """
        Wrapper that checks the compilation cache before executing compilation.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # Check cache
        cached = get_compilation_cache(source_path, target_arch)
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
                "stderr": meta.get("stderr", "")
            }

        # Cache miss: compile
        result = self._run_hipcc_uncached(source_path, output_path, target_arch, workspace_path)
        
        # Write to cache
        write_compilation_cache(source_path, target_arch, result, output_path)
        
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
                        "binary_path": "",
                        "errors": parse_compiler_errors(stderr),
                        "stdout": "",
                        "stderr": stderr
                    }
                # Successful mock compile
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("/* HIPForge compiled mock binary */\n")
                return {
                    "success": True,
                    "binary_path": output_path,
                    "errors": [],
                    "stdout": "Compiled successfully (mock)",
                    "stderr": ""
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
                    "binary_path": "",
                    "errors": [fallback_err],
                    "stdout": "",
                    "stderr": err_msg
                }

        # ── Real sandboxed compilation mode ────────────────────────────────
        from pathlib import Path
        from app.compiler.sandbox import run_sandboxed_compiler

        if not workspace_path:
            source_abs = os.path.abspath(source_path).replace("\\", "/")
            if "/migration_" in source_abs:
                parts = source_abs.split("/migration_")
                subparts = parts[1].split("/")
                workspace_path = parts[0] + "/migration_" + subparts[0]
            else:
                workspace_path = str(Path(source_path).parent.parent)
        # Check if source_path is a Makefile
        is_makefile = os.path.basename(source_path).lower() in ("makefile", "makefile.txt", "makefile.hip")
        
        # Check if Makefile filenames differ from actual files on disk
        filenames_differ = False
        if is_makefile and workspace_path:
            generated_dir = Path(workspace_path) / "generated"
            filenames_differ = check_makefile_filenames_differ(Path(source_path), generated_dir)
            if filenames_differ:
                logger.warning("[COMPILING] Makefile references source files that do not exist. Falling back to direct hipcc compilation.")
            
        if is_makefile and not filenames_differ:
            cmd = ["make"]
            working_dir = os.path.dirname(os.path.abspath(source_path))
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

            cmd = ["hipcc", *compile_sources]
            for include_dir in include_dirs:
                cmd.extend(["-I", include_dir])
            cmd.extend(["-o", output_path])
            if target_arch:
                cmd.append(f"--offload-arch={target_arch}")
            working_dir = None

        try:
            sandbox_res = run_sandboxed_compiler(workspace_path, cmd, working_dir=working_dir)
            success = (sandbox_res["returncode"] == 0)
            errors = []
            if not success:
                errors = parse_compiler_errors(sandbox_res["stderr"])
                if not errors:
                    errors.append(CompilerError(
                        file=source_path,
                        line=1,
                        column=1,
                        message=sandbox_res["stderr"] or sandbox_res["stdout"] or "Compilation failed with unknown error.",
                        code="E999"
                    ))
                
            return {
                "success": success,
                "binary_path": output_path if success else "",
                "errors": errors,
                "stdout": sandbox_res["stdout"],
                "stderr": sandbox_res["stderr"]
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
                "binary_path": "",
                "errors": [fallback_err],
                "stdout": "",
                "stderr": err_msg
            }


def run_hipcc(source_path: str, output_path: str, target_arch: str = None, workspace_path: str = None) -> Dict[str, Any]:
    """
    Top-level helper function to run hipcc.
    Instantiates and executes the real HipccRunner tool.
    """
    return HipccRunner().run_hipcc(source_path, output_path, target_arch, workspace_path)


