"""
Verification tests for 3 CLI migration workflow scenarios.
Run with: pytest tests/backend/test_verify_scenarios.py -s -v
"""
import os, tempfile, zipfile
from pathlib import Path
import pytest


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO 1: .zip input with gfx908 -> NO double-zip
# ═══════════════════════════════════════════════════════════════════════════
def test_zip_input_no_double_zip():
    from cli.hipforge import zip_project

    tmp = Path(tempfile.mktemp(suffix=".zip"))
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("kernel.cu", "int main() {}")
        zf.writestr("src/helper.h", "// helper")
    print(f"\n  Input zip: {tmp.name}")
    print(f"  Contents: {[n for n in zipfile.ZipFile(tmp, 'r').namelist()]}")

    result = zip_project(tmp)

    assert result == tmp, f"Expected same path, got {result}"
    assert result is tmp, "Object identity check -- no new zip created"
    print(f"  zip_project returned same path (no double-zip)")
    print(f"  Contents still: {[n for n in zipfile.ZipFile(result, 'r').namelist()]}")
    print(f"  PASS")
    tmp.unlink()


def test_zip_input_folder_still_packs():
    """Verify that folder input STILL gets zipped (regression check)."""
    from cli.hipforge import zip_project

    tmpdir = tempfile.mkdtemp()
    tmp_path = Path(tmpdir)
    (tmp_path / "kernel.cu").write_text("int main() {}")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "helper.h").write_text("// helper")

    result = zip_project(tmp_path)

    assert result != tmp_path, "Folder input SHOULD produce a new zip"
    assert zipfile.is_zipfile(result)
    with zipfile.ZipFile(result, "r") as zf:
        names = zf.namelist()
    assert "kernel.cu" in names
    print(f"  Folder input: produced {result.name} with {names}")
    print(f"  PASS (folder still zipped, no regression)")
    result.unlink()


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO 2: main.cu with gfx908, retry_budget=2
#   Expects: 2 repair cycles (ANALYZING+PATCHING), 3 compile attempts
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_retry_budget_2_gives_2_repairs_3_compiles(redis_test_client):
    from app.workflow_engine.state_machine import WorkflowEngine
    from app.workflow_engine.context import WorkflowContext

    # Use same pattern as test_workflow_engine_failure_exhausted_retries:
    # stub handlers (migration_id starting with "test-") + compilation_success=False
    migration_id = "test-verify-r2"
    workspace_path = "/tmp/verify-r2"

    context = WorkflowContext(migration_id, workspace_path, retry_budget=2)
    # compilation_success=False makes COMPILING always determine as failure
    context.compilation_success = False

    engine = WorkflowEngine(context)
    visited_states = []

    # Wrap handlers to record state transitions
    for state_name, handler in list(engine.state_registry.items()):
        def make_wrapper(h, name):
            async def wrapper(ctx):
                visited_states.append(name)
                return await h(ctx)
            return wrapper
        engine.state_registry[state_name] = make_wrapper(handler, state_name)

    await engine.run()

    print(f"\n  States visited ({len(visited_states)}):")
    for i, s in enumerate(visited_states):
        markers = []
        if s in ("ANALYZING", "PATCHING"):
            markers.append("AI REPAIR")
        if s == "COMPILING":
            nth = sum(1 for x in visited_states[:i] if x == "COMPILING") + 1
            markers.append(f"compile #{nth}")
        label = f"  <- {' + '.join(markers)}" if markers else ""
        print(f"    [{i+1:2d}] {s}{label}")

    analyze_count = sum(1 for s in visited_states if s == "ANALYZING")
    patching_count = sum(1 for s in visited_states if s == "PATCHING")
    compiling_count = sum(1 for s in visited_states if s == "COMPILING")

    print(f"\n  Repair cycles (ANALYZING): {analyze_count}")
    print(f"  Compile attempts:          {compiling_count}")
    print(f"  Final state:               {visited_states[-1]}")
    print(f"  current_attempt:           {engine.context.current_attempt}")
    print(f"  compilation_success:       {engine.context.compilation_success}")

    assert analyze_count == 2, f"Expected 2 ANALYZING, got {analyze_count}"
    assert patching_count == 2, f"Expected 2 PATCHING, got {patching_count}"
    assert compiling_count == 3, f"Expected 3 COMPILING, got {compiling_count}"
    assert visited_states[-1] == "GENERATING_REPORT", "Retry exhaustion reaches GENERATING_REPORT"
    assert engine.context.current_state == "FAILED", "State machine transitions to FAILED after GENERATING_REPORT"
    assert engine.context.current_attempt == 2
    print(f"  PASS: retry_budget=2 -> 2 repair cycles + 3 compile attempts")


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO 3: gfx940 (format passes) vs invalid_arch (format fails)
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_preflight_arch_validation(redis_test_client):
    """
    Tests the handle_preflight arch format check directly.
    invalid_arch -> format rejected -> UNSUPPORTED_FEATURE
    gfx940 -> format OK (actual support handled by compiler later)
    """
    from app.workflow_engine.states import handle_preflight
    from app.workflow_engine.context import WorkflowContext

    # -- Part A: invalid_arch is REJECTED by preflight format check --
    ctx = WorkflowContext("test-pf-reject", "/tmp/pf-reject", retry_budget=2)
    ctx.target_gpu_architecture = "invalid_arch"
    ctx.migration_id = "mock-pf-reject"  # Override so it doesn't get stub handler
    ctx.workspace_path = tempfile.mkdtemp()
    (Path(ctx.workspace_path) / "generated").mkdir(parents=True)
    (Path(ctx.workspace_path) / "input").mkdir(parents=True)
    (Path(ctx.workspace_path) / "input" / "kernel.cu").write_text("// test\n", encoding="utf-8")

    raised = False
    try:
        await handle_preflight(ctx)
    except RuntimeError as e:
        raised = True
        print(f"\n  Part A -- arch='invalid_arch':")
        print(f"  handle_preflight raised RuntimeError: {e}")
        print(f"  error_category:       {ctx.error_category}")
        print(f"  infrastructure_error: {ctx.infrastructure_error}")
        print(f"  failure_reason:       {ctx.failure_reason[:80]}...")

    assert raised, "handle_preflight should have raised RuntimeError for invalid arch"
    assert ctx.error_category == "UNSUPPORTED_FEATURE", f"Expected UNSUPPORTED_FEATURE, got {ctx.error_category}"
    assert ctx.infrastructure_error is True
    print(f"  PASS: invalid arch rejected at preflight")

    # -- Part B: gfx940 passes format check --
    os.environ["USE_MOCK_COMPILER"] = "true"
    os.environ["USE_MOCK_AI"] = "true"
    ctx2 = WorkflowContext("test-pf-pass", "/tmp/pf-pass", retry_budget=2)
    ctx2.target_gpu_architecture = "gfx940"
    ctx2.migration_id = "mock-pf-pass2"
    ctx2.workspace_path = tempfile.mkdtemp()
    (Path(ctx2.workspace_path) / "generated").mkdir(parents=True)
    (Path(ctx2.workspace_path) / "input").mkdir(parents=True)
    (Path(ctx2.workspace_path) / "input" / "kernel.cu").write_text("// test\n", encoding="utf-8")

    try:
        await handle_preflight(ctx2)
        print(f"\n  Part B -- arch='gfx940': handle_preflight completed")
        print(f"  error_category:       {ctx2.error_category}")
        print(f"  infrastructure_error: {ctx2.infrastructure_error}")
        print(f"  gfx940 passes format check (compiler support handled later)")
    except RuntimeError as e:
        print(f"\n  Part B -- arch='gfx940': handle_preflight raised (unexpected): {e}")
        print(f"  error_category: {ctx2.error_category}, infra_error: {ctx2.infrastructure_error}")

    assert ctx2.infrastructure_error is False, f"gfx940 should NOT be rejected at format check"
    print(f"  PASS: gfx940 has valid format (backend compiler will handle actual support)")
    del os.environ["USE_MOCK_COMPILER"]
    del os.environ["USE_MOCK_AI"]


