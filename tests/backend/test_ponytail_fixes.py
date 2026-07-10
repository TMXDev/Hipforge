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


def test_include_discovery_and_arch(tmp_path):
    # Setup folders
    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True)

    (input_dir / "include").mkdir()
    (input_dir / "src").mkdir()

    from app.compiler.hipify_runner import discover_include_dirs, detect_cuda_arch

    # Create Makefile with -I flags
    makefile = input_dir / "Makefile"
    makefile.write_text("CFLAGS = -I./common -Isrc/utils -I/ignored/absolute -arch=sm_75\n", encoding="utf-8")

    # Create mock subdirs for Makefile flags to be verified
    (input_dir / "common").mkdir()
    (input_dir / "src" / "utils").mkdir()

    # Create src/vector_ops.cu which includes "cuda_check.h"
    (input_dir / "src" / "vector_ops.cu").write_text('#include "cuda_check.h"\n', encoding="utf-8")
    # Place cuda_check.h in include/
    (input_dir / "include" / "cuda_check.h").write_text('// empty\n', encoding="utf-8")

    # Run include paths discovery
    includes = discover_include_dirs(input_dir)

    # Check that obvious dirs, Makefile -I dirs, and parent of quoted includes are present
    assert str((input_dir / "include").resolve()) in includes
    assert str((input_dir / "src").resolve()) in includes
    assert str((input_dir / "common").resolve()) in includes
    assert str((input_dir / "src" / "utils").resolve()) in includes

    # Check arch detection
    arch = detect_cuda_arch(input_dir)
    assert arch == "sm_75"

@pytest.mark.asyncio
async def test_hipify_recovery_and_retry(tmp_path, monkeypatch):
    from app.workflow_engine.context import WorkflowContext
    from app.workflow_engine.states import handle_hipify
    from app.workflow_engine.transitions import determine_next_state

    ws = tmp_path / "ws"
    for sub in ("input", "generated", "logs", "artifacts", "reports", "exports"):
        (ws / sub).mkdir(parents=True)

    (ws / "input" / "vector_ops.cu").write_text("#include \"cuda_check.h\"\n", encoding="utf-8")

    # First try without header (recoverable error)
    ctx = WorkflowContext("test-hipify-retry", str(ws), retry_budget=3)
    ctx.current_state = "HIPIFY"

    # Mock run_hipify to simulate failure containing "file not found"
    calls = []
    def mock_run_hipify(src, dest, extra_include_dirs=None, cuda_parser_arch=None, cuda_toolkit_path=None):
        calls.append((src, dest, extra_include_dirs, cuda_parser_arch))
        # First call has no extra_include_dirs mapping include/
        if not extra_include_dirs or not any("include" in d for d in extra_include_dirs):
            return {
                "success": False,
                "stdout": "",
                "stderr": "fatal error: 'cuda_check.h' file not found"
            }
        return {
            "success": True,
            "stdout": "[Sandbox HIPIFY] completed.",
            "stderr": "",
            "output_path": dest
        }

    monkeypatch.setattr("app.compiler.hipify_runner.run_hipify", mock_run_hipify)

    # Run handle_hipify, which fails
    with pytest.raises(RuntimeError):
        await handle_hipify(ctx)

    # Check transitions
    assert ctx.last_hipify_stderr == "fatal error: 'cuda_check.h' file not found"

    next_state = determine_next_state("HIPIFY", False, ctx)
    assert next_state == "HIPIFY"
    assert ctx.current_attempt == 1

    # Now simulate the header being present (representing a repair or subsequent attempt where we pass include/)
    (ws / "input" / "include").mkdir()
    (ws / "input" / "include" / "cuda_check.h").write_text("//", encoding="utf-8")

    # Run handle_hipify again (simulate state machine running it again)
    ctx.current_state = "HIPIFY"
    await handle_hipify(ctx)

    # Transitions should now succeed
    next_state = determine_next_state("HIPIFY", True, ctx)
    assert next_state == "SCA"

    # Verify original files remain unchanged
    assert (ws / "input" / "vector_ops.cu").read_text(encoding="utf-8") == "#include \"cuda_check.h\"\n"

