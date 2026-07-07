"""
test_architecture_advisor.py — Self-check for architecture_advisor.py.

Covers:
- user_selected priority (never overridden by detected GPU)
- fallback_default when nothing is detected
- CUDA hint scanning
- Risk pattern detection
- advise() result structure

No mocking of subprocess; GPU detection is allowed to return [] in CI.
"""
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.compiler.architecture_advisor import advise, scan_cuda_arch_hints, scan_risk_patterns, ArchAdvice


# ── advise(): user_selected priority ─────────────────────────────────────────

def test_user_arch_always_wins():
    advice = advise(user_arch="gfx942", configured_default="gfx90a", workspace_path=None)
    assert advice.selected_arch == "gfx942"
    assert advice.selection_source == "user_selected"


def test_invalid_user_arch_falls_through():
    """An invalid gfx string (fails regex) must not be used; fallback to detected/configured/default."""
    advice = advise(user_arch="sm_80", configured_default="gfx940", workspace_path=None)
    # sm_80 doesn't match ^gfx\d{2,4}[a-z]?$ so it is treated as no user selection
    assert advice.selected_arch != "sm_80"
    assert advice.selection_source in {"detected_gpu", "configured_default", "fallback_default"}


def test_configured_default_used_when_no_gpu_detected(monkeypatch):
    import app.compiler.architecture_advisor as aa
    monkeypatch.setattr(aa, "detect_amd_gpu_arches", lambda: [])
    advice = advise(user_arch=None, configured_default="gfx906", workspace_path=None)
    assert advice.selected_arch == "gfx906"
    assert advice.selection_source == "configured_default"
    assert advice.confidence == "MEDIUM"


def test_fallback_default_when_nothing(monkeypatch):
    import app.compiler.architecture_advisor as aa
    monkeypatch.setattr(aa, "detect_amd_gpu_arches", lambda: [])
    advice = advise(user_arch=None, configured_default=None, workspace_path=None)
    assert advice.selected_arch == "gfx90a"
    assert advice.selection_source == "fallback_default"
    assert advice.confidence == "LOW"


def test_detected_gpu_used_when_no_user_arch(monkeypatch):
    import app.compiler.architecture_advisor as aa
    monkeypatch.setattr(aa, "detect_amd_gpu_arches", lambda: ["gfx941"])
    advice = advise(user_arch=None, configured_default=None, workspace_path=None)
    assert advice.selected_arch == "gfx941"
    assert advice.selection_source == "detected_gpu"
    assert advice.confidence == "HIGH"


# ── scan_cuda_arch_hints ───────────────────────────────────────────────────────

def test_cuda_hint_scanning():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "kernel.cu"
        p.write_text("// compile: -gencode arch=compute_80,code=sm_80\n__global__ void f() {}")
        hints = scan_cuda_arch_hints(tmp)
        assert any("sm_80" in h or "gencode" in h or "compute_80" in h for h in hints)


def test_no_hints_in_clean_file():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "clean.cu"
        p.write_text("__global__ void f() { int x = 1; }\nint main() { return 0; }")
        hints = scan_cuda_arch_hints(tmp)
        assert hints == []


# ── scan_risk_patterns ────────────────────────────────────────────────────────

def test_risk_warp_size_detected():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "warp.cu"
        p.write_text("int w = warpSize; // careful on AMD\n")
        warnings = scan_risk_patterns(tmp)
        assert any("warpSize" in w for w in warnings)


def test_risk_ptx_asm_detected():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "ptx.cu"
        p.write_text('asm volatile("mov.u32 %0, %%laneid;" : "=r"(lane)); ')
        warnings = scan_risk_patterns(tmp)
        assert any("PTX" in w or "asm" in w for w in warnings)


def test_no_risk_in_clean_file():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "clean.cu"
        p.write_text("__global__ void add(int *a, int *b) { *a += *b; }")
        warnings = scan_risk_patterns(tmp)
        assert warnings == []


# ── ArchAdvice.to_dict ────────────────────────────────────────────────────────

def test_to_dict_structure():
    advice = advise(user_arch="gfx90a", configured_default=None, workspace_path=None)
    d = advice.to_dict()
    for key in ("selected_arch", "selection_source", "confidence", "detected_arches",
                "cuda_arch_hints", "risk_warnings", "recommended_actions"):
        assert key in d, f"Missing key: {key}"


if __name__ == "__main__":
    import traceback

    tests = [
        test_user_arch_always_wins,
        test_invalid_user_arch_falls_through,
        test_no_hints_in_clean_file,
        test_risk_warp_size_detected,
        test_risk_ptx_asm_detected,
        test_no_risk_in_clean_file,
        test_to_dict_structure,
    ]

    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(failed)
