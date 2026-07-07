"""
architecture_advisor.py — Lightweight AMD target architecture advisor.

Produces a structured ArchAdvice result used to:
  - Report selection source and confidence
  - Surface CUDA arch hints from source files
  - Flag architecture-sensitive risk patterns

ponytail: subprocess + re only. No new deps.
"""
import re
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("architecture_advisor")

# ── Risk patterns ──────────────────────────────────────────────────────────────
_RISK_PATTERNS: List[tuple] = [
    (r"\basm\s*(volatile)?\s*\(", "inline PTX/asm: requires manual rewrite for HIP"),
    (r"\bwarpSize\b", "warpSize: AMD warp size is 64 on most targets (NVIDIA is 32); check divergence logic"),
    (r"\b__shfl(?:_sync|_down|_up|_xor)?\b", "__shfl* warp shuffle: behavior differs between AMD and NVIDIA"),
    (r"\b__ballot(?:_sync)?\b", "__ballot*: AMD equivalent exists but lane semantics differ"),
    (r"\b__syncwarp\b", "__syncwarp: no direct AMD equivalent; use __syncthreads or wave-level ops"),
    (r"\bcooperative_groups\b", "cooperative groups: partial HIP support; verify feature parity"),
    (r"\btex(?:1D|2D|3D|Fetch|Object)\b", "texture API: HIP texture support exists but surface APIs differ"),
    (r"\bcuBLAS\b|\bhipBLAS\b(?! )", "cuBLAS: must be replaced with hipBLAS"),
    (r"\bcuDNN\b", "cuDNN: MIOpen is the AMD equivalent"),
    (r"\bcuRAND\b", "cuRAND: hipRAND is the AMD equivalent"),
    (r"\bNCCL\b", "NCCL: RCCL is the AMD equivalent"),
    (r"\b__half\b|\bhalf2\b", "FP16 __half: HIP supports __half but behavior may vary per arch"),
    (r"\b__nv_bfloat16\b", "BF16 __nv_bfloat16: use hip_bfloat16 on AMD"),
    (r"\b__CUDA_ARCH__\b", "hardcoded __CUDA_ARCH__ macro: replace with __HIP_DEVICE_COMPILE__ / __gfx* macros"),
]

# ── CUDA arch hint patterns ────────────────────────────────────────────────────
_CUDA_ARCH_HINTS = [
    r"\bsm_\d+\b",
    r"\bcompute_\d+\b",
    r"\bCUDA_ARCH\b",
    r"\bCMAKE_CUDA_ARCHITECTURES\b",
    r"-gencode\b",
    r"--generate-code\b",
]
_CUDA_ARCH_RE = re.compile("|".join(_CUDA_ARCH_HINTS))

# ── Known valid gfx targets ────────────────────────────────────────────────────
_VALID_GFX_RE = re.compile(r"^gfx\d{2,4}[a-z]?$")


@dataclass
class ArchAdvice:
    selected_arch: str
    # detected_gpu | user_selected | configured_default | fallback_default | unknown
    selection_source: str
    # HIGH | MEDIUM | LOW
    confidence: str
    detected_arches: List[str] = field(default_factory=list)
    cuda_arch_hints: List[str] = field(default_factory=list)
    risk_warnings: List[str] = field(default_factory=list)
    recommended_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "selected_arch": self.selected_arch,
            "selection_source": self.selection_source,
            "confidence": self.confidence,
            "detected_arches": self.detected_arches,
            "cuda_arch_hints": self.cuda_arch_hints,
            "risk_warnings": self.risk_warnings,
            "recommended_actions": self.recommended_actions,
        }


def detect_amd_gpu_arches() -> List[str]:
    """
    Try amdgpu-arch then rocminfo to discover installed AMD GPU architectures.
    Returns list of gfx strings or [] on failure/unavailability.
    ponytail: two safe subprocess calls; both non-fatal.
    """
    # Try amdgpu-arch first (ships with ROCm, fast)
    try:
        result = subprocess.run(
            ["amdgpu-arch"],
            capture_output=True, text=True, timeout=5
        )
        arches = [l.strip() for l in result.stdout.splitlines() if _VALID_GFX_RE.match(l.strip())]
        if arches:
            logger.info("[arch_advisor] amdgpu-arch detected: %s", arches)
            return arches
    except Exception as e:
        logger.debug("[arch_advisor] amdgpu-arch not available: %s", e)

    # Fallback: rocminfo
    try:
        result = subprocess.run(
            ["rocminfo"],
            capture_output=True, text=True, timeout=10
        )
        arches = re.findall(r"gfx\d{2,4}[a-z]?", result.stdout)
        arches = sorted(set(a for a in arches if _VALID_GFX_RE.match(a)))
        if arches:
            logger.info("[arch_advisor] rocminfo detected: %s", arches)
            return arches
    except Exception as e:
        logger.debug("[arch_advisor] rocminfo not available: %s", e)

    return []


