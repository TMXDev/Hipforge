import os
import json
import pytest
import zipfile
from pathlib import Path

from app.workflow_engine.context import WorkflowContext
from app.services.report_service import (
    generate_markdown_report,
    generate_json_report,
    generate_git_patch,
    build_zip
)
from app.workspace.manager import get_workspace_path, create_workspace, teardown_workspace


@pytest.fixture()
def workspace():
    migration_id = "migration_20260701_999999_reporttest"
    create_workspace(migration_id)
    ws_path = get_workspace_path(migration_id)
    
    # 1. Create a mock original CUDA file in input/
    input_file = ws_path / "input" / "simple_kernel.cu"
    input_file.write_text(
        "__global__ void simple_add(int *a, int *b, int *c) {\n"
        "    int idx = threadIdx.x;\n"
        "    c[idx] = a[idx] + b[idx];\n"
        "}\n",
        encoding="utf-8"
    )
    
    # 2. Create a mock generated/translated HIP file in generated/
    gen_file = ws_path / "generated" / "simple_kernel.hip"
    gen_file.write_text(
        "#include <hip/hip_runtime.h>\n"
        "__global__ void simple_add(int *a, int *b, int *c) {\n"
        "    int idx = hipThreadIdx_x;\n"
        "    c[idx] = a[idx] + b[idx];\n"
        "}\n",
        encoding="utf-8"
    )
    
    # 3. Create a mock compiler log file in logs/
    log_file = ws_path / "logs" / "compile_attempt_001.log"
    log_file.write_text(
        "hipcc simple_kernel.hip -o simple_kernel\n"
        "Compilation completed successfully.\n",
        encoding="utf-8"
    )
    
    yield migration_id, ws_path
    
    teardown_workspace(migration_id)


@pytest.fixture()
def ctx(workspace):
    migration_id, ws_path = workspace
    c = WorkflowContext(
        migration_id=migration_id,
        workspace_path=str(ws_path)
    )
    c.compilation_success = True
    c.target_gpu_architecture = "gfx90a"
    c.retry_budget = 3
    c.current_attempt = 1
    c.hipify_output_path = str(ws_path / "generated" / "simple_kernel.hip")
    c.sca_result = {
        "issues": [
            {"description": "Texture Reference API is deprecated in HIP", "line": 12}
        ],
        "score": 0.95
    }
    c.migration_journal = [
        {
            "attempt": 1,
            "analysis_summary": "Initial translation failed compile due to threadIdx referencing",
            "root_cause": "threadIdx reference needs to be mapped to hipThreadIdx_x",
            "repair_plan": ["Run patch agent on simple_kernel.hip"]
        }
    ]
    return c


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_generate_markdown_report(workspace, ctx):
    migration_id, ws_path = workspace
    await generate_markdown_report(migration_id, ctx)
    
    report_file = ws_path / "reports" / "migration_report.md"
    assert report_file.exists()
    
    content = report_file.read_text(encoding="utf-8")
    assert f"Migration ID**: `{migration_id}`" in content
    assert "Status**: `PASSED`" in content
    assert "Target GPU Architecture**: `gfx90a`" in content
    assert "Original Files Uploaded" in content
    assert "simple_kernel.cu" in content
    assert "Texture Reference API is deprecated" in content
    assert "compile_attempt_001.log" in content
    assert "Initial translation failed compile" in content


@pytest.mark.anyio
async def test_generate_json_report(workspace, ctx):
    migration_id, ws_path = workspace
    await generate_json_report(migration_id, ctx)
    
    report_file = ws_path / "reports" / "migration_report.json"
    assert report_file.exists()
    
    with open(report_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    summary = data["migration_summary"]
    assert summary["migration_id"] == migration_id
    assert summary["status"] == "PASSED"
    assert summary["target_gpu_architecture"] == "gfx90a"
    assert summary["retry_budget"] == 3
    assert summary["actual_retries"] == 1
    
    project_details = data["input_project_details"]
    assert "simple_kernel.cu" in project_details["original_files"]
    assert len(project_details["file_hashes"]["simple_kernel.cu"]) == 64
    
    translation = data["translation_summary"]
    assert translation["hipify_clang_status"] == "SUCCESS"
    assert len(translation["sca_findings"]["issues"]) == 1
    
    assert data["compilation_history"][0]["log_file"] == "compile_attempt_001.log"
    assert len(data["ai_agent_activity"]["analysis_summaries"]) == 1
    assert data["generated_artifacts"] is not None


@pytest.mark.anyio
async def test_generate_git_patch(workspace):
    migration_id, ws_path = workspace
    await generate_git_patch(migration_id)
    
    patch_file = ws_path / "reports" / "git_patch.diff"
    assert patch_file.exists()
    
    content = patch_file.read_text(encoding="utf-8")
    assert "--- a/input/simple_kernel.cu" in content
    assert "+++ b/generated/simple_kernel.hip" in content
    assert "-    int idx = threadIdx.x;" in content
    assert "+    int idx = hipThreadIdx_x;" in content


@pytest.mark.anyio
async def test_build_zip(workspace, ctx):
    migration_id, ws_path = workspace
    
    # Generate reports first so they are present in reports/ folder
    await generate_markdown_report(migration_id, ctx)
    await generate_json_report(migration_id, ctx)
    await generate_git_patch(migration_id)
    
    # Build Zip package
    await build_zip(migration_id)
    
    zip_file = ws_path / "exports" / "HIPForge_Migration.zip"
    assert zip_file.exists()
    
    # Verify contents of zip file
    with zipfile.ZipFile(zip_file, "r") as z:
        names = z.namelist()
        
        # Should package subdirs and root README.txt
        assert "README.txt" in names
        assert "generated/simple_kernel.hip" in names
        assert "logs/compile_attempt_001.log" in names
        assert "reports/migration_report.md" in names
        assert "reports/migration_report.json" in names
        assert "reports/git_patch.diff" in names
