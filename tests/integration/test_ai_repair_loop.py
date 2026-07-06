import os
import sys
import shutil
import pytest
import asyncio
from pathlib import Path

# Ensure backend directory is in python path
sys.path.insert(0, "backend")

# Force mock mode before imports
os.environ["USE_MOCK_COMPILER"] = "true"
os.environ["USE_MOCK_AI"] = "true"

from app.workflow_engine.context import WorkflowContext
from app.workflow_engine.state_machine import WorkflowEngine
from app.models.compiler_error import CompilerError
import app.workflow_engine.states
import app.redis.client


from tests.conftest import MockRedis


@pytest.fixture(autouse=True)
def mock_redis():
    """Patches all Redis clients in backend app modules to use MockRedis."""
    mock_client = MockRedis()
    
    # Save originals
    orig_client = app.redis.client.redis_client
    
    # Apply mocks
    app.redis.client.redis_client = mock_client
    
    yield mock_client
    
    # Restore originals
    app.redis.client.redis_client = orig_client


# ---------------------------------------------------------------------------
# Workspace and Context Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def workspace(tmp_path):
    """
    Creates a temporary workspace with the correct structure and
    copies the broken CUDA fixture into input/.
    """
    ws = tmp_path / "test_repair_loop"
    for subdir in ("input", "generated", "logs", "artifacts", "reports", "exports"):
        (ws / subdir).mkdir(parents=True)
    
    # Locate fixture file
    fixture_src = Path(__file__).parent / "fixtures" / "broken_kernel.cu"
    shutil.copy(fixture_src, ws / "input" / "broken_kernel.cu")
    
    return ws


@pytest.fixture()
def ctx(workspace):
    """Returns a WorkflowContext configured for the integration test."""
    return WorkflowContext(
        migration_id="migration_integration_test_loop",
        workspace_path=str(workspace),
        retry_budget=1,  # Establishes transition to RESEARCHING after 1 failed patch attempt
    )


# ---------------------------------------------------------------------------
# Test Definition
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_ai_repair_loop(ctx, workspace, monkeypatch, mock_redis):
    """
    Integration test verifying the full AI self-healing loop:
    HIPIFY -> COMPILING (fails) -> ANALYZING -> PATCHING -> COMPILING (fails) -> RESEARCHING -> COMPILING (succeeds)
    """
    # 1. Capture the original compilation state handler
    original_handle_compiling = app.workflow_engine.states.handle_compiling
    
    # 2. Mock handle_compiling to guide the engine retry loop to RESEARCHING
    async def mock_handle_compiling(context):
        # Run original compiler wrapper to execute mock run_hipcc and populate context
        await original_handle_compiling(context)
        
        # Override compiler success to force a retry loop
        if context.current_attempt == 0:
            context.compilation_success = False
            # Ensure structured errors are present for subsequent analysis/research prompts
            if not context.compiler_errors:
                context.compiler_errors = [
                    CompilerError(
                        file=context.hipify_output_path or "broken_kernel.hip",
                        line=14,
                        column=5,
                        message="use of undeclared identifier 'hipMemcpyAsync_WRONG'",
                        code="E0020",
                    )
                ]
        else:
            # Once research has executed, allow final compilation to succeed
            context.compilation_success = True
            context.compiler_errors = []
            
        return "COMPILING"

    # Patch handle_compiling with the mock controller
    monkeypatch.setattr(app.workflow_engine.states, "handle_compiling", mock_handle_compiling)
    
    # 3. Initialize and run the Workflow Engine
    # Force context initial state to start at HIPIFY
    ctx.current_state = "HIPIFY"
    
    engine = WorkflowEngine(ctx)
    visited_states = []
    
    # Wrap state handlers to record traversal history
    for state_name, handler in list(engine.state_registry.items()):
        def make_wrapper(h, name):
            async def wrapper(c):
                visited_states.append(name)
                return await h(c)
            return wrapper
        engine.state_registry[state_name] = make_wrapper(handler, state_name)
        
    final_state = await engine.run()
    
    # 4. Assert correct state machine sequence was traversed
    expected_sequence = [
        "HIPIFY",
        "SCA",
        "COMPILING",         # Attempt 0 (initial compile, fails)
        "ANALYZING",         # Analysis Agent diagnoses failure
        "PATCHING",          # Patch Agent writes patch, increments attempt
        "COMPILING",         # Attempt 1 (patch compile, succeeds)
        "GENERATING_REPORT",
        "COMPLETED"
    ]
    
    assert visited_states == expected_sequence
    assert final_state == "COMPLETED"
    assert ctx.compilation_success is True
    
    # 5. Verify the Migration Journal entries
    assert len(ctx.migration_journal) >= 1
    
    # The journal should have recorded the first failure attempt details
    first_attempt = ctx.migration_journal[0]
    assert first_attempt["attempt"] == 1
    assert first_attempt["analysis_summary"]
    assert first_attempt["root_cause"]
    assert len(first_attempt["repair_plan"]) >= 1
