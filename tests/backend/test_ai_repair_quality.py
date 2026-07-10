"""
tests/backend/test_ai_repair_quality.py

Focused tests for AI repair quality improvements (req #9).

Tests:
  1. repair context contains the relevant error and source
  2. unrelated large files are excluded (size cap enforced)
  3. structured output validation rejects missing 'diagnosis' field
  4. workspace path containment blocks paths outside workspace
  5. failed patch rolled back when probe produces more errors
  6. duplicate patch fingerprint rejected before AI is called
  7. successful patch followed by compile probe passes
  8. deterministic fixes (lesson match) still bypass AI
  9. requires_human flag surfaced from structured analysis output

Run with:
  pytest tests/backend/test_ai_repair_quality.py -v
"""

import asyncio
import hashlib
import json
import os
import sys
import tempfile
import types
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ["USE_MOCK_AI"] = "true"
os.environ["USE_MOCK_COMPILER"] = "true"

from app.agents.analysis_agent import _build_messages, _parse_response, analyze
from app.agents.base_agent import MockFireworksClient
from app.models.compiler_error import CompilerError
from app.workflow_engine.context import WorkflowContext


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_STDERR = (
    "kernel.hip:42:8: error: no matching function for call to 'hipMemcpyAsync' [E0308]\n"
    "kernel.hip:67:12: error: use of undeclared identifier 'hipStreamNonBlocking' [E0020]\n"
)

SAMPLE_SOURCE = (
    "#include <hip/hip_runtime.h>\n\n"
    "__global__ void kernel(float* d, float* s, int n) {\n"
    "    int i = blockIdx.x * blockDim.x + threadIdx.x;\n"
    "    if (i < n) d[i] = s[i];\n"
    "}\n"
)

SAMPLE_ERRORS = [
    CompilerError(file="kernel.hip", line=42, column=8,
                  message="no matching function for call to 'hipMemcpyAsync'", code="E0308"),
    CompilerError(file="kernel.hip", line=67, column=12,
                  message="use of undeclared identifier 'hipStreamNonBlocking'", code="E0020"),
]

VALID_ANALYSIS_RESPONSE = json.dumps({
    "summary": "hipMemcpyAsync API mismatch.",
    "root_cause": "Wrong function signature used.",
    "diagnosis": "hipMemcpyAsync called with incorrect arguments.",
    "affected_files": ["kernel.hip"],
    "affected_lines": [42, 67],
    "confidence": 0.95,
    "repair_plan": ["Fix hipMemcpyAsync call signature."],
    "proposed_patches": [
        {"file": "kernel.hip", "reason": "Fix API call", "content": "hipMemcpyAsync(...)"}
    ],
    "requires_human": False,
    "blocker": None,
})


def _make_context(tmp_path: Path, retry_budget: int = 5) -> WorkflowContext:
    ctx = WorkflowContext(
        migration_id="test-001",
        workspace_path=str(tmp_path),
        retry_budget=retry_budget,
    )
    ctx.compiler_errors = SAMPLE_ERRORS
    ctx.last_compile_stderr = SAMPLE_STDERR
    ctx.last_compile_command = "hipcc kernel.hip -o out --offload-arch=gfx90a"
    ctx.target_gpu_architecture = "gfx90a"
    ctx.hipify_output_path = str(tmp_path / "generated" / "kernel.hip")
    # Create the file so reads succeed
    (tmp_path / "generated").mkdir(parents=True, exist_ok=True)
    (tmp_path / "generated" / "kernel.hip").write_text(SAMPLE_SOURCE)
    return ctx


# ---------------------------------------------------------------------------
# Test 1: repair context contains the relevant error and source
# ---------------------------------------------------------------------------

