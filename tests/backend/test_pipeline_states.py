"""
tests/backend/test_pipeline_states.py

End-to-end integration test verifying that a real CUDA source file traverses
the HIPIFY → SCA → COMPILING pipeline states correctly.

Session 8.4 gate:
  - handle_hipify() calls run_hipify(), stores output_path in context
  - handle_sca() calls analyze(), stores sca_result, writes migration_risks.json
  - handle_compiling() calls run_hipcc(), stores errors + compilation_success

All compiler tools run in mock mode (USE_MOCK_COMPILER=true, pre-hackathon).

Gate: pytest tests/backend/test_pipeline_states.py -v
"""

import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Force mock mode before importing any app code so factory functions
# pick up USE_MOCK_COMPILER=true regardless of .env content.
# ---------------------------------------------------------------------------
os.environ["USE_MOCK_COMPILER"] = "true"
os.environ["USE_MOCK_AI"] = "true"

from app.workflow_engine.context import WorkflowContext
from app.workflow_engine.states import handle_hipify, handle_sca, handle_compiling


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAMPLE_CUDA = FIXTURE_DIR / "sample.cu"   # clean CUDA file — no mock error trigger


@pytest.fixture()
def workspace(tmp_path):
    """
    Creates a minimal workspace with all required subdirectories
    and places the sample CUDA fixture in input/.
    Returns the workspace root Path.
    """
    ws = tmp_path / "test_migration"
    for subdir in ("input", "generated", "logs", "artifacts", "reports", "exports"):
        (ws / subdir).mkdir(parents=True)
    shutil.copy(SAMPLE_CUDA, ws / "input" / "sample.cu")
    return ws


@pytest.fixture()
def ctx(workspace):
    """Returns a WorkflowContext pointing at the temp workspace."""
    return WorkflowContext(
        migration_id="migration_20260701_000000_test",
        workspace_path=str(workspace),
    )


# ---------------------------------------------------------------------------
# Test: handle_hipify
# ---------------------------------------------------------------------------

class TestHandleHipify:
    """handle_hipify must translate the CUDA file and update context."""

    @pytest.mark.asyncio
    async def test_returns_sca(self, ctx):
        assert await handle_hipify(ctx) == "SCA"

    @pytest.mark.asyncio
    async def test_stores_output_path(self, ctx):
        await handle_hipify(ctx)
        assert ctx.hipify_output_path is not None, (
            "hipify_output_path must be set after handle_hipify"
        )

    @pytest.mark.asyncio
    async def test_output_file_exists(self, ctx, workspace):
        await handle_hipify(ctx)
        assert Path(ctx.hipify_output_path).exists()

    @pytest.mark.asyncio
    async def test_output_in_generated_dir(self, ctx, workspace):
        await handle_hipify(ctx)
        assert Path(ctx.hipify_output_path).parent == workspace / "generated"

    @pytest.mark.asyncio
    async def test_output_has_hip_extension(self, ctx):
        await handle_hipify(ctx)
        assert ctx.hipify_output_path.endswith(".hip")

    @pytest.mark.asyncio
    async def test_translated_content_not_empty(self, ctx):
        await handle_hipify(ctx)
        content = Path(ctx.hipify_output_path).read_text(encoding="utf-8")
        assert content.strip()

    @pytest.mark.asyncio
    async def test_fails_on_missing_source(self, workspace):
        """HIPIFY must raise RuntimeError if no .cu file is in input/."""
        for f in (workspace / "input").iterdir():
            f.unlink()
        c = WorkflowContext(
            migration_id="migration_20260701_000000_empty",
            workspace_path=str(workspace),
        )
        with pytest.raises(RuntimeError, match="HIPIFY"):
            await handle_hipify(c)

    @pytest.mark.asyncio
    async def test_fails_on_mock_error_trigger(self, workspace):
        """HIPIFY must raise RuntimeError when source contains mock failure trigger."""
        trigger_content = (
            "// HIPFORGE_MOCK_COMPILE_ERROR\n"
            "#include <cuda_runtime.h>\n"
            "__global__ void bad() {}\n"
        )
        (workspace / "input" / "sample.cu").write_text(trigger_content, encoding="utf-8")
        c = WorkflowContext(
            migration_id="migration_20260701_000000_fail",
            workspace_path=str(workspace),
        )
        with pytest.raises(RuntimeError, match="HIPIFY failed"):
            await handle_hipify(c)


# ---------------------------------------------------------------------------
# Test: handle_sca
# ---------------------------------------------------------------------------