@pytest.mark.asyncio
async def test_hipify_retry_exhaustion(tmp_path, monkeypatch):
    from app.workflow_engine.context import WorkflowContext
    from app.workflow_engine.states import handle_hipify
    from app.workflow_engine.transitions import determine_next_state

    ws = tmp_path / "ws"
    for sub in ("input", "generated", "logs", "artifacts", "reports", "exports"):
        (ws / sub).mkdir(parents=True)

    (ws / "input" / "vector_ops.cu").write_text("#include \"cuda_check.h\"\n", encoding="utf-8")

    ctx = WorkflowContext("test-hipify-exhaustion", str(ws), retry_budget=2)
    ctx.current_state = "HIPIFY"

    def mock_run_hipify_fail(src, dest, extra_include_dirs=None, cuda_parser_arch=None, cuda_toolkit_path=None):
        return {
            "success": False,
            "stdout": "",
            "stderr": "fatal error: 'cuda_check.h' file not found"
        }

    monkeypatch.setattr("app.compiler.hipify_runner.run_hipify", mock_run_hipify_fail)

    # Attempt 0: fails
    with pytest.raises(RuntimeError):
        await handle_hipify(ctx)
    next_state = determine_next_state("HIPIFY", False, ctx)
    assert next_state == "HIPIFY"
    assert ctx.current_attempt == 1

    # Change config/input to bypass identical fingerprint check
    (ws / "input" / "change1.cu").write_text("// 1\n", encoding="utf-8")

    # Attempt 1: fails
    ctx.current_state = "HIPIFY"
    with pytest.raises(RuntimeError):
        await handle_hipify(ctx)
    next_state = determine_next_state("HIPIFY", False, ctx)
    assert next_state == "HIPIFY"
    assert ctx.current_attempt == 2

    # Change config/input again
    (ws / "input" / "change2.cu").write_text("// 2\n", encoding="utf-8")

    # Attempt 2: fails, budget is 2, so should transition to report
    ctx.current_state = "HIPIFY"
    with pytest.raises(RuntimeError):
        await handle_hipify(ctx)
    next_state = determine_next_state("HIPIFY", False, ctx)
    assert next_state == "GENERATING_REPORT"


@pytest.mark.asyncio
async def test_identical_recoverable_hipify_not_repeated(tmp_path, monkeypatch):
    from app.workflow_engine.context import WorkflowContext
    from app.workflow_engine.states import handle_hipify
    from app.workflow_engine.transitions import determine_next_state

    ws = tmp_path / "ws"
    for sub in ("input", "generated", "logs", "artifacts", "reports", "exports"):
        (ws / sub).mkdir(parents=True)
    (ws / "input" / "vector_ops.cu").write_text("#include \"cuda_check.h\"\n", encoding="utf-8")

    ctx = WorkflowContext("test-identical-fp", str(ws), retry_budget=3)
    ctx.current_state = "HIPIFY"

    # Mock run_hipify to simulate recoverable error (e.g. missing include)
    def mock_run_hipify(src, dest, extra_include_dirs=None, cuda_parser_arch=None, cuda_toolkit_path=None):
        return {
            "success": False,
            "stdout": "",
            "stderr": "fatal error: 'cuda_check.h' file not found"
        }
    monkeypatch.setattr("app.compiler.hipify_runner.run_hipify", mock_run_hipify)

    # Run handle_hipify which sets fingerprint and fails
    with pytest.raises(RuntimeError):
        await handle_hipify(ctx)

    # First failure: transitions to HIPIFY (a retry is scheduled)
    next_state = determine_next_state("HIPIFY", False, ctx)
    assert next_state == "HIPIFY"
    # Current attempt is incremented for recoverable retry
    assert ctx.current_attempt == 1

    # Run handle_hipify again with identical config/inputs -> fingerprint is same
    with pytest.raises(RuntimeError):
        await handle_hipify(ctx)

    # Second failure: fingerprint matches, so it is rejected and transitions to GENERATING_REPORT
    next_state2 = determine_next_state("HIPIFY", False, ctx)
    assert next_state2 == "GENERATING_REPORT"


