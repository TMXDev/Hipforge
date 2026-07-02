"""
tests/backend/test_research_agent.py

Unit tests for the Research Agent (Session 9.4).

Verifies:
  - research() uses the correct 6-section prompt structure
  - Returns structured findings matching docs/11_RESEARCH_AGENT.md / docs/09_AI_AGENTS.md schemas
  - handle_researching() wires correctly into the Workflow Engine state
  - Migration Journal is updated after each research call
  - Invalid AI responses raise ValueError

Gate: Research Agent returns relevant context for a HIP error query.
      pytest tests/backend/test_research_agent.py -v
"""

import json
import os
from pathlib import Path
import pytest

# Force mock mode before any app imports
os.environ["USE_MOCK_AI"] = "true"
os.environ["USE_MOCK_COMPILER"] = "true"

from app.workflow_engine.context import WorkflowContext
from app.workflow_engine.states import handle_researching
from app.agents.research_agent import (
    _build_messages,
    _parse_response,
    research,
    RESEARCH_MODEL,
    _SYSTEM_PROMPT,
)
from app.models.compiler_error import CompilerError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_errors():
    return [
        CompilerError(
            file="kernel.hip",
            line=42,
            column=8,
            message="no matching function for call to 'hipMemcpyAsync'",
            code="E0308",
        )
    ]


@pytest.fixture()
def sample_source():
    return (
        "#include <hip/hip_runtime.h>\n\n"
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
        msgs = _build_messages("test query", sample_source, sample_errors, None)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_system_prompt_contains_keywords(self, sample_errors, sample_source):
        msgs = _build_messages("test query", sample_source, sample_errors, None)
        assert "Research Agent" in msgs[0]["content"]
        assert "documentation" in msgs[0]["content"]

    def test_user_message_contains_six_sections(self, sample_errors, sample_source):
        msgs = _build_messages("test query", sample_source, sample_errors, [])
        content = msgs[1]["content"]
        assert "## 2. Current Task" in content
        assert "## 3. Source Code" in content
        assert "## 4. Compiler Diagnostics" in content
        assert "## 5. Migration Journal" in content
        assert "## 6. Expected JSON Schema" in content

    def test_query_in_user_message(self, sample_errors, sample_source):
        msgs = _build_messages("test query", sample_source, sample_errors, None)
        assert "test query" in msgs[1]["content"]


# ---------------------------------------------------------------------------
# Test: response parsing
# ---------------------------------------------------------------------------

class TestParseResponse:
    """_parse_response must correctly extract and format the structured output."""

    def _valid_json(self):
        return json.dumps({
            "summary": "Found equivalent ROCm memory copy mechanism.",
            "findings": [
                "hipMemcpyAsync requires explicit stream parameter."
            ],
            "recommended_actions": [
                "Check parameters."
            ]
        })

    def test_parses_raw_json(self):
        result = _parse_response(self._valid_json())
        assert result["summary"]
        assert isinstance(result["findings"], list)
        assert isinstance(result["recommended_actions"], list)
        # Optional fields should be populated automatically
        assert "problem" in result
        assert "sources" in result
        assert "confidence" in result
        assert result["confidence"] == 1.0

    def test_strips_markdown_fences(self):
        fenced = f"```json\n{self._valid_json()}\n```"
        result = _parse_response(fenced)
        assert result["summary"]

    def test_raises_on_invalid_json(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            _parse_response("not valid json")

    def test_raises_on_missing_required_fields(self):
        partial = json.dumps({"summary": "ok"})
        with pytest.raises(ValueError, match="missing required fields"):
            _parse_response(partial)


# ---------------------------------------------------------------------------
# Test: research() main wrapper
# ---------------------------------------------------------------------------

class TestResearchWrapper:
    """research() must send request to Fireworks and return conformant schema."""

    def test_returns_expected_fields(self):
        result = research("hipMemcpyAsync ROCm wavefrontSize")
        assert isinstance(result, dict)
        for field in ("summary", "problem", "sources", "findings", "recommended_actions", "confidence"):
            assert field in result, f"Missing field: {field}"
        assert result["summary"]
        assert len(result["findings"]) > 0

    def test_uses_correct_model(self, monkeypatch):
        captured = {}

        class CapturingClient:
            def chat_completion(self, model, messages, max_tokens=2048):
                captured["model"] = model
                return {
                    "choices": [{
                        "message": {
                            "content": json.dumps({
                                "summary": "test",
                                "findings": [],
                                "recommended_actions": []
                            })
                        }
                    }]
                }

        monkeypatch.setattr("app.agents.research_agent.get_ai_client", lambda: CapturingClient())
        research("test")
        assert captured["model"] == RESEARCH_MODEL


# ---------------------------------------------------------------------------
# Test: handle_researching workflow state integration
# ---------------------------------------------------------------------------

class TestHandleResearchingState:
    """handle_researching must execute research and save findings to context/journal."""

    @pytest.mark.asyncio
    async def test_returns_compiling(self, tmp_path):
        ctx = WorkflowContext("test-migration-id", str(tmp_path))
        result = await handle_researching(ctx)
        assert result == "COMPILING"

    @pytest.mark.asyncio
    async def test_stores_research_context_in_ctx(self, tmp_path):
        ctx = WorkflowContext("test-migration-id", str(tmp_path))
        await handle_researching(ctx)
        assert ctx.research_context is not None
        assert "Research Findings" in ctx.research_context
        assert "ROCm documentation confirms" in ctx.research_context

    @pytest.mark.asyncio
    async def test_appends_to_migration_journal(self, tmp_path):
        ctx = WorkflowContext("test-migration-id", str(tmp_path))
        ctx.migration_journal = [{"attempt": 1, "compiler_errors": []}]
        
        await handle_researching(ctx)
        
        # Should have updated the existing entry
        assert len(ctx.migration_journal) == 1
        assert "research_summary" in ctx.migration_journal[-1]
        assert "research_findings" in ctx.migration_journal[-1]

    @pytest.mark.asyncio
    async def test_resilient_to_agent_failures(self, tmp_path, monkeypatch):
        """Failure in Research Agent must not crash the workflow."""
        def failing_research(*args, **kwargs):
            raise RuntimeError("Fireworks API Timeout")

        monkeypatch.setattr("app.agents.research_agent.research", failing_research)
        
        ctx = WorkflowContext("test-migration-id", str(tmp_path))
        next_state = await handle_researching(ctx)
        
        # Should complete and return next state cleanly
        assert next_state == "COMPILING"
        assert ctx.research_context == "Research failed to complete."
