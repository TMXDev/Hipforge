import pytest
import os
import shutil
from pathlib import Path
from app.workflow_engine.context import WorkflowContext
from app.compiler.validator import (
    scan_file_for_cuda_apis,
    replace_cuda_apis_in_file,
    validate_and_replace_cuda_apis,
    CUDA_TO_HIP_MAP,
)
from app.compiler.error_parser import classify_compiler_error
from app.models.compiler_error import CompilerError
from app.workflow_engine.states import handle_analyzing, handle_patching


@pytest.fixture()
def workspace(tmp_path):
    """Creates a temporary workspace structure."""
    ws = tmp_path / "test_validator_ws"
    for subdir in ("input", "generated", "logs", "artifacts", "reports", "exports"):
        (ws / subdir).mkdir(parents=True)
    return ws


@pytest.fixture()
def ctx(workspace):
    """Returns a WorkflowContext configured for tests."""
    return WorkflowContext(
        migration_id="test-migration-val",
        workspace_path=str(workspace),
    )


def test_scan_file_for_cuda_apis(tmp_path):
    test_file = tmp_path / "test_kernel.cu"
    test_file.write_text(
        "__global__ void test() {\n"
        "    cudaMalloc(&dev_ptr, 1024);\n"
        "    cudaMemcpy(dst, src, 1024, cudaMemcpyHostToDevice);\n"
        "}\n",
        encoding="utf-8"
    )
    apis = scan_file_for_cuda_apis(test_file)
    assert "cudaMalloc" in apis
    assert "cudaMemcpy" in apis
    assert apis["cudaMalloc"] == [2]
    assert apis["cudaMemcpy"] == [3]


def test_replace_cuda_apis_in_file(tmp_path):
    test_file = tmp_path / "test_kernel.cu"
    test_file.write_text(
        "cudaMalloc(&dev_ptr, 1024);\n",
        encoding="utf-8"
    )
    count = replace_cuda_apis_in_file(test_file, CUDA_TO_HIP_MAP)
    assert count == 1
    content = test_file.read_text(encoding="utf-8")
    assert "hipMalloc" in content
    assert "cudaMalloc" not in content


@pytest.mark.anyio
async def test_validate_and_replace_cuda_apis(workspace, ctx):
    # Setup files in input/ and generated/
    input_file = workspace / "input" / "kernel.cu"
    input_file.write_text(
        "cudaMalloc(&p, 10);\ncudaMemcpy(p, s, 10, cudaMemcpyDefault);\n",
        encoding="utf-8"
    )
    gen_file = workspace / "generated" / "kernel.hip"
    gen_file.write_text(
        "cudaMalloc(&p, 10);\n// hipify left this:\ncudaMemcpy(p, s, 10, cudaMemcpyDefault);\n",
        encoding="utf-8"
    )

    await validate_and_replace_cuda_apis(ctx)

    assert ctx.cuda_apis_detected == 3
    assert ctx.cuda_apis_converted == 3
    assert ctx.cuda_apis_remaining == 0
    assert (workspace / "artifacts" / "migration_validation.json").exists()

    content = gen_file.read_text(encoding="utf-8")
    assert "hipMalloc" in content
    assert "hipMemcpy" in content


def test_classify_compiler_error():
    assert classify_compiler_error("hipcc: command not found") == "TOOLCHAIN_ERROR"
    assert classify_compiler_error("hipcc not found") == "TOOLCHAIN_ERROR"
    assert classify_compiler_error("cannot find -lamdhip64") == "DEPENDENCY_ERROR"
    assert classify_compiler_error("hip/hip_runtime.h: No such file or directory") == "DEPENDENCY_ERROR"
    
    assert classify_compiler_error("Docker sandbox error: Container failed") == "ENVIRONMENT_ERROR"
    assert classify_compiler_error("Sandbox timeout occurred") == "ENVIRONMENT_ERROR"
    
    assert classify_compiler_error("Permission denied to write log file") == "ENVIRONMENT_ERROR"
    
    assert classify_compiler_error("kernel.hip:12:5: error: expected ';'") == "USER_CODE_ERROR"
    assert classify_compiler_error("use of undeclared identifier 'hipStream_t'") == "USER_CODE_ERROR"
    assert classify_compiler_error("") == "USER_CODE_ERROR"


