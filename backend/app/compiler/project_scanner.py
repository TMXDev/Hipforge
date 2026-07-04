import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("project_scanner")

# ponytail: error categories are plain strings, no enum framework
NO_PROJECT_FILES = "NO_PROJECT_FILES"
NO_CUDA_CODE = "NO_CUDA_CODE"
EXISTING_HIP_PROJECT = "EXISTING_HIP_PROJECT"
MIXED_CUDA_HIP_PROJECT = "MIXED_CUDA_HIP_PROJECT"
MISSING_BUILD_SYSTEM = "MISSING_BUILD_SYSTEM"
HEADER_ONLY_INPUT = "HEADER_ONLY_INPUT"
NON_CUDA_CPP_PROJECT = "NON_CUDA_CPP_PROJECT"
NESTED_ARCHIVE_INPUT = "NESTED_ARCHIVE_INPUT"
GENERATED_BUILD_PLAN = "GENERATED_BUILD_PLAN"
MULTIPLE_ENTRYPOINTS = "MULTIPLE_ENTRYPOINTS"
NO_ENTRYPOINT = "NO_ENTRYPOINT"
LIBRARY_ONLY_INPUT = "LIBRARY_ONLY_INPUT"

CUDA_EXTENSIONS = {".cu", ".cuh"}
HIP_EXTENSIONS = {".hip"}
CPP_EXTENSIONS = {".cpp", ".cc", ".cxx"}
HEADER_EXTENSIONS = {".h", ".hpp", ".hh"}
BUILD_SYSTEM_FILES = {"makefile", "cmakelists.txt"}
BUILD_SCRIPT_EXTENSIONS = {".mk", ".cmake"}
ALL_SOURCE_EXTENSIONS = CUDA_EXTENSIONS | HIP_EXTENSIONS | CPP_EXTENSIONS | HEADER_EXTENSIONS

# ponytail: simple substring/pattern checks, no AST parsing
CUDA_API_PATTERNS = [
    "cudaMalloc", "cudaMemcpy", "cudaFree", "cudaDeviceSynchronize",
    "cudaStream", "cudaEvent", "cudaGraph", "cudaLaunch",
    "cudaGetDevice", "cudaSetDevice", "cudaGetLastError",
    "cuda_runtime.h", "cuda.h", "cuda_runtime_api.h",
    "__global__", "__device__", "__shared__", "<<<",
    "threadIdx", "blockIdx", "blockDim", "gridDim",
    "CUDA_CALL", "CUDART_CB",
]

HIP_API_PATTERNS = [
    "hipMalloc", "hipMemcpy", "hipFree", "hipDeviceSynchronize",
    "hipStream", "hipEvent", "hipGraph", "hipLaunchKernel",
    "hipGetDevice", "hipSetDevice", "hipGetLastError",
    "hip/hip_runtime.h", "hip_runtime.h", "hip/hip_runtime_api.h",
    "hip/hip_common.h",
]


def _find_entrypoints(files: List[Path]) -> List[str]:
    entrypoints = []
    for f in files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            clean = re.sub(r'//.*', '', content)
            clean = re.sub(r'/\*.*?\*/', '', clean, flags=re.DOTALL)
            if re.search(r'\bmain\s*\(', clean):
                entrypoints.append(str(f))
        except Exception:
            pass
    return entrypoints


def _has_any_pattern(content: str, patterns: List[str]) -> bool:
    lower = content.lower()
    for p in patterns:
        if p.lower() in lower:
            return True
    return False


