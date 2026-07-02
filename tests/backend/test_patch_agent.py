"""
tests/backend/test_patch_agent.py

Unit tests for the Patch Agent (Session 9.3).

Verifies:
  - patch() uses the correct 6-section prompt structure
  - Returns the full corrected source file as a string
  - Targeted error is absent from the patched output
  - handle_patching() wires correctly into the Workflow Engine state
  - Patched file is written to workspace patches/ directory
  - context.hipify_output_path updated to point at new patched file

Gate: Patch Agent returns corrected source. Known error is absent in the output.
      pytest tests/backend/test_patch_agent.py -v --asyncio-mode=auto
"""

import json
import os
from pathlib import Path

import pytest

# Force mock mode before any app imports
os.environ["USE_MOCK_AI"] = "true"
os.environ["USE_MOCK_COMPILER"] = "true"

from app.agents.patch_agent import (
    _build_messages,
    _build_patch_metadata,
    _extract_source,
    _format_analysis,
    _format_errors,
    patch,
    PATCH_MODEL,
)
from app.models.compiler_error import CompilerError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ERRONEOUS_SOURCE = """\
#include <hip/hip_runtime.h>

__global__ void kernel(float* dst, float* src, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) dst[i] = src[i];
}

void transfer(float* dst, float* src, int n, hipStream_t s) {
    // KNOWN_ERROR: Using wrong API name
    hipMemcpyAsync_WRONG(dst, src, n * sizeof(float), hipMemcpyDeviceToDevice, s);
}
"""

CORRECTED_SOURCE = """\
#include <hip/hip_runtime.h>

__global__ void kernel(float* dst, float* src, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) dst[i] = src[i];
}

void transfer(float* dst, float* src, int n, hipStream_t s) {
    hipMemcpyAsync(dst, src, n * sizeof(float), hipMemcpyDeviceToDevice, s);
}
"""

SAMPLE_ANALYSIS = {
    "summary": "Compilation failed because hipMemcpyAsync_WRONG is not a valid HIP API.",
    "root_cause": "The function name hipMemcpyAsync_WRONG does not exist in the HIP runtime.",
    "affected_files": ["kernel.hip"],
    "affected_lines": [10],
    "confidence": 0.97,
    "repair_plan": [
        "Replace hipMemcpyAsync_WRONG with hipMemcpyAsync on line 10.",
        "Verify the stream parameter type is hipStream_t.",
    ],
}

SAMPLE_ERRORS = [
    CompilerError(
        file="kernel.hip", line=10, column=5,
        message="use of undeclared identifier 'hipMemcpyAsync_WRONG'",
        code="E0020",
    )
]


