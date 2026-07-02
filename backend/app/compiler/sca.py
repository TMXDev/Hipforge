"""
backend/app/compiler/sca.py

Semantic Compatibility Analyzer (SCA)

A deterministic inspection engine that scans translated HIP source code for
CUDA constructs known to behave differently on AMD hardware.

Per docs/10_COMPILATION_PIPELINE.md (Stage 2.5):
  - The SCA never modifies code.
  - It produces a structured compatibility report (migration_risks.json).
  - The report is attached to the Workflow Context for use by AI agents.

Returns:
    {
        "issues": List[CompatibilityIssue],
        "score":  float   # 0.0 (fully incompatible) to 1.0 (fully compatible)
    }

Detected pattern categories (10 per spec):
  1.  warpSize assumptions
  2.  Cooperative Groups
  3.  Inline PTX
  4.  Dynamic Shared Memory
  5.  CUDA Graphs
  6.  Texture References
  7.  Surface References
  8.  Tensor Core intrinsics
  9.  CUB
  10. Thrust
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any

from app.models.compatibility_issue import CompatibilityIssue


# ---------------------------------------------------------------------------
# Pattern registry
# Each entry defines one detectable semantic risk.
#
# Fields:
#   pattern_id   – Unique rule identifier (used in migration_risks.json)
#   category     – Human-readable category name (matches spec list)
#   severity     – "high" | "medium" | "low"
#   regex        – Compiled regular expression matched against each source line
#   description  – Why this is a migration risk on AMD hardware
#   recommendation – What the developer or AI patch agent should do
# ---------------------------------------------------------------------------

_PATTERNS: List[Dict[str, Any]] = [
    # ------------------------------------------------------------------
    # 1. warpSize assumptions
    # Hardcoded warp size of 32 is NVIDIA-specific; AMD wavefront = 64 (GCN)
    # or 32 (RDNA). Using __builtin_amdgcn_wavefrontsize() is the safe path.
    # ------------------------------------------------------------------
    {
        "pattern_id": "WARP_SIZE_ASSUMPTION_LITERAL",
        "category": "warpSize assumptions",
        "severity": "high",
        "regex": re.compile(
            r"\b32\b(?=\s*[;,)\]/*%]|\s*==|\s*!=|\s*<<|\s*>>)",
        ),
        "description": (
            "Literal value 32 used where warp/wavefront size is assumed. "
            "AMD GCN hardware uses a wavefront size of 64; RDNA uses 32 but "
            "this is not guaranteed. Hardcoding 32 produces incorrect results "
            "on GCN devices."
        ),
        "recommendation": (
            "Replace the literal 32 with warpSize (HIP runtime variable) or "
            "__builtin_amdgcn_wavefrontsize() for compile-time use."
        ),
    },
    {
        "pattern_id": "WARP_SIZE_ASSUMPTION_SYMBOL",
        "category": "warpSize assumptions",
        "severity": "high",
        "regex": re.compile(r"\bwarpSize\b"),
        "description": (
            "warpSize is used directly. While HIP exposes warpSize, its value "
            "differs per AMD architecture (32 for RDNA, 64 for GCN). Code that "
            "assumes warpSize == 32 at compile time will be incorrect on GCN."
        ),
        "recommendation": (
            "Avoid compile-time branching on warpSize. Prefer runtime checks "
            "or use architecture-specific compile flags (e.g. __gfx__) when "
            "wavefront-size-dependent logic is required."
        ),
    },
    # ------------------------------------------------------------------
    # 2. Cooperative Groups
    # HIP supports cooperative groups but with limited feature parity.
    # grid_group and multi-device groups are not fully supported on all ROCm.
    # ------------------------------------------------------------------
    {
        "pattern_id": "COOPERATIVE_GROUPS",
        "category": "Cooperative Groups",
        "severity": "high",
        "regex": re.compile(
            r"\b(?:cooperative_groups|cg::|grid_group|thread_block_tile|"
            r"coalesced_group|__syncthreads_count|__syncthreads_and|"
            r"__syncthreads_or)\b"
        ),
        "description": (
            "CUDA Cooperative Groups API detected. HIP provides partial "
            "cooperative group support, but grid-wide and multi-device groups "
            "require ROCm 4.x+ and specific kernel launch flags "
            "(hipLaunchCooperativeKernel). Not all group types are available."
        ),
        "recommendation": (
            "Verify ROCm cooperative group support for the target hardware. "
            "Replace unsupported group types with HIP equivalents or restructure "
            "synchronisation using __syncthreads() / __builtin_amdgcn_s_barrier()."
        ),
    },
    # ------------------------------------------------------------------
    # 3. Inline PTX
    # PTX is NVIDIA-specific assembly. AMD uses GCN/RDNA ISA.
    # Inline PTX is entirely unsupported under HIP/ROCm.
    # ------------------------------------------------------------------
    {
        "pattern_id": "INLINE_PTX",
        "category": "Inline PTX",
        "severity": "high",
        "regex": re.compile(
            r"\b(?:asm\s+volatile|__asm__|__asm)\s*\("
            r"|\"(?:mov|add|mul|mad|setp|bra|ret|ld|st|cvt|atom|bar|membar)\."
        ),
        "description": (
            "Inline PTX assembly detected. PTX is an NVIDIA-specific intermediate "
            "representation and is completely unsupported on AMD hardware. "
            "The compiler will reject these blocks."
        ),
        "recommendation": (
            "Remove all inline PTX blocks. Replace NVIDIA intrinsics with "
            "HIP device intrinsics (e.g. __hip_hlt, __builtin_amdgcn_*) or "
            "standard C++ equivalents where possible."
        ),
    },
    # ------------------------------------------------------------------
    # 4. Dynamic Shared Memory
    # extern __shared__ is valid in HIP but array-of-struct patterns and
    # multiple dynamic shared memory arrays require special handling.
    # ------------------------------------------------------------------
    {
        "pattern_id": "DYNAMIC_SHARED_MEMORY",
        "category": "Dynamic Shared Memory",
        "severity": "medium",
        "regex": re.compile(r"\bextern\s+__shared__\b"),
        "description": (
            "Dynamic shared memory (extern __shared__) detected. HIP supports "
            "this pattern, but multi-type dynamic shared memory (casting a single "
            "extern array to different types) may produce incorrect padding or "
            "aliasing behaviour on AMD hardware compared to CUDA."
        ),
        "recommendation": (
            "Verify that dynamic shared memory is only used as a single type per "
            "kernel. If multiple types are needed, use static shared memory or "
            "structure the allocations carefully with explicit byte-level offsets."
        ),
    },
    # ------------------------------------------------------------------
    # 5. CUDA Graphs
    # hipGraph support was added in ROCm 4.5 but is not feature-complete.
    # ------------------------------------------------------------------
    {
        "pattern_id": "CUDA_GRAPHS",
        "category": "CUDA Graphs",
        "severity": "high",
        "regex": re.compile(
            r"\b(?:cudaGraphCreate|cudaGraph_t|cudaStreamBeginCapture|"
            r"cudaStreamEndCapture|cudaGraphLaunch|cudaGraphInstantiate|"
            r"hipGraphCreate|hipGraph_t|hipStreamBeginCapture)\b"
        ),
        "description": (
            "CUDA/HIP Graph API detected. Graph capture and instantiation require "
            "ROCm 4.5+ and are not supported on all AMD GPU architectures. "
            "Some graph node types (e.g. conditional nodes) remain unimplemented."
        ),
        "recommendation": (
            "Check ROCm release notes for graph API coverage. Replace unsupported "
            "graph operations with standard stream-ordered launches, or guard "
            "graph usage with runtime capability checks."
        ),
    },
    # ------------------------------------------------------------------
    # 6. Texture References
    # Texture reference API is deprecated in CUDA 11+ and unsupported in HIP.
    # Texture objects (cudaCreateTextureObject) have limited HIP equivalents.
    # ------------------------------------------------------------------
    {
        "pattern_id": "TEXTURE_REFERENCES",
        "category": "Texture References",
        "severity": "high",
        "regex": re.compile(
            r"\b(?:texture\s*<|tex1D|tex2D|tex3D|tex1Dfetch|tex2Dgather|"
            r"cudaBindTexture|cudaUnbindTexture|cudaCreateTextureObject|"
            r"cudaDestroyTextureObject|hipCreateTextureObject|"
            r"hipDestroyTextureObject)\b"
        ),
        "description": (
            "CUDA Texture API detected. The legacy texture reference API "
            "(texture<T, dim>) is unsupported in HIP. Texture object APIs "
            "are partially supported but with different hardware sampling "
            "characteristics on AMD GPUs."
        ),
        "recommendation": (
            "Replace legacy texture references with HIP texture objects. "
            "Validate sampling results on AMD hardware, as interpolation and "
            "addressing modes may differ from CUDA. Consider using global "
            "memory with manual interpolation for portability."
        ),
    },
    # ------------------------------------------------------------------
    # 7. Surface References
    # Surface references are NVIDIA-only; HIP has no equivalent API.
    # ------------------------------------------------------------------
    {
        "pattern_id": "SURFACE_REFERENCES",
        "category": "Surface References",
        "severity": "high",
        "regex": re.compile(
            r"\b(?:surface\s*<|surf1Dread|surf1Dwrite|surf2Dread|surf2Dwrite|"
            r"surf3Dread|surf3Dwrite|cudaBindSurface|cudaCreateSurfaceObject|"
            r"cudaDestroySurfaceObject)\b"
        ),
        "description": (
            "CUDA Surface API detected. Surface references and surface objects "
            "have no direct HIP equivalent and are not supported in ROCm. "
            "This will cause compilation failures."
        ),
        "recommendation": (
            "Replace surface reads/writes with global memory buffer operations "
            "or HIP image APIs if available for your target architecture. "
            "This may require significant algorithmic restructuring."
        ),
    },
    # ------------------------------------------------------------------
    # 8. Tensor Core intrinsics
    # WMMA (warp matrix multiply accumulate) is NVIDIA Volta+ only.
    # AMD equivalent is rocWMMA but with different API and tile sizes.
    # ------------------------------------------------------------------
    {
        "pattern_id": "TENSOR_CORE_INTRINSICS",
        "category": "Tensor Core intrinsics",
        "severity": "high",
        "regex": re.compile(
            r"\b(?:wmma::|nvcuda::wmma|__hmma_m|mma\.sync|"
            r"load_matrix_sync|store_matrix_sync|mma_sync|"
            r"fill_fragment|fragment<)\b"
        ),
        "description": (
            "CUDA Tensor Core / WMMA API detected. NVIDIA WMMA intrinsics "
            "target Volta/Turing Tensor Cores and are unavailable on AMD hardware. "
            "AMD provides rocWMMA for CDNA2+ GPUs with different tile shapes "
            "and a distinct API surface."
        ),
        "recommendation": (
            "Replace nvcuda::wmma calls with rocwmma:: equivalents from the "
            "rocWMMA library. Verify that target AMD GPU supports matrix "
            "operations (CDNA2/RDNA3+). Tile sizes and fragment layouts differ."
        ),
    },
    # ------------------------------------------------------------------
    # 9. CUB
    # CUB is NVIDIA's CUDA UnBound primitives library.
    # AMD equivalent is rocPRIM (different API).
    # ------------------------------------------------------------------
    {
        "pattern_id": "CUB_USAGE",
        "category": "CUB",
        "severity": "medium",
        "regex": re.compile(
            r"(?:#\s*include\s*[<\"]cub/|(?:^|\s)cub::)",
            re.MULTILINE,
        ),
        "description": (
            "NVIDIA CUB (CUDA UnBound) library detected. CUB provides "
            "device-wide and warp-level primitives (scan, reduce, sort) that "
            "are tightly coupled to CUDA internals and unavailable in HIP."
        ),
        "recommendation": (
            "Replace CUB includes and calls with rocPRIM equivalents "
            "(#include <rocprim/rocprim.hpp>, hipcub:: namespace). "
            "hipCUB is a thin wrapper that translates CUB APIs to rocPRIM "
            "and may reduce porting effort."
        ),
    },
    # ------------------------------------------------------------------
    # 10. Thrust
    # Thrust is NVIDIA's high-level parallel algorithms library.
    # AMD provides rocThrust as an equivalent.
    # ------------------------------------------------------------------
    {
        "pattern_id": "THRUST_USAGE",
        "category": "Thrust",
        "severity": "medium",
        "regex": re.compile(
            r"(?:#\s*include\s*[<\"]thrust/|(?:^|\s)thrust::)",
            re.MULTILINE,
        ),
        "description": (
            "NVIDIA Thrust library detected. Thrust provides STL-like parallel "
            "algorithms on CUDA devices. It is not directly available in HIP "
            "and requires replacement with rocThrust."
        ),
        "recommendation": (
            "Replace Thrust includes with rocThrust equivalents "
            "(#include <thrust/...> with ROCm Thrust or "
            "hipify the Thrust calls to rocThrust). Validate algorithm "
            "behaviour, as execution policies and iterator semantics may differ."
        ),
    },
]


# ---------------------------------------------------------------------------
# Severity weights used to compute the compatibility score.
# Score = 1.0 - (sum of weights for all issues, capped at 1.0).
# High-severity issues carry the most weight.
# ---------------------------------------------------------------------------

_SEVERITY_WEIGHT: Dict[str, float] = {
    "high": 0.15,
    "medium": 0.07,
    "low": 0.03,
}


def analyze(source_path: str) -> Dict[str, Any]:
    """
    Scan a translated HIP source file for semantic compatibility issues.

    This function performs deterministic, regex-based pattern matching.
    It never modifies the source file.

    Args:
        source_path: Absolute or relative path to the HIP source file to scan.

    Returns:
        A dict with two keys:
            "issues" – List[CompatibilityIssue] for every pattern match found.
            "score"  – float in [0.0, 1.0] representing overall compatibility.
                       1.0 = no issues detected.
                       0.0 = maximum incompatibility (score floor is 0.0).

    Raises:
        FileNotFoundError: If the source file does not exist.
        IOError: If the source file cannot be read.
    """
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"SCA: source file not found: {source_path}")

    source_text = path.read_text(encoding="utf-8", errors="replace")
    source_lines = source_text.splitlines()
    filename = path.name

    issues: List[CompatibilityIssue] = []

    for pattern in _PATTERNS:
        pid = pattern["pattern_id"]
        category = pattern["category"]
        severity = pattern["severity"]
        regex: re.Pattern = pattern["regex"]
        description = pattern["description"]
        recommendation = pattern["recommendation"]

        # Scan line by line so we can report accurate line/column info.
        for line_idx, line_text in enumerate(source_lines, start=1):
            match = regex.search(line_text)
            if match:
                issues.append(
                    CompatibilityIssue(
                        pattern_id=pid,
                        category=category,
                        severity=severity,
                        file=filename,
                        line=line_idx,
                        column=match.start(),
                        source_snippet=line_text.strip(),
                        description=description,
                        recommendation=recommendation,
                    )
                )
                # Report at most one issue per pattern per file to avoid
                # flooding the report with repeated matches of the same rule.
                break

    # Compute compatibility score.
    # Each distinct issue deducts a fixed weight based on severity.
    # The score is floored at 0.0 to avoid negative values.
    penalty = sum(_SEVERITY_WEIGHT.get(issue.severity, 0.0) for issue in issues)
    score = max(0.0, round(1.0 - penalty, 4))

    return {
        "issues": issues,
        "score": score,
    }


def write_migration_risks(result: Dict[str, Any], output_path: str) -> None:
    """
    Serialise the SCA result to migration_risks.json.

    This file is required by the pipeline spec (docs/10_COMPILATION_PIPELINE.md).

    Args:
        result:      The dict returned by analyze().
        output_path: Full path to write the migration_risks.json file.
    """
    serialisable = {
        "score": result["score"],
        "issues": [issue.model_dump() for issue in result["issues"]],
    }
    Path(output_path).write_text(
        json.dumps(serialisable, indent=2),
        encoding="utf-8",
    )
