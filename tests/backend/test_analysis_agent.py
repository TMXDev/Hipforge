"""
tests/backend/test_analysis_agent.py

Unit tests for the Analysis Agent (Session 9.2).

Verifies:
  - analyze() uses the correct 6-section prompt structure
  - Returns structured diagnosis matching docs/09_AI_AGENTS.md schema
  - handle_analyzing() wires correctly into the Workflow Engine state
  - Migration Journal is updated after each analysis
  - Invalid AI responses raise ValueError

Gate: Analysis Agent returns structured diagnosis for a real compiler error.
      pytest tests/backend/test_analysis_agent.py -v
"""

import json
import os

import pytest

# Force mock mode before any app imports
os.environ["USE_MOCK_AI"] = "true"
os.environ["USE_MOCK_COMPILER"] = "true"

from app.agents.analysis_agent import (
    _build_messages,
    _parse_response,
    analyze,
    ANALYSIS_MODEL,
    _SYSTEM_PROMPT,
    _EXPECTED_SCHEMA,
)
from app.models.compiler_error import CompilerError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_errors():
    """Two realistic CompilerError objects representing a hipcc failure."""
    return [
        CompilerError(
            file="kernel.hip",
            line=42,
            column=8,
            message="no matching function for call to 'hipMemcpyAsync'",
            code="E0308",
        ),
        CompilerError(
            file="kernel.hip",
            line=67,
            column=12,
            message="use of undeclared identifier 'hipStreamNonBlocking'",
            code="E0020",
        ),
    ]


@pytest.fixture()
def sample_source():
    return (
        "#include <hip/hip_runtime.h>\n\n"
        "__global__ void kernel(float* dst, float* src, int n) {\n"
        "    int i = blockIdx.x * blockDim.x + threadIdx.x;\n"
        "    if (i < n) dst[i] = src[i];\n"
        "}\n\n"
        "void transfer(float* dst, float* src, int n, hipStream_t s) {\n"
        "    hipMemcpyAsync(dst, src, n * sizeof(float), hipMemcpyDeviceToDevice, s);\n"
        "}\n"
    )


# ---------------------------------------------------------------------------
# Test: prompt structure
# ---------------------------------------------------------------------------

class TestPromptStructure:
    """_build_messages must produce the correct 6-section prompt."""

    def test_produces_two_messages(self, sample_errors, sample_source):
        msgs = _build_messages(sample_source, sample_errors, 0, None, None)
        assert len(msgs) == 2

    def test_first_message_is_system(self, sample_errors, sample_source):
        msgs = _build_messages(sample_source, sample_errors, 0, None, None)
        assert msgs[0]["role"] == "system"

    def test_system_prompt_contains_analysis_agent_identity(self, sample_errors, sample_source):
        msgs = _build_messages(sample_source, sample_errors, 0, None, None)
        assert "Analysis Agent" in msgs[0]["content"]
        assert "root cause" in msgs[0]["content"]

    def test_second_message_is_user(self, sample_errors, sample_source):
        msgs = _build_messages(sample_source, sample_errors, 0, None, None)
        assert msgs[1]["role"] == "user"

    def test_user_message_contains_all_six_sections(self, sample_errors, sample_source):
        msgs = _build_messages(sample_source, sample_errors, 0, [], None)
        content = msgs[1]["content"]
        assert "## 2. Current Task" in content
        assert "## 3. Source Code" in content
        assert "## 4. Compiler Diagnostics" in content
        assert "## 5. Migration Journal" in content
        assert "## 6. Expected JSON Schema" in content

    def test_source_code_in_user_message(self, sample_errors, sample_source):
        msgs = _build_messages(sample_source, sample_errors, 0, None, None)
        assert "hipMemcpyAsync" in msgs[1]["content"]

    def test_error_file_and_line_in_user_message(self, sample_errors, sample_source):
        msgs = _build_messages(sample_source, sample_errors, 0, None, None)
        content = msgs[1]["content"]
        assert "kernel.hip" in content
        assert "42" in content

    def test_attempt_number_in_user_message(self, sample_errors, sample_source):
        msgs = _build_messages(sample_source, sample_errors, 2, None, None)
        assert "attempt #3" in msgs[1]["content"]

    def test_migration_journal_included(self, sample_errors, sample_source):
        journal = [{"attempt": 1, "root_cause": "previous error"}]
        msgs = _build_messages(sample_source, sample_errors, 1, journal, None)
        assert "previous error" in msgs[1]["content"]

    def test_expected_schema_in_user_message(self, sample_errors, sample_source):
        msgs = _build_messages(sample_source, sample_errors, 0, None, None)
        assert "repair_plan" in msgs[1]["content"]
        assert "root_cause" in msgs[1]["content"]

    def test_previous_research_included_when_provided(self, sample_errors, sample_source):
        msgs = _build_messages(
            sample_source, sample_errors, 1, None,
            "ROCm docs say use hipMemcpyWithStream"
        )
        assert "ROCm docs" in msgs[1]["content"]
        assert "Previous Research" in msgs[1]["content"]

    def test_no_research_section_when_none(self, sample_errors, sample_source):
        msgs = _build_messages(sample_source, sample_errors, 0, None, None)
        assert "Previous Research" not in msgs[1]["content"]


