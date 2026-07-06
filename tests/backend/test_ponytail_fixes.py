import pytest
from unittest.mock import patch, MagicMock
from app.compiler.error_parser import extract_main_error
from app.compiler.makefile_generator import generate_makefile_content
from app.compiler.hipcc_runner import run_hipcc
from app.workflow_engine.context import WorkflowContext
from app.workflow_engine.states import handle_analyzing

def test_selecting_gfx942_propagates_to_hipcc(monkeypatch):
    """Verify that selecting gfx942 results in hipcc --offload-arch=gfx942"""
    monkeypatch.delenv("USE_MOCK_COMPILER", raising=False)
    with patch("app.compiler.sandbox.run_sandboxed_compiler") as mock_sandbox:
        mock_sandbox.return_value = {
            "returncode": 0,
            "stdout": "success",
            "stderr": ""
        }
        
        # Test direct run_hipcc call
        run_hipcc("sample.hip", "output.bin", target_arch="gfx942")
        
        mock_sandbox.assert_called_once()
        args, _ = mock_sandbox.call_args
        cmd = args[1]
        assert "--offload-arch=gfx942" in cmd

def test_generating_makefile_respects_target_arch():
    """Verify that Makefile generation uses the user-selected architecture"""
    content = generate_makefile_content(
        {"compile_strategy": "generated_makefile", "cu_files": ["kernel.cu"]},
        target_arch="gfx942"
    )
    assert "ARCH ?= gfx942" in content
    assert "$(HIPCC) --offload-arch=$(ARCH)" in content

def test_undefined_symbol_prefers_fatal_error_over_warning():
    """Verify undefined symbol errors are reported as Main Error instead of warnings"""
    stderr = (
        "main.hip:29:5: warning: ignoring return value...\n"
        "ld.lld: error: undefined symbol: run_gelu\n"
        "make: *** [Makefile:20: output] Error 1\n"
    )
    main_err = extract_main_error(stderr)
    assert main_err == "ld.lld: error: undefined symbol: run_gelu"

def test_make_failure_priority():
    """Verify make failures are preferred over warnings if no fatal error exists"""
    stderr = (
        "main.hip:29:5: warning: ignoring return value...\n"
        "make: *** [Makefile:20: output] Error 1\n"
    )
    main_err = extract_main_error(stderr)
    assert main_err == "make: *** [Makefile:20: output] Error 1"

@pytest.mark.asyncio
async def test_dependency_errors_produce_clear_explanation():
    """Verify that dependency errors produce a clear user-facing explanation and skip AI repair"""
    ctx = WorkflowContext("test-dep-id", "/tmp/non-existent-workspace")
    ctx.last_compile_stderr = "ld.lld: error: undefined symbol: run_gelu"
    ctx.current_state = "ANALYZING"

    with pytest.raises(RuntimeError):
        await handle_analyzing(ctx)

    assert ctx.error_category == "DEPENDENCY_ERROR"
    assert "AI repair skipped because this appears to be a missing project dependency." in ctx.recommended_next_action
    assert "Upload the full project folder or include the file/library that defines the missing symbol." in ctx.recommended_next_action

@pytest.mark.asyncio
async def test_oversized_project_fails_preflight(tmp_path, monkeypatch):
    """Verify that oversized zip/project fails early in preflight stage."""
    from app.config.settings import settings
    monkeypatch.setattr(settings, "MAX_TOTAL_FILES_FOR_AUTO_MIGRATION", 2)
    
    ws = tmp_path / "ws"
    for sub in ("input", "generated", "logs", "artifacts", "reports", "exports"):
        (ws / sub).mkdir(parents=True)
        
    (ws / "input" / "kernel.cu").write_text("#include <cuda_runtime.h>\n", encoding="utf-8")
    (ws / "input" / "helper1.cu").write_text("void f1(){}", encoding="utf-8")
    (ws / "input" / "helper2.cu").write_text("void f2(){}", encoding="utf-8")
    
    ctx = WorkflowContext("test-oversized", str(ws))
    ctx.current_state = "PREFLIGHT"
    
    from app.workflow_engine.states import handle_preflight
    with pytest.raises(RuntimeError) as exc:
        await handle_preflight(ctx)
        
    assert "Project is too large" in str(exc.value)
    assert ctx.error_category == "PROJECT_TOO_LARGE"
    assert ctx.infrastructure_error is True
    assert "Extract the archive and migrate one CUDA sample" in ctx.recommended_next_action

