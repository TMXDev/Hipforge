import os
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from app.compiler.validator import harden_hip_content
from app.workflow_engine.context import WorkflowContext
from app.services.report_service import generate_json_report, generate_markdown_report


def test_harden_hip_content_basic():
    src = """
    extern "C" void run_gelu(const float* input, float* output, int N) {
        geluKernel<<<1, 1>>>(input, output, N);
    }
    """
    new_code, stats = harden_hip_content(src, validation_enabled=False)
    
    assert "#include <hip/hip_runtime.h>" in new_code
    assert "#include <cstdio>" in new_code
    assert "if (N <= 0 || input == nullptr || output == nullptr)" in new_code
    assert "hipGetLastError()" in new_code
    assert "hipDeviceSynchronize()" not in new_code
    assert "// input and output are expected to be HIP device pointers." in new_code
    
    assert stats["launcher_expects_device_pointers"] == "Yes"
    assert stats["kernel_launch_error_checks"] == "inserted"
    assert stats["synchronization_status"] == "skipped"


def test_harden_hip_content_with_validation():
    src = """
    extern "C" void run_gelu(const float* input, float* output, int N) {
        geluKernel<<<1, 1>>>(input, output, N);
    }
    """
    new_code, stats = harden_hip_content(src, validation_enabled=True)
    
    assert "#include <hip/hip_runtime.h>" in new_code
    assert "#include <cstdio>" in new_code
    assert "if (N <= 0 || input == nullptr || output == nullptr)" in new_code
    assert "hipGetLastError()" in new_code
    assert "hipDeviceSynchronize()" in new_code
    
    assert stats["launcher_expects_device_pointers"] == "Yes"
    assert stats["kernel_launch_error_checks"] == "inserted"
    assert stats["synchronization_status"] == "inserted"


def test_harden_hip_content_existing_guards_no_duplication():
    src = """#include <hip/hip_runtime.h>
    #include <cstdio>
    extern "C" void run_gelu(const float* input, float* output, int N) {
        if (N <= 0 || input == nullptr) {
            return;
        }
        geluKernel<<<1, 1>>>(input, output, N);
        hipError_t err = hipGetLastError();
        hipDeviceSynchronize();
    }
    """
    new_code, stats = harden_hip_content(src, validation_enabled=True)
    
    # Verify no double injection
    assert new_code.count("hipGetLastError") == 1
    assert new_code.count("hipDeviceSynchronize") == 1
    assert new_code.count("if (") == 1
    
    assert stats["launcher_expects_device_pointers"] == "Yes"
    assert stats["kernel_launch_error_checks"] == "found"
    assert stats["synchronization_status"] == "found"


def test_harden_hip_content_host_allocation_skips_comment():
    src = """
    extern "C" void run_gelu(const float* input, float* output, int N) {
        float* d_in;
        hipMalloc(&d_in, N * sizeof(float));
        geluKernel<<<1, 1>>>(d_in, output, N);
    }
    """
    new_code, stats = harden_hip_content(src, validation_enabled=False)
    
    # Should not include device pointer comments because hipMalloc is present
    assert "expected to be HIP device pointers" not in new_code
    assert "if (N <= 0 || input == nullptr || output == nullptr)" in new_code


@pytest.mark.asyncio
async def test_integration_reports_fields(tmp_path, monkeypatch):
    mid = "test_launcher_report"
    ws = tmp_path / "ws"
    for sub in ("input", "generated", "logs", "artifacts", "reports", "exports"):
        (ws / sub).mkdir(parents=True)
        
    (ws / "input" / "kernel.cu").write_text("#include <cuda_runtime.h>\n")
    
    monkeypatch.setattr(
        "app.services.report_service.get_workspace_path",
        lambda _id: ws,
    )
    
    ctx = WorkflowContext(mid, str(ws))
    ctx.compilation_success = True
    ctx.validation_confidence = "MEDIUM"
    ctx.validation_confidence_reason = "hipify and compilation succeeded; runtime execution was not performed"
    ctx.launcher_expects_device_pointers = "Yes"
    ctx.kernel_launch_error_checks = "inserted"
    ctx.synchronization_status = "skipped"
    ctx.runtime_validation_status = "NOT_CONFIGURED"
    ctx.runtime_validation_enabled = False
    
    # Generate JSON report
    await generate_json_report(mid, ctx)
    
    json_path = ws / "reports" / "migration_report.json"
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    
    vc = data["validation_confidence"]
    assert vc["launcher_expects_device_pointers"] == "Yes"
    assert vc["runtime_execution_performed"] == "No"
    assert vc["validation_confidence_type"] == "compile-only"
    assert vc["kernel_launch_error_checks"] == "inserted"
    assert vc["synchronization_status"] == "skipped"
    
    # Generate Markdown report
    await generate_markdown_report(mid, ctx)
    
    md_path = ws / "reports" / "migration_report.md"
    assert md_path.exists()
    md_content = md_path.read_text(encoding="utf-8")
    
    assert "- **Launcher Expects Device Pointers**: `Yes`" in md_content
    assert "- **Runtime Execution Performed**: `No`" in md_content
    assert "- **Validation Confidence Type**: `compile-only`" in md_content
    assert "- **Kernel Launch Error Checks**: `inserted`" in md_content
    assert "- **Synchronization Status**: `skipped`" in md_content
