"""
tests/backend/test_validation_confidence.py

Tests for validation confidence classification, runtime validation defaults,
last_compile_command safety, and report field completeness.

All tests run in mock mode (no real ROCm tools required).
"""

import os
import json
import pytest

os.environ.setdefault("USE_MOCK_COMPILER", "true")
os.environ.setdefault("USE_MOCK_AI", "true")

from app.compiler.validation_confidence import (
    compute_confidence, LOW, MEDIUM, HIGH, PROFILED
)
from app.workflow_engine.context import WorkflowContext


# ── 1. compute_confidence ladder ────────────────────────────────────

class TestComputeConfidence:
    def test_hipify_failed_compile_failed(self):
        level, reason = compute_confidence(False, False)
        assert level == LOW
        assert "hipify" in reason

    def test_hipify_ok_compile_failed(self):
        level, reason = compute_confidence(True, False)
        assert level == LOW
        assert "compilation failed" in reason

    def test_hipify_compile_ok_no_runtime(self):
        level, reason = compute_confidence(True, True)
        assert level == MEDIUM
        assert "compilation" in reason
        assert "runtime" in reason

    def test_compile_ok_runtime_ok(self):
        level, reason = compute_confidence(True, True, runtime_ok=True)
        assert level == HIGH
        assert "runtime" in reason

    def test_runtime_ok_profiled(self):
        level, reason = compute_confidence(True, True, runtime_ok=True, profiled=True)
        assert level == PROFILED
        assert "profiling" in reason

    def test_profiled_without_runtime_ok_is_low_when_compile_fails(self):
        level, reason = compute_confidence(False, False, profiled=True)
        assert level == LOW

    def test_reason_strings_present_for_all_levels(self):
        for hipify in (False, True):
            for compile_ok in (False, True):
                _, reason = compute_confidence(hipify, compile_ok)
                assert reason


# ── 2. Runtime validation defaults ──────────────────────────────────

class TestRuntimeValidationDefaults:
    def test_runtime_validation_disabled_by_default(self):
        ctx = WorkflowContext("test-rt-defaults", "/tmp/fake")
        assert ctx.runtime_validation_enabled is False
        assert ctx.runtime_validation_status == "NOT_RUN"
        assert ctx.profiling_status == "NOT_CONFIGURED"

    def test_default_confidence_is_low(self):
        ctx = WorkflowContext("test-low-default", "/tmp/fake")
        assert ctx.validation_confidence == "LOW"
        assert ctx.validation_confidence_reason == "conversion happened but real compile failed or did not run"


# ── 3. last_compile_command safety ──────────────────────────────────

class TestLastCompileCommandSafety:
    def test_missing_command_defaults_to_empty_string(self):
        ctx = WorkflowContext("test-cmd-safe", "/tmp/fake")
        cmd = ctx.last_compile_command
        assert cmd == ""

    def test_command_stored_when_present(self):
        ctx = WorkflowContext("test-cmd-stored", "/tmp/fake")
        ctx.last_compile_command = "hipcc foo.hip -o bar"
        assert ctx.last_compile_command == "hipcc foo.hip -o bar"

    @pytest.mark.asyncio
    async def test_json_report_does_not_crash_when_command_missing(self, tmp_path, monkeypatch):
        from app.services.report_service import generate_json_report
        from app.workspace.manager import get_workspace_path

        mid = "test-cmd-missing"
        ws = tmp_path / mid
        for sub in ("input", "generated", "logs", "artifacts", "reports", "exports"):
            (ws / sub).mkdir(parents=True)
        (ws / "input" / "kernel.cu").write_text("#include <cuda_runtime.h>\nint main(){return 0;}\n")

        monkeypatch.setattr(
            "app.services.report_service.get_workspace_path",
            lambda _id: ws,
        )

        ctx = WorkflowContext(mid, str(ws))
        await generate_json_report(mid, ctx)

        report_file = ws / "reports" / "migration_report.json"
        assert report_file.exists()
        data = json.loads(report_file.read_text(encoding="utf-8"))
        cm = data["migration_metrics"]["compile_command"]
        assert cm == ""


# ── 4. Mock compiler confidence reason ─────────────────────────────

def test_mock_compiler_confidence_reasons():
    level, reason = compute_confidence(True, True, compiler_mocked=True)
    assert level == LOW
    assert "mocked" in reason

    level, reason = compute_confidence(True, False, compiler_mocked=True)
    assert level == LOW
    assert "mocked" in reason