@pytest.mark.asyncio
async def test_changed_config_permits_retry(tmp_path, monkeypatch):
    from app.workflow_engine.context import WorkflowContext
    from app.workflow_engine.states import handle_hipify
    from app.workflow_engine.transitions import determine_next_state

    ws = tmp_path / "ws"
    for sub in ("input", "generated", "logs", "artifacts", "reports", "exports"):
        (ws / sub).mkdir(parents=True)
    (ws / "input" / "vector_ops.cu").write_text("#include \"cuda_check.h\"\n", encoding="utf-8")

    ctx = WorkflowContext("test-changed-config", str(ws), retry_budget=3)
    ctx.current_state = "HIPIFY"

    # Mock run_hipify to always fail
    def mock_run_hipify(src, dest, extra_include_dirs=None, cuda_parser_arch=None, cuda_toolkit_path=None):
        return {
            "success": False,
            "stdout": "",
            "stderr": "fatal error: 'cuda_check.h' file not found"
        }
    monkeypatch.setattr("app.compiler.hipify_runner.run_hipify", mock_run_hipify)

    # Run first attempt
    with pytest.raises(RuntimeError):
        await handle_hipify(ctx)
    next_state = determine_next_state("HIPIFY", False, ctx)
    assert next_state == "HIPIFY"
    assert ctx.current_attempt == 1

    # Now simulate a changed configuration: we add a file to input
    (ws / "input" / "another.cu").write_text("// dummy\n", encoding="utf-8")

    # Run second attempt (fingerprint will change because of new file in source files list)
    with pytest.raises(RuntimeError):
        await handle_hipify(ctx)

    # It should permit the retry (next_state is HIPIFY, not GENERATING_REPORT)
    next_state2 = determine_next_state("HIPIFY", False, ctx)
    assert next_state2 == "HIPIFY"
    assert ctx.current_attempt == 2


@pytest.mark.asyncio
async def test_semantic_patch_consumed_by_next_hipify(tmp_path, monkeypatch):
    from app.workflow_engine.context import WorkflowContext
    from app.workflow_engine.states import handle_hipify, handle_patching
    from app.workflow_engine.transitions import determine_next_state

    ws = tmp_path / "ws"
    for sub in ("input", "generated", "logs", "artifacts", "reports", "exports", "patches"):
        (ws / sub).mkdir(parents=True)

    # Create target source file
    (ws / "input" / "vector_ops.cu").write_text("#include \"cuda_check.h\"\n", encoding="utf-8")

    ctx = WorkflowContext("test-semantic-patch-consumption", str(ws), retry_budget=3)
    ctx.current_state = "HIPIFY"
    ctx.failed_stage = "HIPIFY"

    # Mock run_hipify to simulate failure initially
    run_calls = []
    def mock_run_hipify(src, dest, extra_include_dirs=None, cuda_parser_arch=None, cuda_toolkit_path=None):
        run_calls.append(src)
        return {
            "success": False,
            "stdout": "",
            "stderr": "semantic error or parsing failed"
        }
    monkeypatch.setattr("app.compiler.hipify_runner.run_hipify", mock_run_hipify)

    # 1. HIPIFY runs and fails
    with pytest.raises(RuntimeError):
        await handle_hipify(ctx)

    next_state = determine_next_state("HIPIFY", False, ctx)
    assert next_state == "ANALYZING"

    # 2. AI repair: PATCHING state runs
    ctx.analysis_result = {
        "confidence": 0.9,
        "root_cause": "hipMemcpyAsync_WRONG is not a valid HIP API.",
        "repair_plan": ["Replace hipMemcpyAsync_WRONG with hipMemcpyAsync."]
    }
    # Realistic localized patch: only the bad API token changes
    _orig_source = (
        "#include <hip/hip_runtime.h>\n"
        "void transfer(float* d, float* s, int n, hipStream_t st) {\n"
        "    hipMemcpyAsync_WRONG(d, s, n*sizeof(float), hipMemcpyDeviceToDevice, st);\n"
        "}\n"
    )
    _patched_source = _orig_source.replace("hipMemcpyAsync_WRONG", "hipMemcpyAsync")
    def mock_patch(*args, **kwargs):
        return _patched_source
    monkeypatch.setattr("app.agents.patch_agent.patch", mock_patch)

    # Mock run_hipcc to make compile probe succeed
    def mock_run_hipcc(*args, **kwargs):
        return {
            "success": True,
            "errors": [],
            "stdout": "mock compile probe passed",
            "stderr": "",
            "command": "hipcc ...",
            "actual_arch": "gfx90a"
        }
    monkeypatch.setattr("app.compiler.hipcc_runner.run_hipcc", mock_run_hipcc)

    ctx.hipify_output_path = str(ws / "generated" / "vector_ops.hip")
    # Simulate generated file with the bad API name
    (ws / "generated" / "vector_ops.hip").write_text(_orig_source, encoding="utf-8")

    ctx.current_state = "PATCHING"
    await handle_patching(ctx)

    # Verify patch was written to patches/
    patch_dir_files = list((ws / "patches").glob("patch_attempt_*_vector_ops.hip"))
    assert len(patch_dir_files) == 1

    # 3. Transitions state back to HIPIFY (since failed_stage is HIPIFY)
    next_state2 = determine_next_state("PATCHING", True, ctx)
    assert next_state2 == "HIPIFY"

    # Clear run_calls to see if run_hipify gets called on retry
    run_calls.clear()

    # Run handle_hipify again
    ctx.current_state = "HIPIFY"
    await handle_hipify(ctx)

    # run_hipify should NOT have been called because it consumed the patch!
    assert len(run_calls) == 0
    # The generated file in workspace should contain the fixed API name
    gen_file = ws / "generated" / "vector_ops.hip"
    assert "hipMemcpyAsync" in gen_file.read_text(encoding="utf-8")
    # File lifecycle should indicate modified by AI
    assert ctx.file_lifecycle["vector_ops.cu"]["modified_by_ai"] is True