class TestHandleSca:
    """handle_sca must scan the HIP file and write migration_risks.json."""

    @pytest.mark.asyncio
    async def test_returns_compiling(self, ctx):
        await handle_hipify(ctx)
        assert await handle_sca(ctx) == "COMPILING"

    @pytest.mark.asyncio
    async def test_stores_sca_result(self, ctx):
        await handle_hipify(ctx)
        await handle_sca(ctx)
        assert ctx.sca_result is not None

    @pytest.mark.asyncio
    async def test_sca_result_has_issues_and_score(self, ctx):
        await handle_hipify(ctx)
        await handle_sca(ctx)
        assert "issues" in ctx.sca_result
        assert "score" in ctx.sca_result

    @pytest.mark.asyncio
    async def test_sca_score_in_range(self, ctx):
        await handle_hipify(ctx)
        await handle_sca(ctx)
        assert 0.0 <= ctx.sca_result["score"] <= 1.0

    @pytest.mark.asyncio
    async def test_migration_risks_json_written(self, ctx, workspace):
        await handle_hipify(ctx)
        await handle_sca(ctx)
        assert (workspace / "artifacts" / "migration_risks.json").exists()

    @pytest.mark.asyncio
    async def test_migration_risks_json_is_valid(self, ctx, workspace):
        await handle_hipify(ctx)
        await handle_sca(ctx)
        data = json.loads((workspace / "artifacts" / "migration_risks.json").read_text())
        assert "score" in data
        assert "issues" in data
        assert isinstance(data["issues"], list)

    @pytest.mark.asyncio
    async def test_sca_without_hipify_output(self, ctx):
        """SCA must handle missing hipify_output_path gracefully (scan from input/)."""
        # ctx.hipify_output_path is None — SCA falls back to input/*.cu
        result = await handle_sca(ctx)
        assert result == "COMPILING"
        assert ctx.sca_result is not None


# ---------------------------------------------------------------------------
# Test: handle_compiling
# ---------------------------------------------------------------------------

class TestHandleCompiling:
    """handle_compiling must run hipcc and update context with results."""

    @pytest.mark.asyncio
    async def test_returns_compiling(self, ctx):
        await handle_hipify(ctx)
        await handle_sca(ctx)
        assert await handle_compiling(ctx) == "COMPILING"

    @pytest.mark.asyncio
    async def test_sets_compilation_success_true_for_clean_source(self, ctx):
        await handle_hipify(ctx)
        await handle_sca(ctx)
        await handle_compiling(ctx)
        assert ctx.compilation_success is True

    @pytest.mark.asyncio
    async def test_empty_errors_on_success(self, ctx):
        await handle_hipify(ctx)
        await handle_sca(ctx)
        await handle_compiling(ctx)
        assert ctx.compiler_errors == []

    @pytest.mark.asyncio
    async def test_sets_last_compile_stderr_attribute(self, ctx):
        await handle_hipify(ctx)
        await handle_sca(ctx)
        await handle_compiling(ctx)
        assert hasattr(ctx, "last_compile_stderr")

    @pytest.mark.asyncio
    async def test_compile_log_written(self, ctx, workspace):
        await handle_hipify(ctx)
        await handle_sca(ctx)
        await handle_compiling(ctx)
        log_files = list((workspace / "logs").glob("compile_attempt_*.log"))
        assert log_files, "At least one compile log must be written"

    @pytest.mark.asyncio
    async def test_compile_log_content(self, ctx, workspace):
        await handle_hipify(ctx)
        await handle_sca(ctx)
        await handle_compiling(ctx)
        log_file = sorted((workspace / "logs").glob("compile_attempt_*.log"))[0]
        content = log_file.read_text(encoding="utf-8")
        assert "HIPForge Compile Attempt" in content
        assert "Source:" in content

    @pytest.mark.asyncio
    async def test_failure_path_sets_errors(self, workspace):
        """Compilation of a file with mock error trigger must populate errors."""
        trigger_content = (
            "#include <hip/hip_runtime.h>\n"
            "// HIPFORGE_MOCK_COMPILE_ERROR\n"
            "__global__ void broken() {}\n"
        )
        error_hip = workspace / "generated" / "broken.hip"
        error_hip.write_text(trigger_content, encoding="utf-8")

        c = WorkflowContext(
            migration_id="migration_20260701_000000_err",
            workspace_path=str(workspace),
        )
        c.hipify_output_path = str(error_hip)

        await handle_compiling(c)

        assert c.compilation_success is False
        assert len(c.compiler_errors) > 0


# ---------------------------------------------------------------------------
# Gate test: end-to-end HIPIFY → SCA → COMPILING
# ---------------------------------------------------------------------------

class TestEndToEndPipeline:
    """
    Gate test: a real CUDA file must traverse HIPIFY → SCA → COMPILING
    and all context fields must be correctly populated.
    """

    @pytest.mark.asyncio
    async def test_full_pipeline_traversal(self, ctx, workspace):
        # Stage 1: HIPIFY
        next_after_hipify = await handle_hipify(ctx)
        assert next_after_hipify == "SCA"
        assert ctx.hipify_output_path is not None
        assert Path(ctx.hipify_output_path).exists()

        # Stage 2: SCA
        next_after_sca = await handle_sca(ctx)
        assert next_after_sca == "COMPILING"
        assert ctx.sca_result is not None
        assert "issues" in ctx.sca_result
        assert "score" in ctx.sca_result
        assert (workspace / "artifacts" / "migration_risks.json").exists()

        # Stage 3: COMPILING
        next_after_compiling = await handle_compiling(ctx)
        assert next_after_compiling == "COMPILING"
        assert isinstance(ctx.compilation_success, bool)
        assert isinstance(ctx.compiler_errors, list)
        assert hasattr(ctx, "last_compile_stderr")
        assert list((workspace / "logs").glob("compile_attempt_*.log"))

        # Clean source → should succeed in mock mode
        assert ctx.compilation_success is True