@pytest.mark.asyncio
async def test_many_cu_files_triggers_guidance(tmp_path, monkeypatch):
    """Verify that many .cu files exceeds the auto migration limit and provides Guidance."""
    from app.config.settings import settings
    monkeypatch.setattr(settings, "MAX_CUDA_FILES_FOR_AUTO_MIGRATION", 1)
    
    ws = tmp_path / "ws"
    for sub in ("input", "generated", "logs", "artifacts", "reports", "exports"):
        (ws / sub).mkdir(parents=True)
        
    (ws / "input" / "kernel.cu").write_text("#include <cuda_runtime.h>\n", encoding="utf-8")
    (ws / "input" / "helper1.cu").write_text("void f1(){}", encoding="utf-8")
    
    ctx = WorkflowContext("test-many-cu", str(ws))
    ctx.current_state = "PREFLIGHT"
    
    from app.workflow_engine.states import handle_preflight
    with pytest.raises(RuntimeError) as exc:
        await handle_preflight(ctx)
        
    assert "number of CUDA files" in str(exc.value)
    assert ctx.error_category == "PROJECT_TOO_LARGE"
    assert "Extract the archive" in ctx.recommended_next_action

@pytest.mark.asyncio
async def test_dependency_error_skips_ai_repair_without_delay(tmp_path):
    """Verify that dependency errors skip AI repair immediately by setting infrastructure_error."""
    ws = tmp_path / "ws"
    for sub in ("input", "generated", "logs", "artifacts", "reports", "exports"):
        (ws / sub).mkdir(parents=True)
    hip_file = ws / "generated" / "kernel.hip"
    hip_file.write_text("int main() { return 0; }\n", encoding="utf-8")

    ctx = WorkflowContext("test-dep-skip", str(ws))
    ctx.hipify_output_path = str(hip_file)
    ctx.last_compile_stderr = "fatal error: 'missing_lib.h' file not found"
    ctx.current_state = "COMPILING"
    ctx.target_gpu_architecture = "gfx90a"
    
    with patch("app.compiler.hipcc_runner.run_hipcc") as mock_run:
        mock_run.return_value = {
            "success": False,
            "errors": [],
            "stderr": "fatal error: 'missing_lib.h' file not found",
            "stdout": "",
            "command": "hipcc"
        }
        from app.workflow_engine.states import handle_compiling
        await handle_compiling(ctx)
        
    assert ctx.compilation_success is False
    assert ctx.error_category == "DEPENDENCY_ERROR"
    assert ctx.infrastructure_error is True
    assert "AI repair skipped because this appears to be a missing project dependency." in ctx.recommended_next_action

@pytest.mark.asyncio
async def test_stage_timings_in_json_report(tmp_path, monkeypatch):
    """Verify that stage timings are serialized into the JSON report."""
    mid = "test-timings-json"
    ws = tmp_path / mid
    for sub in ("input", "generated", "logs", "artifacts", "reports", "exports"):
        (ws / sub).mkdir(parents=True)
        
    ctx = WorkflowContext(mid, str(ws))
    ctx.stage_timings = {"PREFLIGHT": 1.23, "HIPIFY": 2.34}
    ctx.compilation_success = True
    ctx.project_inventory = {"input_kind": "single_file"}
    
    monkeypatch.setattr(
        "app.services.report_service.get_workspace_path",
        lambda _id: ws,
    )
    
    from app.services.report_service import generate_json_report
    await generate_json_report(mid, ctx)
    
    json_path = ws / "reports" / "migration_report.json"
    assert json_path.exists()
    import json
    data = json.loads(json_path.read_text(encoding="utf-8"))
    
    metrics = data.get("migration_metrics", {})
    assert "stage_timings" in metrics
    assert metrics["stage_timings"]["PREFLIGHT"] == 1.23
    assert metrics["stage_timings"]["HIPIFY"] == 2.34

def test_ai_context_cap_truncation(monkeypatch):
    """Verify that huge prompts are truncated according to settings.MAX_AI_PROMPT_CONTEXT_CHARS."""
    from app.config.settings import settings
    monkeypatch.setattr(settings, "MAX_AI_PROMPT_CONTEXT_CHARS", 100)
    
    source = "A" * 500
    errors = ["Error" * 50]
    
    ctx = MagicMock()
    ctx.ai_context_truncated = False
    
    from app.agents.analysis_agent import _build_messages
    messages = _build_messages(
        source_code=source,
        compiler_errors=errors,
        attempt=0,
        migration_journal=[],
        previous_research=None,
        context=ctx
    )
    
    user_content = messages[1]["content"]
    assert len(user_content) <= 150
    assert ctx.ai_context_truncated is True

@pytest.mark.asyncio
async def test_normal_small_cuda_project_runs(tmp_path, monkeypatch):
    """Verify that a small project with direct compile and no errors succeeds preflight."""
    ws = tmp_path / "ws"
    for sub in ("input", "generated", "logs", "artifacts", "reports", "exports"):
        (ws / sub).mkdir(parents=True)
        
    (ws / "input" / "kernel.cu").write_text("#include <cuda_runtime.h>\n__global__ void k(){}\nint main(){return 0;}\n", encoding="utf-8")
    
    ctx = WorkflowContext("test-normal-small", str(ws))
    ctx.target_gpu_architecture = "gfx90a"
    ctx.current_state = "PREFLIGHT"
    
    from app.workflow_engine.states import handle_preflight
    next_state = await handle_preflight(ctx)
    assert next_state == "HIPIFY"
    assert ctx.error_category == "NONE"
    assert ctx.infrastructure_error is False
