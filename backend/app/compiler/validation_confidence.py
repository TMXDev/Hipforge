"""
backend/app/compiler/validation_confidence.py

Deterministic validation confidence classifier.

HIPForge v0 claims "compile-validated migration" by default.
Runtime execution is optional and disabled unless RUNTIME_VALIDATION_ENABLED=true.

Confidence ladder:
  LOW      - hipify ran, compile failed
  MEDIUM   - hipify + compile both succeeded; no runtime execution
  HIGH     - compile succeeded + runtime execution passed on AMD GPU
  PROFILED - HIGH + profiling data collected
"""

# ponytail: plain strings, no enum — same pattern as error_parser.py categories
LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"
PROFILED = "PROFILED"

_REASONS = {
    LOW: "hipify completed but compilation failed",
    MEDIUM: "hipify and compilation succeeded; runtime execution was not performed",
    HIGH: "hipify, compilation, and runtime execution on AMD GPU all passed",
    PROFILED: "runtime validation passed and profiling data was collected",
}


def compute_confidence(
    hipify_ok: bool,
    compile_ok: bool,
    runtime_ok: bool = False,
    profiled: bool = False,
) -> tuple[str, str]:
    """
    Returns (confidence_level, reason) deterministically.

    Args:
        hipify_ok:  hipify-clang ran and produced output
        compile_ok: hipcc/make exited 0
        runtime_ok: binary was executed on AMD GPU and output verified
        profiled:   rocprof or equivalent collected profiling data

    Returns (level, reason) — never raises.
    """
    if not hipify_ok or not compile_ok:
        return LOW, _REASONS[LOW]
    if profiled:
        return PROFILED, _REASONS[PROFILED]
    if runtime_ok:
        return HIGH, _REASONS[HIGH]
    return MEDIUM, _REASONS[MEDIUM]


if __name__ == "__main__":
    # ponytail: self-check — fails if logic breaks
    assert compute_confidence(False, False) == (LOW, _REASONS[LOW])
    assert compute_confidence(True, False) == (LOW, _REASONS[LOW])
    assert compute_confidence(True, True) == (MEDIUM, _REASONS[MEDIUM])
    assert compute_confidence(True, True, runtime_ok=True) == (HIGH, _REASONS[HIGH])
    assert compute_confidence(True, True, runtime_ok=True, profiled=True) == (PROFILED, _REASONS[PROFILED])
    print("validation_confidence: all assertions passed")
