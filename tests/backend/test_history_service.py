import os
import json
import pytest
import time
from pathlib import Path
from unittest.mock import MagicMock

from app.workflow_engine.context import WorkflowContext
from app.services.report_service import (
    generate_markdown_report,
    generate_json_report,
    write_history_summary,
)
from app.workspace.manager import get_workspace_path, create_workspace, teardown_workspace
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture()
def workspace():
    migration_id = "test-20260707_123456_historytest"
    create_workspace(migration_id)
    ws_path = get_workspace_path(migration_id)

    # Clean history folder for this test case
    root_path_str = os.getenv("WORKSPACE_PATH") or "workspace"
    history_dir = Path(root_path_str) / "history"
    if history_dir.exists():
        for f in history_dir.glob("*.json"):
            try:
                f.unlink()
            except Exception:
                pass

    yield migration_id, ws_path

    teardown_workspace(migration_id)
    # clean up history files
    history_file = history_dir / f"{migration_id}.json"
    if history_file.exists():
        history_file.unlink()


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
    c.compile_status = "PASSED"
    c.validation_confidence = "HIGH"
    c.runtime_validation_status = "PASSED"
    c.hipify_output_path = str(ws_path / "generated" / "kernel.hip")
    c.sca_result = {"issues": [], "score": 1.0}
    c.project_scan = {"input_kind": "single_file", "category": "standard_cuda"}
    return c


@pytest.mark.anyio
async def test_history_written_after_report(workspace, ctx):
    migration_id, ws_path = workspace
    
    # Write some dummy files in input/ and generated/ to allow history to count them
    input_file = ws_path / "input" / "kernel.cu"
    input_file.write_text("void foo() {}", encoding="utf-8")
    
    gen_file = ws_path / "generated" / "kernel.hip"
    gen_file.write_text("void foo() {}", encoding="utf-8")

    # Generate reports
    await generate_markdown_report(migration_id, ctx)
    await generate_json_report(migration_id, ctx)
    await write_history_summary(migration_id, ctx)

    root_path_str = os.getenv("WORKSPACE_PATH") or "workspace"
    history_file = Path(root_path_str) / "history" / f"{migration_id}.json"
    assert history_file.exists()

    with open(history_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["job_id"] == migration_id
    assert data["input_name"] == "kernel.cu"
    assert data["input_kind"] == "single_file"
    assert data["target_architecture"] == "gfx90a"
    assert data["final_state"] == "COMPLETED"
    assert data["compile_status"] == "PASSED"
    assert data["validation_confidence"] == "HIGH"
    assert data["runtime_validation_status"] == "PASSED"
    assert data["report_missing"] is False
    assert data["artifact_missing"] is True  # We did not build the zip archive in this test
    assert data["file_count"] == 1
    assert data["generated_file_count"] == 1


@pytest.mark.anyio
async def test_history_written_on_failure(workspace, ctx):
    migration_id, ws_path = workspace
    ctx.compilation_success = False
    ctx.compile_status = "FAILED"
    ctx.validation_confidence = "LOW"
    ctx.current_state = "FAILED"
    ctx.error_category = "COMPILATION_ERROR"
    ctx.main_error = "hipcc failed with exit code 1"

    await write_history_summary(migration_id, ctx, failed=True)

    root_path_str = os.getenv("WORKSPACE_PATH") or "workspace"
    history_file = Path(root_path_str) / "history" / f"{migration_id}.json"
    assert history_file.exists()

    with open(history_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["job_id"] == migration_id
    assert data["final_state"] == "FAILED"
    assert data["compile_status"] == "FAILED"
    assert data["error_category"] == "COMPILATION_ERROR"
    assert data["main_error"] == "hipcc failed with exit code 1"
    assert data["report_missing"] is True
    assert data["artifact_missing"] is True


@pytest.mark.anyio
async def test_history_list_newest_first():
    # Setup multiple history summaries with artificial delay to ensure mtime diff
    root_path_str = os.getenv("WORKSPACE_PATH") or "workspace"
    history_dir = Path(root_path_str) / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    # Clear history directory first
    for f in history_dir.glob("*.json"):
        f.unlink()

    job1 = "test-history-1"
    job2 = "test-history-2"

    with open(history_dir / f"{job1}.json", "w") as f:
        json.dump({"job_id": job1, "finished_at": "2026-07-07T12:00:00Z"}, f)
    # Sleep to differentiate st_mtime
    time.sleep(0.1)
    with open(history_dir / f"{job2}.json", "w") as f:
        json.dump({"job_id": job2, "finished_at": "2026-07-07T12:05:00Z"}, f)

    response = client.get("/api/v1/migrations/history")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    # Newest mtime (job2) should be first
    assert data[0]["job_id"] == job2
    assert data[1]["job_id"] == job1

    # Cleanup
    (history_dir / f"{job1}.json").unlink()
    (history_dir / f"{job2}.json").unlink()


@pytest.mark.anyio
async def test_missing_report_handled(workspace, ctx):
    migration_id, ws_path = workspace
    await write_history_summary(migration_id, ctx)

    response = client.get(f"/api/v1/migrations/history/{migration_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == migration_id
    # The actual physical files do not exist (reports/migration_report.md)
    assert data["report_exists"] is False
    assert data["artifact_exists"] is False


@pytest.mark.anyio
async def test_generated_only_not_compile_passed(workspace, ctx):
    migration_id, ws_path = workspace
    ctx.compilation_success = False
    ctx.compile_status = "NOT_RUN"
    ctx.validation_confidence = "LOW"
    
    await write_history_summary(migration_id, ctx)

    root_path_str = os.getenv("WORKSPACE_PATH") or "workspace"
    history_file = Path(root_path_str) / "history" / f"{migration_id}.json"
    with open(history_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["compile_status"] == "NOT_RUN"
    assert data["final_state"] == "COMPLETED"


@pytest.mark.anyio
async def test_compile_only_runtime_not_run(workspace, ctx):
    migration_id, ws_path = workspace
    ctx.compilation_success = True
    ctx.compile_status = "PASSED"
    ctx.runtime_validation_status = "NOT_RUN"

    await write_history_summary(migration_id, ctx)

    root_path_str = os.getenv("WORKSPACE_PATH") or "workspace"
    history_file = Path(root_path_str) / "history" / f"{migration_id}.json"
    with open(history_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["runtime_validation_status"] == "NOT_RUN"


def test_cli_history_list_renders(capsys):
    from cli.hipforge import run_history_command
    from unittest.mock import patch

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "job_id": "migration_123",
            "finished_at": "2026-07-07T12:00:00Z",
            "target_architecture": "gfx90a",
            "final_state": "COMPLETED",
            "compile_status": "PASSED",
            "validation_confidence": "HIGH",
            "main_error": None,
            "report_missing": False
        }
    ]

    with patch("requests.get", return_value=mock_resp) as mock_get:
        ok = run_history_command("http://localhost:8000", limit=20)
        assert ok
        mock_get.assert_called_once_with("http://localhost:8000/api/v1/migrations/history?limit=20", timeout=10)
        
        captured = capsys.readouterr()
        assert "migration_123" in captured.out
        assert "gfx90a" in captured.out
        assert "PASSED" in captured.out
        assert "HIGH" in captured.out
