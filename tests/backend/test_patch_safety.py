"""
tests/backend/test_patch_safety.py

Focused tests for AI-patch safety gate (validate_patch).

Tests:
  1. Localized patch (one-line fix) → accepted.
  2. Broad rewrite (rewrites whole file) → rejected.
  3. Arch-sensitive patch (warpSize changed) without runtime validation → accepted
     with a non-None arch_warning.

Run with:
  pytest tests/backend/test_patch_safety.py -v
"""

import os
import tempfile
from pathlib import Path

import pytest

os.environ["USE_MOCK_AI"] = "true"
os.environ["USE_MOCK_COMPILER"] = "true"

from app.agents.patch_agent import validate_patch

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_ORIGINAL = """\
#include <hip/hip_runtime.h>

__global__ void kernel(float* dst, float* src, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) dst[i] = src[i];
}

void transfer(float* dst, float* src, int n, hipStream_t s) {
    hipMemcpyAsync_WRONG(dst, src, n * sizeof(float), hipMemcpyDeviceToDevice, s);
}
"""

_LOCALIZED_PATCH = _ORIGINAL.replace(
    "hipMemcpyAsync_WRONG(dst, src, n * sizeof(float), hipMemcpyDeviceToDevice, s);",
    "hipMemcpyAsync(dst, src, n * sizeof(float), hipMemcpyDeviceToDevice, s);",
)

_ANALYSIS = {
    "root_cause": "hipMemcpyAsync_WRONG is not a valid HIP API.",
    "affected_files": ["kernel.hip"],
    "repair_plan": ["Replace hipMemcpyAsync_WRONG with hipMemcpyAsync on the transfer function call."],
}

# ---------------------------------------------------------------------------
# Test 1: localized patch → accepted
# ---------------------------------------------------------------------------

def test_localized_patch_accepted(tmp_path):
    patch_file = tmp_path / "patches" / "patch_001_kernel.hip"
    patch_file.parent.mkdir(parents=True)

    result = validate_patch(
        original=_ORIGINAL,
        patched=_LOCALIZED_PATCH,
        workspace_root=str(tmp_path),
        patch_file_path=str(patch_file),
        analysis=_ANALYSIS,
        runtime_validated=False,
    )

    assert result["accepted"] is True, f"Expected accepted, got: {result['reason']}"
    assert result["changed_lines"] > 0
    assert result["before_hash"] != result["after_hash"]
    assert "---" in result["diff"] or "+++" in result["diff"]
    assert result["diagnosis"]  # non-empty
    assert result["arch_warning"] is None  # no arch-sensitive code


# ---------------------------------------------------------------------------
# Test 2: broad rewrite → rejected
# ---------------------------------------------------------------------------

def _make_big_source(n_lines: int = 300) -> str:
    """Generate a multi-function source large enough to trigger the removal check."""
    lines = ["#include <hip/hip_runtime.h>\n"]
    for i in range(n_lines):
        lines.append(f"// line {i}\n")
    lines.append("void foo() {}\n")
    return "".join(lines)


def test_broad_rewrite_rejected(tmp_path):
    original = _make_big_source(300)
    # Broad rewrite: replace with a one-liner (removes >40% of lines)
    broad_patch = "#include <hip/hip_runtime.h>\nvoid foo() {}\n"

    patch_file = tmp_path / "patches" / "patch_001_kernel.hip"
    patch_file.parent.mkdir(parents=True)

    result = validate_patch(
        original=original,
        patched=broad_patch,
        workspace_root=str(tmp_path),
        patch_file_path=str(patch_file),
        analysis=_ANALYSIS,
        runtime_validated=False,
    )

    assert result["accepted"] is False, "Expected broad rewrite to be rejected"
    assert "rewrite" in result["reason"].lower() or "exceeds" in result["reason"].lower() or "removes" in result["reason"].lower()
    # Audit fields must still be present even on rejection
    assert result["before_hash"]
    assert result["after_hash"]
    assert result["changed_lines"] > 0


# ---------------------------------------------------------------------------
# Test 3: arch-sensitive patch → accepted with arch_warning
# ---------------------------------------------------------------------------

_ARCH_ORIGINAL = """\
#include <hip/hip_runtime.h>

__global__ void reduce(float* data, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    float val = (i < n) ? data[i] : 0.0f;
    // WRONG: hardcoded warp size 32
    for (int offset = 32; offset > 0; offset >>= 1)
        val += __shfl_down(val, offset);
    if (i < n) data[i] = val;
}
"""

_ARCH_PATCHED = _ARCH_ORIGINAL.replace(
    "for (int offset = 32; offset > 0; offset >>= 1)\n        val += __shfl_down(val, offset);",
    "for (int offset = warpSize / 2; offset > 0; offset >>= 1)\n        val += __shfl_down(val, offset);",
)

_ARCH_ANALYSIS = {
    "root_cause": "Hardcoded warp size 32 breaks on CDNA (warpSize=64).",
    "affected_files": ["kernel.hip"],
    "repair_plan": ["Replace hardcoded 32 with warpSize to be architecture-portable."],
}


def test_arch_sensitive_patch_warns(tmp_path):
    patch_file = tmp_path / "patches" / "patch_001_reduce.hip"
    patch_file.parent.mkdir(parents=True)

    result = validate_patch(
        original=_ARCH_ORIGINAL,
        patched=_ARCH_PATCHED,
        workspace_root=str(tmp_path),
        patch_file_path=str(patch_file),
        analysis=_ARCH_ANALYSIS,
        runtime_validated=False,  # no runtime validation → warning expected
    )

    assert result["accepted"] is True, f"Arch patch should be accepted: {result['reason']}"
    assert result["arch_warning"] is not None, "Expected an arch_warning for warpSize/shfl change"
    assert "runtime" in result["arch_warning"].lower() or "architecture" in result["arch_warning"].lower()
    # No warning when runtime_validated=True
    result_validated = validate_patch(
        original=_ARCH_ORIGINAL,
        patched=_ARCH_PATCHED,
        workspace_root=str(tmp_path),
        patch_file_path=str(patch_file),
        analysis=_ARCH_ANALYSIS,
        runtime_validated=True,
    )
    assert result_validated["arch_warning"] is None, "No warning expected when runtime validated"