@pytest.mark.asyncio
async def test_one_semantic_recovery_one_retry(tmp_path, monkeypatch):
    from app.workflow_engine.context import WorkflowContext
    from app.workflow_engine.states import handle_hipify, handle_patching
    from app.workflow_engine.transitions import determine_next_state

    ws = tmp_path / "ws"
    for sub in ("input", "generated", "logs", "artifacts", "reports", "exports", "patches"):
        (ws / sub).mkdir(parents=True)
    (ws / "input" / "vector_ops.cu").write_text("#include \"cuda_check.h\"\n", encoding="utf-8")

    ctx = WorkflowContext("test-semantic-attempt-count", str(ws), retry_budget=3)
    ctx.current_state = "HIPIFY"
    ctx.failed_stage = "HIPIFY"

    # Mock run_hipify to simulate failure
    def mock_run_hipify(*args, **kwargs):
        return {
            "success": False,
            "stdout": "",
            "stderr": "semantic error"
        }
    monkeypatch.setattr("app.compiler.hipify_runner.run_hipify", mock_run_hipify)

    # First HIPIFY failure
    with pytest.raises(RuntimeError):
        await handle_hipify(ctx)

    # Transition to ANALYZING. Attempt counter should NOT increment yet!
    next_state = determine_next_state("HIPIFY", False, ctx)
    assert next_state == "ANALYZING"
    assert ctx.current_attempt == 0

    # Transition PATCHING runs
    ctx.analysis_result = {
        "root_cause": "hipMemcpyAsync_WRONG is not a valid HIP API.",
        "repair_plan": ["Replace hipMemcpyAsync_WRONG with hipMemcpyAsync."]
    }
    # Realistic localized patch: only the bad API token changes
    _orig = (
        "#include <hip/hip_runtime.h>\n"
        "void transfer(float* d, float* s, int n, hipStream_t st) {\n"
        "    hipMemcpyAsync_WRONG(d, s, n*sizeof(float), hipMemcpyDeviceToDevice, st);\n"
        "}\n"
    )
    def mock_patch(*args, **kwargs):
        return _orig.replace("hipMemcpyAsync_WRONG", "hipMemcpyAsync")
    monkeypatch.setattr("app.agents.patch_agent.patch", mock_patch)

    # Mock run_hipcc to make compile probe succeed
    def mock_run_hipcc(*args, **kwargs):
        return {
            "success": True,
            "errors": [],
            "stdout": "mock compile probe passed",
            "stderr": "",
            "command": "hipcc ...",
            "actual_arch": "gfx90a"
        }
    monkeypatch.setattr("app.compiler.hipcc_runner.run_hipcc", mock_run_hipcc)
    ctx.hipify_output_path = str(ws / "generated" / "vector_ops.hip")
    (ws / "generated" / "vector_ops.hip").write_text(_orig, encoding="utf-8")

    ctx.current_state = "PATCHING"
    await handle_patching(ctx)

    # handle_patching increments attempt to 1
    assert ctx.current_attempt == 1

    # Transition back to HIPIFY
    next_state2 = determine_next_state("PATCHING", True, ctx)
    assert next_state2 == "HIPIFY"

    # So one full semantic repair cycle has consumed exactly 1 retry (0 -> 1)!
    assert ctx.current_attempt == 1