def _make_client(response_content: str):
    """Build a capturing client that returns response_content as AI output."""
    class ControlledClient:
        captured_messages = None

        def chat_completion(self, model, messages, max_tokens=2048):
            ControlledClient.captured_messages = messages
            return {
                "id": "patch-test-1",
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": response_content},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            }
    return ControlledClient()


# ---------------------------------------------------------------------------
# Test: prompt structure
# ---------------------------------------------------------------------------

class TestPromptStructure:
    """_build_messages must produce the correct 6-section prompt."""

    def test_produces_two_messages(self):
        msgs = _build_messages(ERRONEOUS_SOURCE, SAMPLE_ANALYSIS, SAMPLE_ERRORS, [], [])
        assert len(msgs) == 2

    def test_first_message_is_system(self):
        msgs = _build_messages(ERRONEOUS_SOURCE, SAMPLE_ANALYSIS, SAMPLE_ERRORS, [], [])
        assert msgs[0]["role"] == "system"

    def test_system_prompt_identifies_patch_agent(self):
        msgs = _build_messages(ERRONEOUS_SOURCE, SAMPLE_ANALYSIS, SAMPLE_ERRORS, [], [])
        assert "Patch Agent" in msgs[0]["content"]

    def test_system_prompt_instructs_minimal_patch(self):
        msgs = _build_messages(ERRONEOUS_SOURCE, SAMPLE_ANALYSIS, SAMPLE_ERRORS, [], [])
        assert "minimal" in msgs[0]["content"].lower() or "MINIMAL" in msgs[0]["content"]

    def test_system_prompt_instructs_no_extra_content(self):
        """System prompt must tell the model to return only source code."""
        msgs = _build_messages(ERRONEOUS_SOURCE, SAMPLE_ANALYSIS, SAMPLE_ERRORS, [], [])
        content = msgs[0]["content"]
        assert "ONLY" in content or "only" in content

    def test_second_message_is_user(self):
        msgs = _build_messages(ERRONEOUS_SOURCE, SAMPLE_ANALYSIS, SAMPLE_ERRORS, [], [])
        assert msgs[1]["role"] == "user"

    def test_user_message_has_all_six_sections(self):
        msgs = _build_messages(ERRONEOUS_SOURCE, SAMPLE_ANALYSIS, SAMPLE_ERRORS, [], [])
        content = msgs[1]["content"]
        assert "## 2. Current Task" in content
        assert "## 3. Source Code" in content
        assert "## 4. Compiler Diagnostics" in content
        assert "## 5. Migration Journal" in content
        assert "## 6. Expected Output" in content

    def test_source_code_embedded_in_prompt(self):
        msgs = _build_messages(ERRONEOUS_SOURCE, SAMPLE_ANALYSIS, SAMPLE_ERRORS, [], [])
        assert "hipMemcpyAsync_WRONG" in msgs[1]["content"]

    def test_repair_plan_embedded(self):
        msgs = _build_messages(ERRONEOUS_SOURCE, SAMPLE_ANALYSIS, SAMPLE_ERRORS, [], [])
        assert "hipMemcpyAsync" in msgs[1]["content"]

    def test_error_diagnostic_in_prompt(self):
        msgs = _build_messages(ERRONEOUS_SOURCE, SAMPLE_ANALYSIS, SAMPLE_ERRORS, [], [])
        assert "hipMemcpyAsync_WRONG" in msgs[1]["content"]
        assert "E0020" in msgs[1]["content"]

    def test_migration_journal_in_prompt(self):
        journal = [{"attempt": 1, "root_cause": "previous failure"}]
        msgs = _build_messages(ERRONEOUS_SOURCE, SAMPLE_ANALYSIS, SAMPLE_ERRORS, journal, [])
        assert "previous failure" in msgs[1]["content"]

    def test_previous_patches_in_prompt(self):
        msgs = _build_messages(
            ERRONEOUS_SOURCE, SAMPLE_ANALYSIS, SAMPLE_ERRORS, [],
            ["// prior attempt 1\n#include <hip/hip_runtime.h>\n"]
        )
        assert "prior attempt 1" in msgs[1]["content"]

    def test_no_prior_history_when_empty(self):
        msgs = _build_messages(ERRONEOUS_SOURCE, SAMPLE_ANALYSIS, SAMPLE_ERRORS, [], [])
        content = msgs[1]["content"]
        assert "no prior history" in content or "(none)" in content


# ---------------------------------------------------------------------------
# Test: _extract_source
# ---------------------------------------------------------------------------

class TestExtractSource:
    """_extract_source must return raw source code from various model outputs."""

    def test_returns_raw_source_unchanged(self):
        result = _extract_source(CORRECTED_SOURCE, ERRONEOUS_SOURCE)
        assert "hipMemcpyAsync" in result
        assert "hipMemcpyAsync_WRONG" not in result

    def test_strips_markdown_hip_fence(self):
        fenced = f"```hip\n{CORRECTED_SOURCE}\n```"
        result = _extract_source(fenced, ERRONEOUS_SOURCE)
        assert "hipMemcpyAsync" in result
        assert "```" not in result

    def test_strips_markdown_cpp_fence(self):
        fenced = f"```cpp\n{CORRECTED_SOURCE}\n```"
        result = _extract_source(fenced, ERRONEOUS_SOURCE)
        assert "```" not in result

    def test_strips_plain_fence(self):
        fenced = f"```\n{CORRECTED_SOURCE}\n```"
        result = _extract_source(fenced, ERRONEOUS_SOURCE)
        assert "```" not in result

    def test_raises_on_empty_response(self):
        with pytest.raises(ValueError, match="empty"):
            _extract_source("", ERRONEOUS_SOURCE)

    def test_raises_on_whitespace_only_response(self):
        with pytest.raises(ValueError, match="empty"):
            _extract_source("   \n\n   ", ERRONEOUS_SOURCE)


# ---------------------------------------------------------------------------
# Test: _build_patch_metadata
# ---------------------------------------------------------------------------

class TestBuildPatchMetadata:
    """_build_patch_metadata must produce spec-compliant metadata."""

    def test_has_required_fields(self):
        meta = _build_patch_metadata(ERRONEOUS_SOURCE, CORRECTED_SOURCE, "k.hip", SAMPLE_ANALYSIS)
        assert "summary" in meta
        assert "modified_files" in meta
        assert "changes" in meta

    def test_filename_in_modified_files(self):
        meta = _build_patch_metadata(ERRONEOUS_SOURCE, CORRECTED_SOURCE, "k.hip", SAMPLE_ANALYSIS)
        assert "k.hip" in meta["modified_files"]

    def test_changes_list_has_entries(self):
        meta = _build_patch_metadata(ERRONEOUS_SOURCE, CORRECTED_SOURCE, "k.hip", SAMPLE_ANALYSIS)
        assert len(meta["changes"]) >= 1

    def test_changed_lines_are_positive_integers(self):
        meta = _build_patch_metadata(ERRONEOUS_SOURCE, CORRECTED_SOURCE, "k.hip", SAMPLE_ANALYSIS)
        for line_num in meta["changes"][0]["lines"]:
            assert isinstance(line_num, int)
            assert line_num >= 1

    def test_unchanged_source_has_no_changed_lines(self):
        meta = _build_patch_metadata(CORRECTED_SOURCE, CORRECTED_SOURCE, "k.hip", SAMPLE_ANALYSIS)
        assert meta["changes"][0]["lines"] == []


# ---------------------------------------------------------------------------
# Gate test: patch() returns corrected source, known error is absent
# ---------------------------------------------------------------------------

class TestPatch:
    """Gate: patch() returns corrected source, known error is absent."""

    def test_returns_string(self, monkeypatch):
        monkeypatch.setattr(
            "app.agents.patch_agent.get_ai_client",
            lambda: _make_client(CORRECTED_SOURCE)
        )
        result = patch(
            source_code=ERRONEOUS_SOURCE,
            analysis=SAMPLE_ANALYSIS,
            compiler_errors=SAMPLE_ERRORS,
        )
        assert isinstance(result, str)

    def test_known_error_absent_in_output(self, monkeypatch):
        """Gate: the targeted error token must not appear in the patched source."""
        monkeypatch.setattr(
            "app.agents.patch_agent.get_ai_client",
            lambda: _make_client(CORRECTED_SOURCE)
        )
        result = patch(
            source_code=ERRONEOUS_SOURCE,
            analysis=SAMPLE_ANALYSIS,
            compiler_errors=SAMPLE_ERRORS,
        )
        # The wrong API name should be absent from the corrected output
        assert "hipMemcpyAsync_WRONG" not in result, (
            "Patched source still contains the known error 'hipMemcpyAsync_WRONG'"
        )

    def test_corrected_api_present_in_output(self, monkeypatch):
        """Gate: the correct API replacement must appear in the patched output."""
        monkeypatch.setattr(
            "app.agents.patch_agent.get_ai_client",
            lambda: _make_client(CORRECTED_SOURCE)
        )
        result = patch(
            source_code=ERRONEOUS_SOURCE,
            analysis=SAMPLE_ANALYSIS,
            compiler_errors=SAMPLE_ERRORS,
        )
        assert "hipMemcpyAsync" in result

    def test_returns_full_file_not_fragment(self, monkeypatch):
        """Output must be a complete source file (includes includes + kernel)."""
        monkeypatch.setattr(
            "app.agents.patch_agent.get_ai_client",
            lambda: _make_client(CORRECTED_SOURCE)
        )
        result = patch(
            source_code=ERRONEOUS_SOURCE,
            analysis=SAMPLE_ANALYSIS,
            compiler_errors=SAMPLE_ERRORS,
        )
        assert "#include" in result
        assert "__global__" in result
        assert "void kernel" in result

    def test_uses_patch_model(self, monkeypatch):
        """Verify that PATCH_MODEL is sent to chat_completion."""
        client = _make_client(CORRECTED_SOURCE)
        captured_model = {}

        original_cc = client.chat_completion
        def capturing_cc(model, messages, max_tokens=2048):
            captured_model["value"] = model
            return original_cc(model, messages, max_tokens)
        client.chat_completion = capturing_cc

        monkeypatch.setattr("app.agents.patch_agent.get_ai_client", lambda: client)
        patch(source_code=ERRONEOUS_SOURCE, analysis=SAMPLE_ANALYSIS)
        assert captured_model["value"] == PATCH_MODEL

    def test_strips_code_fence_from_model_response(self, monkeypatch):
        """patch() must strip markdown fences if model wraps source in them."""
        fenced_correct = f"```hip\n{CORRECTED_SOURCE}\n```"
        monkeypatch.setattr(
            "app.agents.patch_agent.get_ai_client",
            lambda: _make_client(fenced_correct)
        )
        result = patch(
            source_code=ERRONEOUS_SOURCE,
            analysis=SAMPLE_ANALYSIS,
            compiler_errors=SAMPLE_ERRORS,
        )
        assert "```" not in result
        assert "hipMemcpyAsync_WRONG" not in result

    def test_prompt_sections_sent_to_model(self, monkeypatch):
        """All 6 prompt sections must reach the model."""
        client = _make_client(CORRECTED_SOURCE)
        monkeypatch.setattr("app.agents.patch_agent.get_ai_client", lambda: client)
        patch(source_code=ERRONEOUS_SOURCE, analysis=SAMPLE_ANALYSIS,
              compiler_errors=SAMPLE_ERRORS)
        msgs = client.__class__.captured_messages
        user_content = msgs[1]["content"]
        for section in ["## 2. Current Task", "## 3. Source Code",
                        "## 4. Compiler Diagnostics", "## 5. Migration Journal",
                        "## 6. Expected Output"]:
            assert section in user_content, f"Missing section: {section}"

    def test_raises_on_empty_response(self, monkeypatch):
        monkeypatch.setattr(
            "app.agents.patch_agent.get_ai_client",
            lambda: _make_client("")
        )
        with pytest.raises(ValueError, match="empty"):
            patch(source_code=ERRONEOUS_SOURCE, analysis=SAMPLE_ANALYSIS)


# ---------------------------------------------------------------------------
# Test: handle_patching workflow state integration
# ---------------------------------------------------------------------------

class TestHandlePatching:
    """handle_patching must call patch() and write the corrected file to disk."""

    def _make_ctx(self, tmp_path, source: str = ERRONEOUS_SOURCE):
        from app.workflow_engine.context import WorkflowContext
        ws = tmp_path / "ws"
        for d in ("input", "generated", "patches", "logs", "artifacts"):
            (ws / d).mkdir(parents=True)
        # Write source to generated/ directory
        hip_file = ws / "generated" / "kernel.hip"
        hip_file.write_text(source, encoding="utf-8")

        ctx = WorkflowContext(
            migration_id="migration_20260701_000000_patch",
            workspace_path=str(ws),
        )
        ctx.hipify_output_path = str(hip_file)
        ctx.analysis_result = SAMPLE_ANALYSIS
        ctx.compiler_errors = SAMPLE_ERRORS
        return ctx, ws

    @pytest.mark.asyncio
    async def test_returns_compiling(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.agents.patch_agent.get_ai_client",
            lambda: _make_client(CORRECTED_SOURCE)
        )
        from app.workflow_engine.states import handle_patching
        ctx, _ = self._make_ctx(tmp_path)
        result = await handle_patching(ctx)
        assert result == "COMPILING"

    @pytest.mark.asyncio
    async def test_writes_patch_file_to_workspace(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.agents.patch_agent.get_ai_client",
            lambda: _make_client(CORRECTED_SOURCE)
        )
        from app.workflow_engine.states import handle_patching
        ctx, ws = self._make_ctx(tmp_path)
        await handle_patching(ctx)
        patch_files = list((ws / "patches").glob("patch_attempt_*.hip"))
        assert len(patch_files) == 1, f"Expected 1 patch file, got: {patch_files}"

    @pytest.mark.asyncio
    async def test_patch_file_content_lacks_known_error(self, tmp_path, monkeypatch):
        """Gate: written patch file must not contain the known error."""
        monkeypatch.setattr(
            "app.agents.patch_agent.get_ai_client",
            lambda: _make_client(CORRECTED_SOURCE)
        )
        from app.workflow_engine.states import handle_patching
        ctx, ws = self._make_ctx(tmp_path)
        await handle_patching(ctx)
        patch_files = list((ws / "patches").glob("patch_attempt_*.hip"))
        content = patch_files[0].read_text(encoding="utf-8")
        assert "hipMemcpyAsync_WRONG" not in content

    @pytest.mark.asyncio
    async def test_updates_hipify_output_path(self, tmp_path, monkeypatch):
        """handle_patching must update hipify_output_path for next COMPILING."""
        monkeypatch.setattr(
            "app.agents.patch_agent.get_ai_client",
            lambda: _make_client(CORRECTED_SOURCE)
        )
        from app.workflow_engine.states import handle_patching
        ctx, ws = self._make_ctx(tmp_path)
        original_path = ctx.hipify_output_path
        await handle_patching(ctx)
        assert ctx.hipify_output_path != original_path, (
            "hipify_output_path must be updated to the new patch file"
        )
        assert "patch_attempt" in ctx.hipify_output_path

    @pytest.mark.asyncio
    async def test_sets_patched_source_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.agents.patch_agent.get_ai_client",
            lambda: _make_client(CORRECTED_SOURCE)
        )
        from app.workflow_engine.states import handle_patching
        ctx, ws = self._make_ctx(tmp_path)
        await handle_patching(ctx)
        assert ctx.patched_source_path is not None
        assert Path(ctx.patched_source_path).exists()

    @pytest.mark.asyncio
    async def test_increments_current_attempt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.agents.patch_agent.get_ai_client",
            lambda: _make_client(CORRECTED_SOURCE)
        )
        from app.workflow_engine.states import handle_patching
        ctx, ws = self._make_ctx(tmp_path)
        assert ctx.current_attempt == 0
        await handle_patching(ctx)
        assert ctx.current_attempt == 1

    @pytest.mark.asyncio
    async def test_appends_to_patch_history(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.agents.patch_agent.get_ai_client",
            lambda: _make_client(CORRECTED_SOURCE)
        )
        from app.workflow_engine.states import handle_patching
        ctx, ws = self._make_ctx(tmp_path)
        assert len(ctx.patch_history) == 0
        await handle_patching(ctx)
        assert len(ctx.patch_history) == 1
        assert "hipMemcpyAsync" in ctx.patch_history[0]

    @pytest.mark.asyncio
    async def test_raises_on_missing_source_file(self, tmp_path):
        """handle_patching must raise RuntimeError when source path is empty."""
        from app.workflow_engine.context import WorkflowContext
        from app.workflow_engine.states import handle_patching
        ctx = WorkflowContext(
            migration_id="migration_20260701_000000_empty",
            workspace_path=str(tmp_path),
        )
        # hipify_output_path is None → no source
        with pytest.raises(RuntimeError, match="PATCHING"):
            await handle_patching(ctx)