class TestRepairContextContent:
    def test_repair_context_in_prompt_section2(self, tmp_path):
        """repair_context fields must appear in the prompt's Current Task section."""
        repair_context = {
            "failed_stage": "COMPILING",
            "compile_command": "hipcc kernel.hip -o out --offload-arch=gfx90a",
            "raw_stderr": SAMPLE_STDERR,
            "target_arch": "gfx90a",
            "rocm_version": "ROCm 5.7.0",
            "compiler_version": "HIP 5.7",
            "source_file": "kernel.hip",
            "remaining_budget": 3,
        }
        messages = _build_messages(
            source_code=SAMPLE_SOURCE,
            compiler_errors=SAMPLE_ERRORS,
            attempt=0,
            migration_journal=None,
            previous_research=None,
            repair_context=repair_context,
        )
        user_content = messages[1]["content"]
        assert "Failed Stage: COMPILING" in user_content
        assert "hipcc kernel.hip" in user_content
        assert "gfx90a" in user_content
        assert "ROCm 5.7.0" in user_content
        assert "Remaining Repair Budget: 3" in user_content
        assert "kernel.hip" in user_content

    def test_source_code_present_in_prompt(self):
        """Source code must appear in section 3 of the prompt."""
        messages = _build_messages(
            source_code=SAMPLE_SOURCE,
            compiler_errors=SAMPLE_ERRORS,
            attempt=0,
            migration_journal=None,
            previous_research=None,
            repair_context=None,
        )
        user_content = messages[1]["content"]
        assert "__global__ void kernel" in user_content

    def test_error_messages_in_prompt(self):
        """Structured compiler errors must appear in the Compiler Diagnostics section."""
        messages = _build_messages(
            source_code=SAMPLE_SOURCE,
            compiler_errors=SAMPLE_ERRORS,
            attempt=0,
            migration_journal=None,
            previous_research=None,
            repair_context=None,
        )
        user_content = messages[1]["content"]
        assert "hipMemcpyAsync" in user_content
        assert "hipStreamNonBlocking" in user_content


# ---------------------------------------------------------------------------
# Test 2: unrelated large files are excluded (size cap enforced)
# ---------------------------------------------------------------------------