def test_escaping_include_paths_rejected(tmp_path):
    from app.compiler.hipify_runner import discover_include_dirs
    import os

    input_dir = tmp_path / "input"
    input_dir.mkdir()

    # Create a target directory outside input_dir
    outside_dir = tmp_path / "outside_include"
    outside_dir.mkdir()

    # Create an escaping symlink or junction
    escape_link = input_dir / "include"

    # Helper to create a junction or symlink
    if os.name == 'nt':
        import subprocess
        subprocess.run(["cmd", "/c", "mklink", "/J", str(escape_link), str(outside_dir)], check=True, capture_output=True)
    else:
        os.symlink(outside_dir, escape_link, target_is_directory=True)

    # Run discover_include_dirs
    includes = discover_include_dirs(input_dir)

    # The outside directory must NOT be present in includes
    assert str(outside_dir.resolve()) not in includes
    # The symlink/junction path itself must NOT be present if it resolves outside
    assert str(escape_link.resolve()) not in includes


def test_local_include_paths_accepted(tmp_path):
    from app.compiler.hipify_runner import discover_include_dirs

    input_dir = tmp_path / "input"
    input_dir.mkdir()

    # Create normal local include dir
    local_dir = input_dir / "include"
    local_dir.mkdir()

    # Run discover_include_dirs
    includes = discover_include_dirs(input_dir)

    # It must be accepted
    assert str(local_dir.resolve()) in includes


@pytest.mark.asyncio
async def test_single_file_cuda_migration_lightweight(tmp_path):
    from app.workflow_engine.context import WorkflowContext
    from app.workflow_engine.states import handle_preflight

    ws = tmp_path / "ws"
    for sub in ("input", "generated", "logs", "artifacts", "reports", "exports"):
        (ws / sub).mkdir(parents=True)

    (ws / "input" / "single_kernel.cu").write_text("int main() { return 0; }\n", encoding="utf-8")

    ctx = WorkflowContext("test-single-lightweight", str(ws))
    ctx.current_state = "PREFLIGHT"

    next_state = await handle_preflight(ctx)
    assert next_state == "HIPIFY"
    assert ctx.project_inventory["input_kind"] == "single_file"
    assert ctx.error_category == "NONE"


def test_compilation_cache_key_robustness(tmp_path):
    from app.compiler.hipcc_runner import compute_compilation_cache_key
    
    ws = tmp_path / "ws"
    (ws / "generated").mkdir(parents=True)
    
    # 1. Base cache key
    source = ws / "generated" / "kernel.hip"
    source.write_text("int main() { return 0; }", encoding="utf-8")
    
    key1 = compute_compilation_cache_key(str(source), target_arch="gfx942", workspace_path=str(ws), cmd_str="hipcc kernel.hip -o out --offload-arch=gfx942")
    
    # 2. Modify target arch
    key2 = compute_compilation_cache_key(str(source), target_arch="gfx90a", workspace_path=str(ws), cmd_str="hipcc kernel.hip -o out --offload-arch=gfx90a")
    assert key1 != key2
    
    # 3. Modify source file content
    source.write_text("int main() { return 1; }", encoding="utf-8")
    key3 = compute_compilation_cache_key(str(source), target_arch="gfx942", workspace_path=str(ws), cmd_str="hipcc kernel.hip -o out --offload-arch=gfx942")
    assert key1 != key3

    # 4. Modify build file content (Makefile)
    makefile = ws / "generated" / "Makefile"
    makefile.write_text("all:\n\t$(HIPCC) kernel.hip -o out", encoding="utf-8")
    key4 = compute_compilation_cache_key(str(source), target_arch="gfx942", workspace_path=str(ws), cmd_str="hipcc kernel.hip -o out --offload-arch=gfx942")
    assert key3 != key4


def test_compiled_architecture_regex(tmp_path):
    from app.compiler.hipcc_runner import detect_compiled_architecture
    
    bin_file = tmp_path / "mock.bin"
    
    # Check that gfx942 is extracted from mock binary
    bin_file.write_bytes(b"some prefix code gfx942 some suffix code")
    assert detect_compiled_architecture(str(bin_file)) == "gfx942"
    
    # Check gfx906 is extracted
    bin_file.write_bytes(b"some prefix code gfx906 some suffix code")
    assert detect_compiled_architecture(str(bin_file)) == "gfx906"

    # Check non-matching
    bin_file.write_bytes(b"no matching architecture signature here")
    assert detect_compiled_architecture(str(bin_file)) is None