def scan_cuda_arch_hints(workspace_path: str) -> List[str]:
    """
    Grep source/build files for CUDA arch flags (sm_XX, compute_XX, -gencode, etc.).
    Returns unique sorted hint strings found. Does not map CUDA → AMD arches.
    ponytail: re.findall over text files; no new deps.
    """
    hints: set = set()
    root = Path(workspace_path)
    extensions = {".cu", ".cuh", ".cpp", ".c", ".h", ".hpp", ".cmake", "CMakeLists.txt", "Makefile"}

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in extensions and p.name not in extensions:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            for m in _CUDA_ARCH_RE.findall(text):
                hints.add(m.strip())
        except Exception:
            pass

    return sorted(hints)


def scan_risk_patterns(workspace_path: str) -> List[str]:
    """
    Scan source files for architecture-sensitive patterns.
    Returns deduplicated warning strings.
    """
    seen: set = set()
    warnings: List[str] = []
    root = Path(workspace_path)

    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in {".cu", ".cuh", ".cpp", ".c", ".h", ".hpp"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for pattern, msg in _RISK_PATTERNS:
            if msg in seen:
                continue
            if re.search(pattern, text):
                seen.add(msg)
                warnings.append(msg)

    return warnings


def advise(
    user_arch: Optional[str],
    configured_default: Optional[str],
    workspace_path: Optional[str],
) -> ArchAdvice:
    """
    Main entry point. Determine selected_arch, source, confidence, scan hints and risks.

    Priority order:
      1. user_arch (user explicitly selected) — never overridden
      2. detected local AMD GPU
      3. configured_default (env/config)
      4. hardcoded fallback "gfx90a"
    """
    detected = []
    try:
        detected = detect_amd_gpu_arches()
    except Exception as e:
        logger.warning("[arch_advisor] GPU detection failed: %s", e)

    cuda_hints: List[str] = []
    risk_warnings: List[str] = []
    if workspace_path:
        try:
            cuda_hints = scan_cuda_arch_hints(workspace_path)
        except Exception as e:
            logger.warning("[arch_advisor] CUDA hint scan failed: %s", e)
        try:
            risk_warnings = scan_risk_patterns(workspace_path)
        except Exception as e:
            logger.warning("[arch_advisor] Risk pattern scan failed: %s", e)

    recommended: List[str] = []

    # ── Determine selected_arch and source ───────────────────────────────
    if user_arch and _VALID_GFX_RE.match(user_arch):
        selected = user_arch
        source = "user_selected"
        confidence = "MEDIUM"  # user knows their target; we can't verify at compile time
        if detected and selected not in detected:
            recommended.append(
                f"Selected target '{selected}' does not match detected local AMD GPU(s): "
                f"{', '.join(detected)}. Binary compiled for '{selected}' may not run on the local machine."
            )
    elif detected:
        selected = detected[0]
        source = "detected_gpu"
        confidence = "HIGH"
        recommended.append(
            f"Architecture '{selected}' was detected from installed AMD GPU hardware."
        )
    elif configured_default and _VALID_GFX_RE.match(configured_default):
        selected = configured_default
        source = "configured_default"
        confidence = "MEDIUM"
        recommended.append(
            f"No GPU detected locally. Using configured default '{selected}'."
        )
    else:
        selected = "gfx90a"
        source = "fallback_default"
        confidence = "LOW"
        recommended.append(
            "No AMD GPU detected and no configured default. Falling back to gfx90a (MI200). "
            "Code alone cannot determine the correct target; specify --arch explicitly."
        )

    if cuda_hints:
        recommended.append(
            f"CUDA architecture flags found in source: {', '.join(cuda_hints)}. "
            "These are hints only — they do not map directly to AMD gfx targets."
        )

    if risk_warnings:
        recommended.append(
            "Architecture-sensitive patterns detected. Review warnings before assuming "
            "compile success equals runtime correctness."
        )

    # Honest caveat always present
    recommended.append(
        "Source code analysis alone cannot perfectly determine the correct AMD GPU target. "
        "Detected hardware or explicit user selection is more reliable."
    )

    return ArchAdvice(
        selected_arch=selected,
        selection_source=source,
        confidence=confidence,
        detected_arches=detected,
        cuda_arch_hints=cuda_hints,
        risk_warnings=risk_warnings,
        recommended_actions=recommended,
    )
