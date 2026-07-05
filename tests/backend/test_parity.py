import os
import json
import base64
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from pathlib import Path

from app.main import app as fastapi_app
import app.redis.client
from app.redis.keys import status_key, attempt_key, retry_budget_key, metadata_key
from app.redis.keys import pending_queue_key
import app.redis.client

async def dequeue_job(timeout: int = 0):
    key = pending_queue_key()
    result = await app.redis.client.redis_client.brpop(key, timeout=timeout)
    if not result:
        return None
    _, value = result
    payload = json.loads(value)
    return payload.get("migration_id"), payload
from app.workflow_engine.context import WorkflowContext
from app.workflow_engine.state_machine import WorkflowEngine
from app.workflow_engine.states import handle_compiling
from app.services.report_service import generate_json_report, generate_markdown_report, get_skipped_ai_repair_reason

client = TestClient(fastapi_app)

@pytest.fixture(autouse=True)
def force_mock_compiler():
    # Force mock settings to keep tests clean and fast
    os.environ["USE_MOCK_COMPILER"] = "true"
    os.environ["USE_MOCK_AI"] = "true"
    yield

@pytest.mark.anyio
async def test_cli_web_parity_initialization(redis_test_client):
    # Web paste migration payload
    paste_payload = {
        "code": "__global__ void kernel() {}",
        "filename": "kernel.cu",
        "target_gpu_architecture": "gfx942",
        "retry_budget": 4,
        "migration_mode": "standard"
    }
    
    # Web upload/CLI payload
    code_bytes = b"__global__ void kernel() {}"
    encoded_file = base64.b64encode(code_bytes).decode("utf-8")
    upload_payload = {
        "file": encoded_file,
        "filename": "kernel.cu",
        "target_gpu_architecture": "gfx942",
        "retry_budget": 4,
        "migration_mode": "standard"
    }

    # 1. Post to paste endpoint
    response_paste = client.post("/api/v1/migrate/paste", json=paste_payload)
    assert response_paste.status_code == 202
    paste_data = response_paste.json()
    paste_id = paste_data["migration_id"]

    # Dequeue the paste job to inspect
    paste_job = await dequeue_job()
    assert paste_job is not None
    assert paste_job[0] == paste_id
    paste_payload_job = paste_job[1]

    # Verify Redis keys for paste job
    paste_status = await app.redis.client.redis_client.get(status_key(paste_id))
    paste_attempts = await app.redis.client.redis_client.get(attempt_key(paste_id))
    paste_budget = await app.redis.client.redis_client.get(retry_budget_key(paste_id))
    paste_metadata = await app.redis.client.redis_client.hgetall(metadata_key(paste_id))

    # 2. Post to upload endpoint
    response_upload = client.post("/api/v1/migrate/upload", json=upload_payload)
    assert response_upload.status_code == 202
    upload_data = response_upload.json()
    upload_id = upload_data["migration_id"]

    # Dequeue the upload job to inspect
    upload_job = await dequeue_job()
    assert upload_job is not None
    assert upload_job[0] == upload_id
    upload_payload_job = upload_job[1]

    # Verify Redis keys for upload job
    upload_status = await app.redis.client.redis_client.get(status_key(upload_id))
    upload_attempts = await app.redis.client.redis_client.get(attempt_key(upload_id))
    upload_budget = await app.redis.client.redis_client.get(retry_budget_key(upload_id))
    upload_metadata = await app.redis.client.redis_client.hgetall(metadata_key(upload_id))

    # Validate absolute parity in Redis states
    assert paste_status == upload_status == "QUEUED"
    assert paste_attempts == upload_attempts == "0"
    assert paste_budget == upload_budget == "4"
    
    # Metadata fields must match (except dynamic timestamps & workspace paths)
    for key in ["project_name", "compiler", "target_architecture"]:
        assert paste_metadata[key] == upload_metadata[key]
    assert paste_metadata["target_architecture"] == "gfx942"

    # Queued job payload details must match
    assert paste_payload_job["retry_budget"] == upload_payload_job["retry_budget"] == 4


@pytest.mark.anyio
async def test_target_architecture_reaches_compiler(tmp_path, redis_test_client):
    # Setup test workspace
    ws = tmp_path / "test_arch_propagation"
    for subdir in ("input", "generated", "logs", "artifacts", "reports", "exports"):
        (ws / subdir).mkdir(parents=True)
    
    # Write a dummy hip source file
    hip_source = ws / "generated" / "kernel.hip"
    hip_source.write_text("__global__ void kernel() {}", encoding="utf-8")

    ctx = WorkflowContext(
        migration_id="migration_20260701_000000_arch_test",
        workspace_path=str(ws),
        retry_budget=3
    )
    ctx.hipify_output_path = str(hip_source)
    ctx.target_gpu_architecture = "gfx90a"

    # Disable mock compiler override so sandbox run_sandboxed_compiler is called
    with patch("app.compiler.hipcc_runner.os.getenv", return_value="false"):
        with patch("app.compiler.sandbox.run_sandboxed_compiler") as mock_sandbox:
            mock_sandbox.return_value = {
                "returncode": 0,
                "stdout": "success",
                "stderr": ""
            }
            
            await handle_compiling(ctx)
            
            # Assert target architecture was passed to the compile command args
            called_cmd = mock_sandbox.call_args[0][1]
            assert "--offload-arch=gfx90a" in called_cmd