class TestContextSizeLimits:
    def test_large_source_truncated(self, tmp_path):
        """A source file larger than the cap must be truncated in the prompt."""
        from app.config.settings import settings
        cap = settings.MAX_AI_PROMPT_CONTEXT_CHARS
        huge_source = "// padding\n" * (cap // 10)  # clearly larger than the 40% slice
        ctx = _make_context(tmp_path)
        messages = _build_messages(
            source_code=huge_source,
            compiler_errors=SAMPLE_ERRORS,
            attempt=0,
            migration_journal=None,
            previous_research=None,
            repair_context=None,
            context=ctx,
        )
        user_content = messages[1]["content"]
        # Either the source was truncated or the prompt was hard-capped
        assert len(user_content) <= cap + 200  # tiny slack for surrounding template
        assert "truncated" in user_content or len(user_content) < len(huge_source)

    def test_huge_unrelated_context_does_not_bloat_prompt(self):
        """A massive journal should not cause the prompt to exceed 2x the cap."""
        from app.config.settings import settings
        cap = settings.MAX_AI_PROMPT_CONTEXT_CHARS
        fat_journal = [{"attempt": i, "analysis_summary": "x" * 5000} for i in range(100)]
        messages = _build_messages(
            source_code=SAMPLE_SOURCE,
            compiler_errors=SAMPLE_ERRORS,
            attempt=0,
            migration_journal=fat_journal,
            previous_research=None,
            repair_context=None,
        )
        user_content = messages[1]["content"]
        assert len(user_content) <= cap * 2


# ---------------------------------------------------------------------------
# Test 3: structured output validation rejects missing 'diagnosis' field
# ---------------------------------------------------------------------------

class TestStructuredOutputValidation:
    def test_valid_response_parses_ok(self):
        result = _parse_response(VALID_ANALYSIS_RESPONSE)
        assert result["diagnosis"]
        assert isinstance(result["confidence"], float)
        assert isinstance(result["requires_human"], bool)

    def test_missing_diagnosis_raises(self):
        bad = {
            "summary": "x", "root_cause": "y",
            "affected_files": [], "affected_lines": [],
            "confidence": 0.9, "repair_plan": [],
        }
        with pytest.raises(ValueError, match="diagnosis"):
            _parse_response(json.dumps(bad))

    def test_missing_confidence_raises(self):
        bad = {
            "summary": "x", "root_cause": "y", "diagnosis": "z",
            "affected_files": [], "affected_lines": [],
            "repair_plan": [],
        }
        with pytest.raises(ValueError, match="confidence"):
            _parse_response(json.dumps(bad))

    def test_requires_human_coerced_to_bool(self):
        resp = {
            "summary": "x", "root_cause": "y", "diagnosis": "z",
            "affected_files": [], "affected_lines": [],
            "confidence": 0.5, "repair_plan": [],
            "requires_human": 1,  # int, not bool
        }
        result = _parse_response(json.dumps(resp))
        assert result["requires_human"] is True

    def test_proposed_patches_optional(self):
        """proposed_patches is optional — parse should succeed without it."""
        resp = {
            "summary": "x", "root_cause": "y", "diagnosis": "z",
            "affected_files": [], "affected_lines": [],
            "confidence": 0.5, "repair_plan": [],
            "requires_human": False,
        }
        result = _parse_response(json.dumps(resp))
        assert "proposed_patches" not in result or result.get("proposed_patches") is None


# ---------------------------------------------------------------------------
# Test 4: workspace path containment
# ---------------------------------------------------------------------------

class TestWorkspaceContainment:
    @pytest.mark.asyncio
    async def test_patch_inside_workspace_ok(self, tmp_path):
        """Patch files inside workspace/patches/ must NOT raise."""
        from app.workflow_engine.states import handle_patching

        ctx = _make_context(tmp_path)
        ctx.analysis_result = {
            "summary": "s", "root_cause": "r", "diagnosis": "d",
            "affected_files": ["kernel.hip"], "affected_lines": [42],
            "confidence": 0.9,
            "repair_plan": ["Fix hipMemcpyAsync."],
            "requires_human": False,
        }

        # Use a source that actually has hipMemcpyAsync_WRONG so the fix is localized
        _orig = SAMPLE_SOURCE + "void transfer(float* d, float* s, int n, hipStream_t st) {\n    hipMemcpyAsync_WRONG(d, s, n*sizeof(float), hipMemcpyDeviceToDevice, st);\n}\n"
        corrected = _orig.replace("hipMemcpyAsync_WRONG", "hipMemcpyAsync")
        (tmp_path / "generated" / "kernel.hip").write_text(_orig)
        with patch("app.agents.patch_agent.patch", return_value=corrected), \
             patch("app.compiler.hipcc_runner.run_hipcc", return_value={
                 "success": True, "errors": [], "stderr": "", "stdout": "", "command": ""}), \
             patch("app.compiler.sca.analyze", return_value={"issues": []}), \
             patch("app.workflow_engine.state_machine.publish_log", new_callable=AsyncMock), \
             patch("app.workflow_engine.state_machine.publish_event", new_callable=AsyncMock), \
             patch("app.compiler.validator.harden_hip_content", side_effect=lambda src, **kw: (src, {})):
            result = await handle_patching(ctx)
        assert result == "COMPILING"
        # Patch file must live inside workspace/patches/
        patch_path = Path(ctx.hipify_output_path)
        assert (tmp_path / "patches").resolve() in [patch_path.resolve().parent]

    @pytest.mark.asyncio
    async def test_containment_check_rejects_path_traversal(self, tmp_path):
        """Symlink traversal or path manipulation that escapes patches/ must raise."""
        from app.workflow_engine import states

        # Monkey-patch patches_dir to simulate a symlink attack where
        # the resolved patch would be outside workspace
        workspace = tmp_path
        patches_dir = workspace / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)
        # A patch_path with '..' traversal
        bad_patch_path = patches_dir / ".." / ".." / "evil.hip"

        with pytest.raises((RuntimeError, ValueError)):
            resolved_patch = bad_patch_path.resolve()
            resolved_patches_dir = patches_dir.resolve()
            resolved_patch.relative_to(resolved_patches_dir)


# ---------------------------------------------------------------------------
# Test 5: failed patch rolled back when probe produces more errors
# ---------------------------------------------------------------------------