# ---------------------------------------------------------------------------
# Test: response parsing
# ---------------------------------------------------------------------------

class TestParseResponse:
    """_parse_response must correctly extract the structured output."""

    def _valid_json(self):
        return json.dumps({
            "summary": "Compilation failed due to missing API.",
            "root_cause": "hipMemcpyAsync stream parameter type mismatch.",
            "affected_files": ["kernel.hip"],
            "affected_lines": [42, 67],
            "confidence": 0.92,
            "repair_plan": ["Replace with hipMemcpyWithStream.", "Upgrade ROCm."],
        })

    def test_parses_raw_json(self):
        result = _parse_response(self._valid_json())
        assert result["summary"]
        assert result["root_cause"]
        assert isinstance(result["affected_files"], list)
        assert isinstance(result["affected_lines"], list)
        assert isinstance(result["confidence"], float)
        assert isinstance(result["repair_plan"], list)

    def test_strips_markdown_fences(self):
        fenced = f"```json\n{self._valid_json()}\n```"
        result = _parse_response(fenced)
        assert result["summary"]

    def test_strips_plain_code_fences(self):
        fenced = f"```\n{self._valid_json()}\n```"
        result = _parse_response(fenced)
        assert result["root_cause"]

    def test_raises_on_invalid_json(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            _parse_response("not valid json at all")

    def test_raises_on_missing_required_fields(self):
        partial = json.dumps({"summary": "ok", "root_cause": "something"})
        with pytest.raises(ValueError, match="missing required fields"):
            _parse_response(partial)

    def test_raises_on_empty_string(self):
        with pytest.raises(ValueError):
            _parse_response("")

    def test_all_required_fields_present(self):
        result = _parse_response(self._valid_json())
        for field in ("summary", "root_cause", "affected_files", "affected_lines",
                      "confidence", "repair_plan"):
            assert field in result, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# Gate test: analyze() returns structured diagnosis for a real compiler error
# ---------------------------------------------------------------------------

class TestAnalyze:
    """Gate: analyze() returns structured diagnosis for a real compiler error."""

    def test_returns_dict(self, sample_errors, sample_source):
        result = analyze(compiler_errors=sample_errors, source_code=sample_source)
        assert isinstance(result, dict)

    def test_returns_all_required_fields(self, sample_errors, sample_source):
        result = analyze(compiler_errors=sample_errors, source_code=sample_source)
        for field in ("summary", "root_cause", "affected_files", "affected_lines",
                      "confidence", "repair_plan"):
            assert field in result, f"Missing field: {field}"

    def test_summary_is_nonempty_string(self, sample_errors, sample_source):
        result = analyze(compiler_errors=sample_errors, source_code=sample_source)
        assert isinstance(result["summary"], str) and result["summary"].strip()

    def test_root_cause_is_nonempty_string(self, sample_errors, sample_source):
        result = analyze(compiler_errors=sample_errors, source_code=sample_source)
        assert isinstance(result["root_cause"], str) and result["root_cause"].strip()

    def test_affected_files_is_list(self, sample_errors, sample_source):
        result = analyze(compiler_errors=sample_errors, source_code=sample_source)
        assert isinstance(result["affected_files"], list)

    def test_affected_lines_is_list(self, sample_errors, sample_source):
        result = analyze(compiler_errors=sample_errors, source_code=sample_source)
        assert isinstance(result["affected_lines"], list)

    def test_confidence_is_float_in_range(self, sample_errors, sample_source):
        result = analyze(compiler_errors=sample_errors, source_code=sample_source)
        assert isinstance(result["confidence"], (int, float))
        assert 0.0 <= result["confidence"] <= 1.0

    def test_repair_plan_is_nonempty_list(self, sample_errors, sample_source):
        result = analyze(compiler_errors=sample_errors, source_code=sample_source)
        assert isinstance(result["repair_plan"], list)
        assert len(result["repair_plan"]) >= 1

    def test_repair_plan_items_are_strings(self, sample_errors, sample_source):
        result = analyze(compiler_errors=sample_errors, source_code=sample_source)
        for step in result["repair_plan"]:
            assert isinstance(step, str), f"repair_plan step must be str: {step!r}"

    def test_with_migration_journal(self, sample_errors, sample_source):
        journal = [{"attempt": 1, "root_cause": "type mismatch", "repair_plan": ["tried X"]}]
        result = analyze(
            compiler_errors=sample_errors,
            source_code=sample_source,
            attempt=1,
            migration_journal=journal,
        )
        assert isinstance(result, dict)

    def test_with_empty_errors_list(self, sample_source):
        """analyze() must handle empty error list without crashing."""
        result = analyze(compiler_errors=[], source_code=sample_source)
        assert isinstance(result, dict)

    def test_uses_analysis_model(self, sample_errors, sample_source, monkeypatch):
        """Verify that the analysis model constant is passed to chat_completion."""
        captured = {}

        class CapturingClient:
            def chat_completion(self, model, messages, max_tokens=2048):
                captured["model"] = model
                captured["messages"] = messages
                # Return a valid mock response
                return {
                    "id": "test-1",
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({
                                "summary": "test",
                                "root_cause": "test cause",
                                "affected_files": ["f.hip"],
                                "affected_lines": [1],
                                "confidence": 0.9,
                                "repair_plan": ["fix it"],
                            }),
                        },
                        "finish_reason": "stop",
                    }],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }

        monkeypatch.setattr("app.agents.analysis_agent.get_ai_client", lambda: CapturingClient())
        analyze(compiler_errors=sample_errors, source_code=sample_source)
        assert captured["model"] == ANALYSIS_MODEL

    def test_prompt_sections_sent_to_client(self, sample_errors, sample_source, monkeypatch):
        """Verify the 6-section prompt structure reaches the client."""
        captured = {}

        class CapturingClient:
            def chat_completion(self, model, messages, max_tokens=2048):
                captured["messages"] = messages
                return {
                    "id": "test-1",
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({
                                "summary": "s",
                                "root_cause": "r",
                                "affected_files": [],
                                "affected_lines": [],
                                "confidence": 0.8,
                                "repair_plan": ["step"],
                            }),
                        },
                        "finish_reason": "stop",
                    }],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }

        monkeypatch.setattr("app.agents.analysis_agent.get_ai_client", lambda: CapturingClient())
        analyze(compiler_errors=sample_errors, source_code=sample_source)

        user_content = captured["messages"][1]["content"]
        for section in ["## 2. Current Task", "## 3. Source Code",
                        "## 4. Compiler Diagnostics", "## 5. Migration Journal",
                        "## 6. Expected JSON Schema"]:
            assert section in user_content, f"Missing section: {section}"