@pytest.mark.anyio
async def test_repair_budget_preserved_through_engine(redis_test_client):
    # Setup a state machine with a mock context
    ctx = WorkflowContext(
        migration_id="int-test-budget-preservation",
        workspace_path="workspace/test",
        retry_budget=7
    )
    ctx.target_gpu_architecture = "gfx1030"
    
    engine = WorkflowEngine(ctx)
    await engine.run()
    
    # Verify budget and selected arch are unchanged on context
    assert ctx.retry_budget == 7
    assert ctx.target_gpu_architecture == "gfx1030"


@pytest.mark.anyio
async def test_event_stream_stage_order_and_trace(redis_test_client):
    # Success path
    ctx = WorkflowContext(
        migration_id="int-test-event-stream-success",
        workspace_path="workspace/test",
        retry_budget=2
    )
    ctx.compilation_success = True
    engine = WorkflowEngine(ctx)
    await engine.run()

    trace = ctx.workflow_trace
    assert len(trace) > 0
    stages_entered = [t["state"] for t in trace if t.get("event") == "state_start"]
    expected_order = [
        "QUEUED", "PREPARING", "PREFLIGHT", "HIPIFY", "SCA", 
        "COMPILING", "GENERATING_REPORT", "COMPLETED"
    ]
    assert stages_entered == expected_order

    # Failure / retry path
    ctx_fail = WorkflowContext(
        migration_id="int-test-event-stream-fail",
        workspace_path="workspace/test",
        retry_budget=1
    )
    ctx_fail.compilation_success = False
    engine_fail = WorkflowEngine(ctx_fail)
    await engine_fail.run()

    trace_fail = ctx_fail.workflow_trace
    stages_entered_fail = [t["state"] for t in trace_fail if t.get("event") == "state_start"]
    expected_order_fail = [
        "QUEUED", "PREPARING", "PREFLIGHT", "HIPIFY", "SCA", 
        "COMPILING", "ANALYZING", "PATCHING", "COMPILING", "GENERATING_REPORT", "FAILED"
    ]
    assert stages_entered_fail == expected_order_fail


@pytest.mark.anyio
async def test_final_report_contains_all_fields(redis_test_client):
    from app.workspace.manager import create_workspace, teardown_workspace
    
    migration_id = "test-20260701_000000_report"
    ws_str = create_workspace(migration_id)
    ws = Path(ws_str)

    try:
        # Populate dummy compile log file
        log_file = ws / "logs" / "compile_attempt_001.log"
        log_file.write_text("dummy error message on line 42", encoding="utf-8")

        ctx = WorkflowContext(
            migration_id=migration_id,
            workspace_path=str(ws),
            retry_budget=5
        )
        ctx.target_gpu_architecture = "gfx942"
        ctx.current_attempt = 1
        ctx.compilation_success = False
        ctx.failed_stage = "COMPILING"
        ctx.error_category = "COMPILER_ERROR"
        ctx.main_error = "dummy error message on line 42"
        ctx.workflow_trace = [
            {"event": "state_start", "state": "QUEUED", "timestamp": "2026-07-05T00:00:00Z"},
            {"event": "state_success", "state": "QUEUED", "timestamp": "2026-07-05T00:00:01Z"}
        ]

        # Generate both Markdown and JSON reports
        await generate_markdown_report(migration_id, ctx)
        await generate_json_report(migration_id, ctx)

        # 1. Assert Markdown report exists and contains fields
        md_file = ws / "reports" / "migration_report.md"
        assert md_file.exists()
        md_content = md_file.read_text(encoding="utf-8")
        
        assert "**Target Architecture**: `gfx942`" in md_content
        assert "**Repair Budget**: `5`" in md_content
        assert "**Compile Attempts**: `1`" in md_content
        assert "**Failed Stage**: `COMPILING`" in md_content
        assert "**Error Category**: `COMPILER_ERROR`" in md_content
        assert "**Main Error**: `dummy error message on line 42`" in md_content
        assert "**Skipped AI Repair Reason**: `Skipped: no compile failure encountered.`" in md_content

        # 2. Assert JSON report exists and contains fields
        json_file = ws / "reports" / "migration_report.json"
        assert json_file.exists()
        json_data = json.loads(json_file.read_text(encoding="utf-8"))

        # Assert under final_summary
        final_sum = json_data["final_summary"]
        assert final_sum["target_architecture"] == "gfx942"
        assert final_sum["repair_budget"] == 5
        assert final_sum["compile_attempts"] == 1
        assert final_sum["failed_stage"] == "COMPILING"
        assert final_sum["failure_category"] == "COMPILER_ERROR"
        assert final_sum["main_error"] == "dummy error message on line 42"
        assert final_sum["skipped_ai_repair_reason"] == "Skipped: no compile failure encountered."

        # Assert under migration_metrics
        metrics = json_data["migration_metrics"]
        assert metrics["target_architecture"] == "gfx942"
        assert metrics["repair_budget"] == 5
        assert metrics["compile_attempts"] == 1
        assert metrics["failed_stage"] == "COMPILING"
        assert metrics["error_category"] == "COMPILER_ERROR"
        assert metrics["main_error"] == "dummy error message on line 42"
        assert metrics["skipped_ai_repair_reason"] == "Skipped: no compile failure encountered."
        assert len(metrics["workflow_trace"]) == 2
        assert metrics["workflow_trace"][0]["state"] == "QUEUED"
        
    finally:
        teardown_workspace(migration_id)
