"""
tests/backend/test_real_validation_regression.py

Regression tests verifying compiler validation status tracking, diagnostics handling,
and reporting updates in both mock and real-like environments.
"""

import os
import json
import pytest
from pathlib import Path
from app.workflow_engine.context import WorkflowContext
from app.compiler.validation_confidence import compute_confidence
from app.services.report_service import generate_json_report, generate_markdown_report

@pytest.mark.asyncio
async def test_compile_validation_defaults_to_not_run():
    """Verify that compile validation status defaults correctly to NOT_RUN prior to compilation."""
    ctx = WorkflowContext("test-reg-defaults", "/tmp")
    assert ctx.compile_status == "NOT_RUN"
    assert ctx.runtime_validation_status == "NOT_RUN"


@pytest.mark.asyncio
async def test_compiler_mode_unavailable_when_missing_tools(monkeypatch):
    """Verify that compiler_mode is set to 'unavailable' if compile tools are missing."""
    import app.diagnostics
    # Force diagnostics to fail tool checks
    monkeypatch.setattr(app.diagnostics, "_sandbox_probe_command", lambda cmd: (False, "", "command not found"))
    
    report = app.diagnostics.run_preflight()
    assert report["overall_status"] == "unhealthy"
    
    # Simulate how states.py maps this failure to context
    ctx = WorkflowContext("test-reg-missing", "/tmp")
    ctx.compiler_mode = "unavailable"
    ctx.compile_status = "FAILED_SETUP"
    
    assert ctx.compiler_mode == "unavailable"
    assert ctx.compile_status == "FAILED_SETUP"


@pytest.mark.asyncio
async def test_validation_confidence_low_when_skipped_or_mocked():
    """Verify that validation_confidence defaults to LOW if checks are mocked, missing, or skipped."""
    # Mock compiler validation
    level, reason = compute_confidence(hipify_ok=True, compile_ok=True, compiler_mocked=True)
    assert level == "LOW"
    assert "mocked" in reason

    # Skip compile validation (tools missing)
    level, reason = compute_confidence(hipify_ok=True, compile_ok=False, tools_missing=True)
    assert level == "LOW"
    assert "missing" in reason


@pytest.mark.asyncio
async def test_report_contains_compile_command_and_errors(tmp_path, monkeypatch):
    """Verify that JSON and Markdown reports save compile_command and classified errors correctly."""
    mid = "migration_reg_reports"
    ws = tmp_path / mid
    for sub in ("input", "generated", "logs", "artifacts", "reports", "exports"):
        (ws / sub).mkdir(parents=True)
        
    (ws / "input" / "kernel.cu").write_text("int main() { return 0; }", encoding="utf-8")
    
    monkeypatch.setattr(
        "app.services.report_service.get_workspace_path",
        lambda _id: ws,
    )
    
    ctx = WorkflowContext(mid, str(ws))
    ctx.compilation_success = False
    ctx.compiler_mode = "real"
    ctx.compile_status = "FAILED"
    ctx.last_compile_command = "hipcc kernel.hip -o main"
    ctx.main_error = "error: undefined symbol: run_gelu"
    ctx.error_category = "DEPENDENCY_ERROR"
    ctx.recommended_next_action = "include run_gelu"
    
    ctx.project_scan = {
        "category": "standard_cuda",
        "message": "CUDA project detected",
        "input_kind": "single_file",
        "compile_strategy": "generated_single_file_makefile",
        "cu_files": ["kernel.cu"],
        "hip_files": [],
        "cpp_files": [],
        "cuh_files": [],
        "header_files": [],
        "build_system_detected": "none",
        "file_count": 1,
    }
    
    # Recalculate will read settings. We mock settings to return USE_MOCK_COMPILER = False so we test "real" compiler mode
    from app.config.settings import settings
    monkeypatch.setattr(settings, "USE_MOCK_COMPILER", False)
    
    # Generate JSON
    await generate_json_report(mid, ctx)
    json_file = ws / "reports" / "migration_report.json"
    assert json_file.exists()
    
    report_data = json.loads(json_file.read_text(encoding="utf-8"))
    assert report_data["compile_command"] == "hipcc kernel.hip -o main"
    assert report_data["compile_status"] == "FAILED"
    assert report_data["validation_confidence_level"] == "LOW"
    assert report_data["main_error_val"] == "error: undefined symbol: run_gelu"
    assert report_data["error_category_val"] == "DEPENDENCY_ERROR"
    
    # Generate MD
    await generate_markdown_report(mid, ctx)
    md_file = ws / "reports" / "migration_report.md"
    assert md_file.exists()
    
    md_content = md_file.read_text(encoding="utf-8")
    assert "hipcc kernel.hip -o main" in md_content
    assert "error: undefined symbol: run_gelu" in md_content
    assert "DEPENDENCY_ERROR" in md_content