# ---------------------------------------------------------------------------
# Test: handle_analyzing workflow state integration
# ---------------------------------------------------------------------------

class TestHandleAnalyzing:
    """handle_analyzing must call analyze() and store result in context."""

    @pytest.mark.asyncio
    async def test_returns_patching(self, tmp_path):
        from app.workflow_engine.context import WorkflowContext
        from app.workflow_engine.states import handle_analyzing

        ctx = WorkflowContext(
            migration_id="migration_20260701_000000_a",
            workspace_path=str(tmp_path),
        )
        ctx.compiler_errors = [
            CompilerError(file="k.hip", line=10, column=1,
                         message="undefined symbol", code="E0001")
        ]
        result = await handle_analyzing(ctx)
        assert result == "PATCHING"

    @pytest.mark.asyncio
    async def test_stores_analysis_result_in_context(self, tmp_path):
        from app.workflow_engine.context import WorkflowContext
        from app.workflow_engine.states import handle_analyzing

        ctx = WorkflowContext(
            migration_id="migration_20260701_000000_b",
            workspace_path=str(tmp_path),
        )
        ctx.compiler_errors = [
            CompilerError(file="k.hip", line=10, column=1,
                         message="undefined symbol", code="E0001")
        ]
        await handle_analyzing(ctx)
        assert ctx.analysis_result is not None, "analysis_result must be set"
        assert "root_cause" in ctx.analysis_result

    @pytest.mark.asyncio
    async def test_appends_journal_entry(self, tmp_path):
        from app.workflow_engine.context import WorkflowContext
        from app.workflow_engine.states import handle_analyzing

        ctx = WorkflowContext(
            migration_id="migration_20260701_000000_c",
            workspace_path=str(tmp_path),
        )
        ctx.compiler_errors = [
            CompilerError(file="k.hip", line=10, column=1,
                         message="undefined symbol", code="E0001")
        ]
        assert len(ctx.migration_journal) == 0
        await handle_analyzing(ctx)
        assert len(ctx.migration_journal) == 1

    @pytest.mark.asyncio
    async def test_journal_entry_has_required_fields(self, tmp_path):
        from app.workflow_engine.context import WorkflowContext
        from app.workflow_engine.states import handle_analyzing

        ctx = WorkflowContext(
            migration_id="migration_20260701_000000_d",
            workspace_path=str(tmp_path),
        )
        ctx.compiler_errors = [
            CompilerError(file="k.hip", line=10, column=1,
                         message="undefined symbol", code="E0001")
        ]
        await handle_analyzing(ctx)
        entry = ctx.migration_journal[0]
        assert "attempt" in entry
        assert "analysis_summary" in entry
        assert "root_cause" in entry
        assert "repair_plan" in entry

    @pytest.mark.asyncio
    async def test_reads_source_from_hipify_output_path(self, tmp_path):
        """handle_analyzing reads the HIP source via hipify_output_path."""
        from app.workflow_engine.context import WorkflowContext
        from app.workflow_engine.states import handle_analyzing

        hip_file = tmp_path / "kernel.hip"
        hip_file.write_text("#include <hip/hip_runtime.h>\n__global__ void k() {}\n")

        ctx = WorkflowContext(
            migration_id="migration_20260701_000000_e",
            workspace_path=str(tmp_path),
        )
        ctx.hipify_output_path = str(hip_file)
        ctx.compiler_errors = []
        await handle_analyzing(ctx)
        assert ctx.analysis_result is not None