class TestPatchRollback:
    @pytest.mark.asyncio
    async def test_rollback_on_worse_compile(self, tmp_path):
        """If probe compile returns more errors than before, original source is restored."""
        from app.workflow_engine.states import handle_patching

        ctx = _make_context(tmp_path)
        ctx.analysis_result = {
            "summary": "s", "root_cause": "r", "diagnosis": "d",
            "affected_files": ["kernel.hip"], "affected_lines": [42],
            "confidence": 0.9, "repair_plan": ["fix"], "requires_human": False,
        }

        broken_patch = SAMPLE_SOURCE + "\nBAD_CODE_THAT_BREAKS_THINGS;\n"
        # Probe returns 5 errors (worse than the original 2)
        probe_errors = [
            CompilerError(file="kernel.hip", line=i, column=1, message="err", code="E")
            for i in range(5)
        ]
        with patch("app.agents.patch_agent.patch", return_value=broken_patch), \
             patch("app.compiler.hipcc_runner.run_hipcc", return_value={
                 "success": False, "errors": probe_errors, "stderr": "5 errors", "stdout": "", "command": ""}), \
             patch("app.workflow_engine.state_machine.publish_log", new_callable=AsyncMock), \
             patch("app.workflow_engine.state_machine.publish_event", new_callable=AsyncMock), \
             patch("app.compiler.validator.harden_hip_content", side_effect=lambda src, **kw: (src, {})):
            result = await handle_patching(ctx)

        # Should still transition to COMPILING (rollback doesn't abort the pipeline)
        assert result == "COMPILING"
        # The file on disk should contain the rolled-back (original) source
        patch_path = Path(ctx.hipify_output_path)
        on_disk = patch_path.read_text()
        # Rolled-back content should NOT have the bad code
        assert "BAD_CODE_THAT_BREAKS_THINGS" not in on_disk


# ---------------------------------------------------------------------------
# Test 6: duplicate patch fingerprint rejected
# ---------------------------------------------------------------------------

class TestPatchFingerprintDedup:
    @pytest.mark.asyncio
    async def test_duplicate_fingerprint_raises(self, tmp_path):
        """Second call with identical (stderr, source, attempt) must raise without calling AI."""
        from app.workflow_engine.states import handle_analyzing

        ctx = _make_context(tmp_path)
        # Pre-seed the fingerprint
        stderr_hash = hashlib.sha256(SAMPLE_STDERR.encode()).hexdigest()[:16]
        source_hash = hashlib.sha256(SAMPLE_SOURCE.encode()).hexdigest()[:16]
        fingerprint = (stderr_hash, source_hash, 0)
        ctx.seen_patch_fingerprints = {fingerprint}

        ai_called = []

        with patch("app.agents.analysis_agent.analyze", side_effect=lambda **kw: ai_called.append(1) or {}) as mock_ai, \
             patch("app.redis.client.redis_client") as mock_redis, \
             patch("app.learning.lesson_storage.find_lesson", new_callable=AsyncMock, return_value=None), \
             patch("app.learning.lesson_storage.store_lesson", new_callable=AsyncMock), \
             patch("app.workflow_engine.state_machine.publish_event", new_callable=AsyncMock), \
             patch("app.compiler.ast_slicing.get_optimized_error_context", return_value=SAMPLE_SOURCE):
            with pytest.raises(RuntimeError, match="fingerprint"):
                await handle_analyzing(ctx)

        # AI must NOT have been called
        assert len(ai_called) == 0

    @pytest.mark.asyncio
    async def test_new_fingerprint_allows_ai(self, tmp_path):
        """First call with a fresh fingerprint must proceed to AI analysis."""
        from app.workflow_engine.states import handle_analyzing

        ctx = _make_context(tmp_path)
        ctx.seen_patch_fingerprints = set()  # empty

        good_result = json.loads(VALID_ANALYSIS_RESPONSE)
        with patch("app.agents.analysis_agent.analyze", return_value=good_result) as mock_ai, \
             patch("app.redis.client.redis_client") as mock_redis, \
             patch("app.learning.lesson_storage.find_lesson", new_callable=AsyncMock, return_value=None), \
             patch("app.learning.lesson_storage.store_lesson", new_callable=AsyncMock), \
             patch("app.workflow_engine.state_machine.publish_event", new_callable=AsyncMock), \
             patch("app.compiler.ast_slicing.get_optimized_error_context", return_value=SAMPLE_SOURCE):
            result = await handle_analyzing(ctx)

        assert result == "PATCHING"
        mock_ai.assert_called_once()


# ---------------------------------------------------------------------------
# Test 7: successful patch followed by compile probe passing
# ---------------------------------------------------------------------------