@pytest.mark.anyio
async def test_safeguard_non_code_error(ctx):
    ctx.last_compile_stderr = "hipcc: command not found"
    ctx.compiler_errors = [CompilerError(file="f", line=1, column=1, message="hipcc not found", code="E1")]
    
    with pytest.raises(RuntimeError, match="environment/toolchain issue"):
        await handle_analyzing(ctx)
        
    assert ctx.infrastructure_error is True
    assert ctx.error_category == "TOOLCHAIN_ERROR"


@pytest.mark.anyio
async def test_safeguard_repeated_error(ctx):
    ctx.last_compile_stderr = "kernel.hip:12:5: error: expected ';'"
    ctx.compiler_errors = [CompilerError(file="kernel.hip", line=12, column=5, message="expected ';'", code="E1")]
    
    # First time analyzer runs
    ctx.previous_compile_stderr = "kernel.hip:12:5: error: expected ';'"
    ctx.previous_compiler_errors = [CompilerError(file="kernel.hip", line=12, column=5, message="expected ';'", code="E1")]
    
    with pytest.raises(RuntimeError, match="Infinite loop prevented"):
        await handle_analyzing(ctx)
        
    assert ctx.infrastructure_error is True


@pytest.mark.anyio
async def test_safeguard_unchanged_patch(workspace, ctx, monkeypatch):
    ctx.hipify_output_path = str(workspace / "generated" / "kernel.hip")
    Path(ctx.hipify_output_path).write_text("void foo() {}\n", encoding="utf-8")
    ctx.analysis_result = {"repair_plan": []}
    
    # Mock the patch agent to return unchanged source
    monkeypatch.setattr("app.agents.patch_agent.patch", lambda *args, **kwargs: "void foo() {}\n")
    
    with pytest.raises(RuntimeError, match="Patch Agent returned unchanged source code"):
        await handle_patching(ctx)
        
    assert ctx.infrastructure_error is True


def test_compiler_caching(tmp_path):
    import shutil
    from app.compiler.hipcc_runner import CACHE_DIR, HipccRunner
    
    source_file = tmp_path / "test_cache.hip"
    source_file.write_text("void main_func() {}\n", encoding="utf-8")
    output_bin = tmp_path / "test_cache.bin"
    
    # Enable mock compiler environment
    os.environ["USE_MOCK_COMPILER"] = "true"
    
    # Ensure cache directory is empty for this test
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
        
    # First compilation (cache miss)
    runner = HipccRunner()
    res1 = runner.run_hipcc(str(source_file), str(output_bin), target_arch="gfx90a")
    assert res1["success"] is True
    assert "[Cache Hit]" not in res1["stdout"]
    assert Path(output_bin).exists()
    
    # Remove the output binary manually to verify caching restores it
    Path(output_bin).unlink()
    
    # Second compilation (cache hit)
    res2 = runner.run_hipcc(str(source_file), str(output_bin), target_arch="gfx90a")
    assert res2["success"] is True
    assert "[Cache Hit]" in res2["stdout"]
    assert Path(output_bin).exists()
    
    # Clean up the cache directory
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)


def test_scan_ast_for_cuda_apis(tmp_path):
    from app.compiler.validator import scan_ast_for_cuda_apis
    
    cu_file = tmp_path / "cuda_test.cu"
    cu_file.write_text("cudaMalloc(&p, 100);\n", encoding="utf-8")
    
    apis = scan_ast_for_cuda_apis(cu_file)
    assert "cudaMalloc" in apis
    assert apis["cudaMalloc"] == [1]