def scan_project(input_dir: Path) -> Dict:
    cu_files = []
    cuh_files = []
    hip_files = []
    cpp_files = []
    header_files = []
    build_files = []
    all_files = []

    for p in input_dir.rglob("*"):
        if not p.is_file():
            continue
        all_files.append(p)
        suffix = p.suffix.lower()
        name_lower = p.name.lower()
        if suffix == ".cu":
            cu_files.append(p)
        elif suffix == ".cuh":
            cuh_files.append(p)
        elif suffix == ".hip":
            hip_files.append(p)
        elif suffix in CPP_EXTENSIONS:
            cpp_files.append(p)
        elif suffix in HEADER_EXTENSIONS:
            header_files.append(p)
        if name_lower in BUILD_SYSTEM_FILES or suffix in BUILD_SCRIPT_EXTENSIONS:
            build_files.append(p)

    has_build_system = bool(build_files)
    build_system_detected = "none"
    for bf in build_files:
        name = bf.name.lower()
        if name == "cmakelists.txt":
            build_system_detected = "cmake"
        elif name == "makefile":
            build_system_detected = "makefile"
        elif bf.suffix.lower() in BUILD_SCRIPT_EXTENSIONS:
            if build_system_detected == "none":
                build_system_detected = "build_script"

    is_header_only = not (cu_files or cuh_files or hip_files or cpp_files) and bool(header_files)

    has_cuda_files = bool(cu_files or cuh_files)
    has_hip_files = bool(hip_files)
    has_cpp_files = bool(cpp_files)
    has_source_files = bool(cu_files or hip_files or cpp_files)

    # Check content for CUDA/HIP API usage in cpp/header files
    has_cuda_api = False
    has_hip_api = False
    for f in cpp_files + header_files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            if _has_any_pattern(content, CUDA_API_PATTERNS):
                has_cuda_api = True
            if _has_any_pattern(content, HIP_API_PATTERNS):
                has_hip_api = True
        except Exception:
            pass

    # ponytail: single-file detection — first .cu or .hip that looks like a main entry point
    single_entry_point = None
    if len(cu_files) == 1 and not hip_files and not cpp_files:
        single_entry_point = str(cu_files[0])
    elif len(hip_files) == 1 and not cu_files and not cpp_files:
        single_entry_point = str(hip_files[0])
    elif len(cu_files) + len(hip_files) == 1 and len(cpp_files) == 0:
        all_src = cu_files + hip_files
        single_entry_point = str(all_src[0])

    # Entrypoint detection across all source files
    all_source = cu_files + cuh_files + hip_files + cpp_files
    entrypoint_files = _find_entrypoints(all_source)
    entrypoint_count = len(entrypoint_files)

    # Classify project type
    if not all_files:
        category = NO_PROJECT_FILES
        message = "No CUDA/HIP project files were found in the uploaded input."
    elif not has_cuda_files and not has_hip_files and not has_cuda_api and not has_hip_api:
        if has_source_files or has_cpp_files:
            category = NON_CUDA_CPP_PROJECT
            message = "This appears to be a regular C/C++ project with no CUDA/HIP constructs to migrate."
        elif is_header_only:
            category = HEADER_ONLY_INPUT
            message = "Upload contains only header files with no compile entry point."
        else:
            category = NO_PROJECT_FILES
            message = "No CUDA/HIP project files were found in the uploaded input."
    elif has_hip_files and not has_cuda_files and not has_cuda_api:
        category = EXISTING_HIP_PROJECT
        message = "Existing HIP project detected. Skipping hipify."
    elif has_cuda_files or has_cuda_api:
        if has_hip_files or has_hip_api:
            category = MIXED_CUDA_HIP_PROJECT
            message = "Mixed CUDA/HIP project detected. hipify will process only CUDA sources."
        else:
            category = None
            message = "CUDA project detected."
    else:
        category = None
        message = "CUDA project detected."

    has_multiple_source_files = len(cu_files) + len(hip_files) + len(cpp_files) > 1

    compile_strategy = "fail_preflight"
    if category in (NO_PROJECT_FILES, NON_CUDA_CPP_PROJECT, HEADER_ONLY_INPUT):
        compile_strategy = "fail_preflight"
    elif category == EXISTING_HIP_PROJECT and has_multiple_source_files and not has_build_system:
        compile_strategy = "fail_preflight"
    elif has_build_system and build_system_detected == "makefile":
        compile_strategy = "makefile"
    elif has_build_system and build_system_detected == "cmake":
        compile_strategy = "cmake"
    elif has_build_system:
        compile_strategy = "build_script"
    elif entrypoint_count > 1:
        compile_strategy = "fail_preflight"
    elif entrypoint_count == 0 and has_multiple_source_files:
        compile_strategy = "fail_preflight"
    elif has_multiple_source_files and not has_build_system:
        if has_cuda_files or has_cuda_api:
            if has_hip_files or has_hip_api:
                compile_strategy = "generated_mixed_makefile"
            else:
                compile_strategy = "generated_multi_file_makefile"
        elif has_hip_files or has_hip_api:
            compile_strategy = "generated_existing_hip_makefile"
        else:
            compile_strategy = "generated_multi_file_makefile"
    elif has_source_files:
        if len(hip_files) > 0:
            compile_strategy = "generated_existing_hip_makefile"
        else:
            compile_strategy = "generated_single_file_makefile"
    else:
        compile_strategy = "direct_single_file"

    return {
        "category": category,
        "message": message,
        "cu_files": [str(f) for f in cu_files],
        "cuh_files": [str(f) for f in cuh_files],
        "hip_files": [str(f) for f in hip_files],
        "cpp_files": [str(f) for f in cpp_files],
        "header_files": [str(f) for f in header_files],
        "build_files": [str(f) for f in build_files],
        "has_build_system": has_build_system,
        "build_system_detected": build_system_detected,
        "has_cuda_files": has_cuda_files,
        "has_hip_files": has_hip_files,
        "has_cpp_files": has_cpp_files,
        "has_cuda_api": has_cuda_api,
        "has_hip_api": has_hip_api,
        "is_header_only": is_header_only,
        "has_multiple_source_files": has_multiple_source_files,
        "single_entry_point": single_entry_point,
        "entrypoint_files": entrypoint_files,
        "entrypoint_count": entrypoint_count,
        "compile_strategy": compile_strategy,
        "file_count": len(all_files),
    }


def check_nested_zip(input_dir: Path) -> bool:
    for p in input_dir.iterdir():
        if p.suffix.lower() == ".zip":
            import zipfile
            try:
                with zipfile.ZipFile(p, "r") as zf:
                    names = zf.namelist()
                    for name in names:
                        if name.lower().endswith(".zip"):
                            return True
            except Exception:
                pass
    return False


def project_summary_line(scan: Dict) -> str:
    cu = len(scan["cu_files"])
    cuh = len(scan["cuh_files"])
    hip = len(scan["hip_files"])
    cpp = len(scan["cpp_files"])
    hdr = len(scan["header_files"])
    build = scan["build_system_detected"]
    ep = scan.get("entrypoint_count", 0)
    return (
        f"Detected {cu} CUDA file(s), {cuh} CUDA header(s), "
        f"{hip} HIP file(s), {cpp} C/C++ file(s), "
        f"{hdr} header(s). Build system: {build}. "
        f"Entry points: {ep}."
    )