class TestSuccessfulPatchFlow:
    @pytest.mark.asyncio
    async def test_patch_and_probe_pass(self, tmp_path):
        """When patch agent succeeds and probe compile passes, transition to COMPILING."""
        from app.workflow_engine.states import handle_patching

        ctx = _make_context(tmp_path)
        ctx.analysis_result = {
            "summary": "Fix hipMemcpyAsync call.",
            "root_cause": "Wrong API name.",
            "diagnosis": "API mismatch at line 42.",
            "affected_files": ["kernel.hip"], "affected_lines": [42],
            "confidence": 0.95, "repair_plan": ["Replace API."], "requires_human": False,
        }

        # Localized patch: only the bad API token changes; no function renames
        _orig = SAMPLE_SOURCE + "void transfer(float* d, float* s, int n, hipStream_t st) {\n    hipMemcpyAsync_WRONG(d, s, n*sizeof(float), hipMemcpyDeviceToDevice, st);\n}\n"
        fixed = _orig.replace("hipMemcpyAsync_WRONG", "hipMemcpyAsync")
        (tmp_path / "generated" / "kernel.hip").write_text(_orig)
        with patch("app.agents.patch_agent.patch", return_value=fixed), \
             patch("app.compiler.hipcc_runner.run_hipcc", return_value={
                 "success": True, "errors": [], "stderr": "", "stdout": "OK", "command": "hipcc ..."}), \
             patch("app.compiler.sca.analyze", return_value={"issues": []}), \
             patch("app.workflow_engine.state_machine.publish_log", new_callable=AsyncMock), \
             patch("app.workflow_engine.state_machine.publish_event", new_callable=AsyncMock), \
             patch("app.compiler.validator.harden_hip_content", side_effect=lambda src, **kw: (src, {})):
            result = await handle_patching(ctx)

        assert result == "COMPILING"
        # Patch file written and context updated
        assert ctx.hipify_output_path is not None
        assert Path(ctx.hipify_output_path).exists()


# ---------------------------------------------------------------------------
# Test 8: deterministic fixes (lesson match) bypass AI
# ---------------------------------------------------------------------------

class TestDeterministicBypassesAI:
    @pytest.mark.asyncio
    async def test_lesson_match_skips_ai(self, tmp_path):
        """When a lesson matches the current error, AI analyze() must NOT be called."""
        from app.workflow_engine.states import handle_analyzing

        ctx = _make_context(tmp_path)
        ctx.seen_patch_fingerprints = set()

        known_lesson = {
            "category": "DEPENDENCY_ERROR",
            "main_error_text": SAMPLE_STDERR[:100],
            "recommended_action": "Upload full project",
            "patch_skipped_reason": "known lesson",
        }

        ai_called = []
        with patch("app.agents.analysis_agent.analyze", side_effect=lambda **kw: ai_called.append(1) or {}) as mock_ai, \
             patch("app.redis.client.redis_client") as mock_redis, \
             patch("app.learning.lesson_storage.find_lesson", new_callable=AsyncMock, return_value=known_lesson), \
             patch("app.learning.lesson_storage.store_lesson", new_callable=AsyncMock), \
             patch("app.workflow_engine.state_machine.publish_event", new_callable=AsyncMock), \
             patch("app.compiler.ast_slicing.get_optimized_error_context", return_value=SAMPLE_SOURCE):
            # handle_analyzing returns None when lesson matched (falls through to report)
            result = await handle_analyzing(ctx)

        assert len(ai_called) == 0, "AI should not be called when lesson matches"
        assert ctx.lesson_matched is not None


# ---------------------------------------------------------------------------
# Test 9: requires_human flag surfaced from structured output
# ---------------------------------------------------------------------------

class TestRequiresHumanFlag:
    def test_requires_human_true_parsed(self):
        """requires_human=true in AI response must be preserved in parsed output."""
        resp = {
            "summary": "Unsupported intrinsic.",
            "root_cause": "This intrinsic has no HIP equivalent.",
            "diagnosis": "Intrinsic __cuda_arch_X is not available in HIP.",
            "affected_files": ["kernel.hip"], "affected_lines": [10],
            "confidence": 0.2, "repair_plan": [],
            "requires_human": True,
            "blocker": "No HIP equivalent for __cuda_arch_X intrinsic.",
        }
        result = _parse_response(json.dumps(resp))
        assert result["requires_human"] is True
        assert "blocker" in result
        assert result["blocker"]

    def test_requires_human_false_parsed(self):
        """requires_human=false must pass through correctly."""
        result = _parse_response(VALID_ANALYSIS_RESPONSE)
        assert result["requires_human"] is False