# ═══════════════════════════════════════════════════════════════════════════
# BONUS: Verify RESEARCHING in pipeline display and transitions
# ═══════════════════════════════════════════════════════════════════════════
def test_researching_removed_from_pipeline_display():
    """RESEARCHING was removed from the pipeline display (dead/unreachable)."""
    from cli.hipforge import draw_stage_pipeline
    import io, contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        draw_stage_pipeline("COMPILING")
    output = buf.getvalue()

    has_researching = "RESEARCHING" in output
    print(f"\n  Pipeline from draw_stage_pipeline():")
    print(f"  Contains RESEARCHING stage: {has_researching}")
    assert not has_researching, "RESEARCHING should be removed from pipeline display"
    print(f"  Stages shown: {[s.strip('[]') for s in output.split() if s.strip('[]').isupper()]}")
    print(f"  PASS: RESEARCHING removed from pipeline display (dead code removed)")


@pytest.mark.asyncio
async def test_researching_never_reached_in_workflow(redis_test_client):
    """Confirm the workflow does NOT visit RESEARCHING."""
    from app.workflow_engine.state_machine import WorkflowEngine
    from app.workflow_engine.context import WorkflowContext

    migration_id = "test-verify-noresearch"
    workspace_path = "/tmp/verify-noresearch"
    context = WorkflowContext(migration_id, workspace_path, retry_budget=2)
    context.compilation_success = False

    engine = WorkflowEngine(context)
    visited_states = []

    for state_name, handler in list(engine.state_registry.items()):
        def make_wrapper(h, name):
            async def wrapper(ctx):
                visited_states.append(name)
                return await h(ctx)
            return wrapper
        engine.state_registry[state_name] = make_wrapper(handler, state_name)

    await engine.run()

    researching_count = sum(1 for s in visited_states if s == "RESEARCHING")
    print(f"\n  Total states visited: {len(visited_states)}")
    print(f"  RESEARCHING occurrences: {researching_count}")
    assert researching_count == 0, f"Workflow visited RESEARCHING {researching_count} times!"
    print(f"  PASS: RESEARCHING never reached in actual workflow")
    print(f"  States: {visited_states}")
    print(f"  Note: RESEARCHING was removed from draw_stage_pipeline() display;")
    print(f"  transitions.py has no path to reach it. Handler still exists for")
    print(f"  backward compat but maps to GENERATING_REPORT (not COMPILING)")
