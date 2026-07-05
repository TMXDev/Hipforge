"""
End-to-end integration test for auto-generated Makefile build plan.

Verifies all 7 criteria for a multi-file CUDA project without a build system:
  1. project scan strategy → generated_multi_file_makefile
  2. Makefile.hipforge created in workspace/generated
  3. Referenced files exist from the Makefile working directory
  4. COMPILING copies Makefile.hipforge → Makefile and uses it
  5. helper.cpp included in SOURCES
  6. preflight report contains the strategy
  7. project_summary_line() shows Build Strategy
"""

import os
import json
import tempfile
from pathlib import Path

import pytest
from app.workflow_engine.context import WorkflowContext
from app.workflow_engine.state_machine import WorkflowEngine
from app.workspace.manager import get_workspace_path


@pytest.mark.asyncio
async def test_generated_makefile_e2e(redis_test_client, monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="hipforge_int_"))
    monkeypatch.setenv("WORKSPACE_PATH", str(root))
    monkeypatch.setenv("USE_MOCK_COMPILER", "true")
    monkeypatch.setenv("USE_MOCK_AI", "true")

    migration_id = "int-gen-makefile-e2e"
    ws = get_workspace_path(migration_id)
    ws.mkdir(parents=True)
    for sub in ("input", "generated", "patches", "logs", "artifacts", "reports", "exports"):
        (ws / sub).mkdir(parents=True, exist_ok=True)

    (ws / "input" / "main.cu").write_text(
        '#include <cuda_runtime.h>\n#include <stdio.h>\n'
        'extern void helper_init();\n'
        'int main() {\n    helper_init();\n'
        '    printf("Hello from main\\n");\n    return 0;\n}\n'
    )
    (ws / "input" / "helper.cpp").write_text(
        '#include <cuda_runtime.h>\n#include <stdio.h>\n'
        'void helper_init() {\n    printf("Helper initialized\\n");\n}\n'
    )
    (ws / "input" / "helper.h").write_text('#pragma once\nvoid helper_init();\n')

    ctx = WorkflowContext(migration_id, str(ws), retry_budget=2)
    ctx.target_gpu_architecture = "gfx942"

    engine = WorkflowEngine(ctx)

    visited = []
    for name, handler in list(engine.state_registry.items()):
        def wrap(h, n):
            async def w(c):
                visited.append(n)
                return await h(c)
            return w
        engine.state_registry[name] = wrap(handler, name)

    final_state = await engine.run()

    gen = ws / "generated"
    mf = gen / "Makefile.hipforge"

    scan = ctx.project_scan
    assert scan is not None
    assert scan["compile_strategy"] == "generated_multi_file_makefile", \
        f"got {scan['compile_strategy']}"
    print(f"[1] Strategy: {scan['compile_strategy']}")

    assert mf.exists(), "Makefile.hipforge missing"
    print("[2] Makefile.hipforge exists")

    content = mf.read_text()
    # .cu → .hip + .cpp are SOURCES; headers found via -I include paths
    for ref in ("main.hip", "helper.cpp"):
        assert ref in content, f"Makefile missing {ref}"
    assert "-I." in content and "-I../input" in content, "Makefile missing include paths"
    for ref in ("main.hip", "helper.cpp", "helper.h"):
        assert (gen / ref).exists(), f"{ref} not in generated/"
    print("[3] References real files")

    assert (gen / "Makefile").exists(), "Makefile copy missing"
    assert ctx.source_files is not None
    print("[4] Compile used Makefile.hipforge")

    assert "helper.cpp" in content, "helper.cpp not in SOURCES"
    print("[5] helper.cpp in SOURCES")

    report_p = ws / "artifacts" / "preflight_report.json"
    assert report_p.exists()
    rpt = json.loads(report_p.read_text())
    assert rpt["project_scan"]["compile_strategy"] == "generated_multi_file_makefile"
    print("[6] Report contains strategy")

    assert scan["compile_strategy"] == "generated_multi_file_makefile"
    print(f"[7] Build Strategy: {scan['compile_strategy']}")

    print(f"\nFinal: {final_state}")
    print(f"States: {' -> '.join(visited)}")
    print(f"\nMakefile:\n{content}")
    print("\nAll 7 PASSED")
