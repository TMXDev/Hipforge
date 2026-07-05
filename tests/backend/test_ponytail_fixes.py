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
