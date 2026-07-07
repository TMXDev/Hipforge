"""
tests/backend/test_migration_hardening.py

Unit and integration tests for migration logic hardening:
  - Preflight project inventory
  - Build-system selection determinism
  - Multi-file compile/link fallback
  - Dependency/missing-symbol handling
  - Repair policy
  - Report field completeness

All tests run in mock mode (no real ROCm tools required).
"""

import os
import json
from pathlib import Path
import pytest

os.environ.setdefault("USE_MOCK_COMPILER", "true")
os.environ.setdefault("USE_MOCK_AI", "true")

from app.compiler.project_scanner import scan_project, DEPENDENCY_ERROR
from app.compiler.makefile_generator import generate_makefile_content, write_generated_makefile
from app.compiler.error_parser import classify_compiler_error, extract_missing_symbol
from app.workflow_engine.context import WorkflowContext
from app.workflow_engine.states import handle_preflight, handle_hipify, handle_sca, handle_compiling


# ── helpers ──────────────────────────────────────────────────────────────

SAMPLE_CUDA = "#include <cuda_runtime.h>\n__global__ void k(int *a){} \nint main(){return 0;}\n"
SAMPLE_HIP = "#include <hip/hip_runtime.h>\n__global__ void k(int *a){}\nint main(){return 0;}\n"


def _ws(tmp_path, files: dict) -> Path:
    """Create a minimal workspace with input/ files."""
    ws = tmp_path / "ws"
    for sub in ("input", "generated", "logs", "artifacts", "reports", "exports"):
        (ws / sub).mkdir(parents=True)
    for name, content in files.items():
        p = ws / "input" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return ws


# ── 1. Preflight project inventory ───────────────────────────────────────

class TestProjectInventory:
    def test_single_file_input_kind(self, tmp_path):
        d = tmp_path / "input"
        d.mkdir()
        (d / "kernel.cu").write_text(SAMPLE_CUDA, encoding="utf-8")
        scan = scan_project(d)
        inv = scan["project_inventory"]
        assert inv["input_kind"] == "single_file"
        assert len(inv["cuda_source_files"]) == 1
        assert inv["build_system_detected"] == "none"
        assert inv["generated_makefile_fallback"] is True

    def test_folder_with_makefile_input_kind(self, tmp_path):
        d = tmp_path / "input"
        d.mkdir()
        (d / "kernel.cu").write_text(SAMPLE_CUDA, encoding="utf-8")
        (d / "Makefile").write_text("all:\n", encoding="utf-8")
        scan = scan_project(d)
        inv = scan["project_inventory"]
        assert inv["input_kind"] == "folder"
        assert inv["build_system_detected"] == "makefile"
        assert inv["generated_makefile_fallback"] is False

    def test_multi_file_no_build_system(self, tmp_path):
        d = tmp_path / "input"
        d.mkdir()
        (d / "main.cu").write_text(SAMPLE_CUDA, encoding="utf-8")
        (d / "gelu.cu").write_text("__global__ void gelu(){}\n", encoding="utf-8")
        scan = scan_project(d)
        inv = scan["project_inventory"]
        assert inv["generated_makefile_fallback"] is True

    def test_inventory_in_scan_result(self, tmp_path):
        d = tmp_path / "input"
        d.mkdir()
        (d / "kernel.cu").write_text(SAMPLE_CUDA, encoding="utf-8")
        scan = scan_project(d)
        assert "project_inventory" in scan
        assert "input_kind" in scan  # top-level shortcut


# ── 2. Build-system selection ─────────────────────────────────────────────

class TestBuildSystemSelection:
    def test_uses_existing_makefile_strategy(self, tmp_path):
        d = tmp_path / "input"
        d.mkdir()
        (d / "kernel.cu").write_text(SAMPLE_CUDA, encoding="utf-8")
        (d / "Makefile").write_text("all:\n", encoding="utf-8")
        scan = scan_project(d)
        assert scan["compile_strategy"] == "makefile"

    def test_generated_makefile_lives_in_correct_path(self, tmp_path):
        ws = tmp_path / "ws"
        (ws / "generated").mkdir(parents=True)
        input_dir = ws / "input"
        input_dir.mkdir()
        (input_dir / "kernel.cu").write_text(SAMPLE_CUDA, encoding="utf-8")
        scan = scan_project(input_dir)
        result = write_generated_makefile(ws, scan, "gfx90a", input_dir)
        assert result is not None
        assert result == ws / "generated" / "Makefile.hipforge"

    def test_user_makefile_not_overwritten(self, tmp_path):
        ws = tmp_path / "ws"
        gen = ws / "generated"
        gen.mkdir(parents=True)
        (gen / "Makefile").write_text("# user makefile\n", encoding="utf-8")
        input_dir = ws / "input"
        input_dir.mkdir()
        (input_dir / "kernel.cu").write_text(SAMPLE_CUDA, encoding="utf-8")
        scan = scan_project(input_dir)
        result = write_generated_makefile(ws, scan, "gfx90a", input_dir)
        assert result is None
        assert (gen / "Makefile").read_text(encoding="utf-8") == "# user makefile\n"

    def test_no_generated_makefile_when_makefile_exists(self, tmp_path):
        d = tmp_path / "input"
        d.mkdir()
        (d / "kernel.cu").write_text(SAMPLE_CUDA, encoding="utf-8")
        (d / "Makefile").write_text("all:\n", encoding="utf-8")
        scan = scan_project(d)
        assert not scan["compile_strategy"].startswith("generated_")


# ── 3. Multi-file generated Makefile ─────────────────────────────────────

class TestMultiFileGeneratedMakefile:
    def test_all_sources_in_makefile(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "main.cu").write_text(SAMPLE_CUDA, encoding="utf-8")
        (input_dir / "gelu.cu").write_text("__global__ void gelu(){}\n", encoding="utf-8")
        scan = scan_project(input_dir)
        content = generate_makefile_content(scan, "gfx90a", input_dir)
        assert "main.hip" in content
        assert "gelu.hip" in content

    def test_arch_in_every_generated_makefile(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "main.cu").write_text(SAMPLE_CUDA, encoding="utf-8")
        (input_dir / "helper.cpp").write_text("void h(){}\n", encoding="utf-8")
        scan = scan_project(input_dir)
        content = generate_makefile_content(scan, "gfx942", input_dir)
        # arch must appear exactly once in ARCH line, and in the compile target
        assert "ARCH ?= gfx942" in content
        assert "--offload-arch=$(ARCH)" in content
        assert "helper.cpp" in content

    def test_single_file_fallback_works(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "kernel.cu").write_text(SAMPLE_CUDA, encoding="utf-8")
        scan = scan_project(input_dir)
        content = generate_makefile_content(scan, "gfx90a", input_dir)
        assert "kernel.hip" in content


# ── 4. Dependency / missing-symbol handling ───────────────────────────────

class TestDependencyErrorHandling:
    def test_undefined_reference_is_dependency_error(self):
        err = "ld.lld: error: undefined reference to `run_gelu`"
        assert classify_compiler_error(err) == DEPENDENCY_ERROR

    def test_undefined_symbol_is_dependency_error(self):
        err = "undefined symbol: hipLaunchKernel"
        assert classify_compiler_error(err) == DEPENDENCY_ERROR

    def test_missing_header_is_dependency_error(self):
        err = "fatal error: 'mylib.h' file not found"
        assert classify_compiler_error(err) == DEPENDENCY_ERROR

    def test_missing_source_file_is_dependency_error(self):
        err = "make: *** No rule to make target 'helper.hip'. No such file or directory."
        assert classify_compiler_error(err) == DEPENDENCY_ERROR

    def test_extract_missing_symbol_from_linker_error(self):
        err = "ld.lld: error: undefined symbol: run_gelu\n>>> referenced by main.hip"
        sym = extract_missing_symbol(err)
        assert sym == "run_gelu"

    def test_extract_missing_symbol_undefined_reference(self):
        err = "undefined reference to `compute_loss`"
        sym = extract_missing_symbol(err)
        assert sym == "compute_loss"

    def test_extract_missing_header(self):
        err = "fatal error: 'myutils.h' file not found"
        sym = extract_missing_symbol(err)
        assert "myutils.h" in sym

    def test_extract_missing_library(self):
        err = "/usr/bin/ld: cannot find -lmycudalib"
        sym = extract_missing_symbol(err)
        assert "-lmycudalib" in sym

    def test_extract_returns_empty_for_no_symbol(self):
        err = "error: some generic error with no symbol"
        sym = extract_missing_symbol(err)
        assert sym == ""


# ── 5. Repair policy ─────────────────────────────────────────────────────

class TestRepairPolicy:
    @pytest.mark.asyncio
    async def test_dependency_error_skips_ai_repair(self):
        ctx = WorkflowContext("test-dep", "/tmp/nonexistent-dep")
        ctx.last_compile_stderr = "ld.lld: error: undefined symbol: run_gelu"
        ctx.current_state = "ANALYZING"
        with pytest.raises(RuntimeError):
            from app.workflow_engine.states import handle_analyzing
            await handle_analyzing(ctx)
        assert ctx.error_category == "DEPENDENCY_ERROR"
        assert "missing project dependency" in ctx.recommended_next_action.lower()

    @pytest.mark.asyncio
    async def test_dependency_error_includes_symbol_name(self):
        ctx = WorkflowContext("test-sym", "/tmp/nonexistent-sym")
        ctx.last_compile_stderr = "ld.lld: error: undefined symbol: gelu_forward"
        ctx.current_state = "ANALYZING"
        with pytest.raises(RuntimeError):
            from app.workflow_engine.states import handle_analyzing
            await handle_analyzing(ctx)
        # Missing symbol name should appear in the recommended action
        assert "gelu_forward" in ctx.recommended_next_action

    @pytest.mark.asyncio
    async def test_missing_header_dep_error_skips_ai_repair(self):
        ctx = WorkflowContext("test-hdr", "/tmp/nonexistent-hdr")
        ctx.last_compile_stderr = "fatal error: 'mylib.h' file not found\nno such file or directory"
        ctx.current_state = "ANALYZING"
        with pytest.raises(RuntimeError):
            from app.workflow_engine.states import handle_analyzing
            await handle_analyzing(ctx)
        assert ctx.error_category == "DEPENDENCY_ERROR"


# ── 6. Report fields ─────────────────────────────────────────────────────

class TestReportFields:
    @pytest.mark.asyncio
    async def test_json_report_contains_inventory_and_compile_command(self, tmp_path, monkeypatch):
        from app.services.report_service import generate_json_report
        from app.workspace.manager import get_workspace_path

        mid = "migration_report_test_hardening"
        ws = tmp_path / mid
        for sub in ("input", "generated", "logs", "artifacts", "reports", "exports"):
            (ws / sub).mkdir(parents=True)
        (ws / "input" / "kernel.cu").write_text(SAMPLE_CUDA, encoding="utf-8")

        monkeypatch.setattr(
            "app.services.report_service.get_workspace_path",
            lambda _id: ws,
        )

        ctx = WorkflowContext(mid, str(ws))
        ctx.compilation_success = False
        ctx.error_category = "DEPENDENCY_ERROR"
        ctx.last_compile_command = "hipcc main.hip gelu.hip -o output --offload-arch=gfx90a"
        ctx.source_files = ["main.hip", "gelu.hip"]
        ctx.project_inventory = {
            "input_kind": "folder",
            "cuda_source_files": ["main.cu", "gelu.cu"],
            "hip_source_files": [],
            "header_files": [],
            "build_system_detected": "none",
            "generated_makefile_fallback": True,
        }
        ctx.generated_makefile_path = str(ws / "generated" / "Makefile.hipforge")
        ctx.project_scan = {
            "category": None,
            "message": "CUDA project detected.",
            "input_kind": "folder",
            "compile_strategy": "generated_multi_file_makefile",
            "cu_files": ["main.cu", "gelu.cu"],
            "hip_files": [],
            "cpp_files": [],
            "header_files": [],
            "build_system_detected": "none",
            "project_inventory": ctx.project_inventory,
        }
        ctx.recommended_next_action = "Upload the full project including gelu.hip."

        await generate_json_report(mid, ctx)

        report_file = ws / "reports" / "migration_report.json"
        assert report_file.exists()
        data = json.loads(report_file.read_text(encoding="utf-8"))

        # project_scan section
        ps = data["project_scan"]
        assert ps["input_kind"] == "folder"
        assert ps["generated_makefile_path"] is not None
        assert "project_inventory" in ps

        # migration_metrics section
        mm = data["migration_metrics"]
        assert mm["compile_command"] == "hipcc main.hip gelu.hip -o output --offload-arch=gfx90a"
        assert "main.hip" in mm["source_files_compiled"]
        assert "gelu.hip" in mm["source_files_compiled"]

        # validation_confidence section
        vc = data["validation_confidence"]
        assert vc["validation_confidence"] == "LOW"
        assert vc["validation_confidence_reason"] == "conversion happened but real compile failed or did not run (hipify failed)"
        assert vc["compile_validation_status"] == "FAILED"
        assert vc["runtime_validation_enabled"] is False
        assert vc["runtime_validation_status"] == "NOT_RUN"
        assert "runtime_validation_reason" in vc
        assert vc["profiling_status"] == "NOT_CONFIGURED"

    @pytest.mark.asyncio
    async def test_markdown_report_contains_inventory_fields(self, tmp_path, monkeypatch):
        from app.services.report_service import generate_markdown_report
        from app.workspace.manager import get_workspace_path

        mid = "migration_report_md_hardening"
        ws = tmp_path / mid
        for sub in ("input", "generated", "logs", "artifacts", "reports", "exports"):
            (ws / sub).mkdir(parents=True)
        (ws / "input" / "kernel.cu").write_text(SAMPLE_CUDA, encoding="utf-8")

        monkeypatch.setattr(
            "app.services.report_service.get_workspace_path",
            lambda _id: ws,
        )

        ctx = WorkflowContext(mid, str(ws))
        ctx.compilation_success = False
        ctx.last_compile_command = "hipcc main.hip -o output --offload-arch=gfx90a"
        ctx.source_files = ["main.hip"]
        ctx.project_inventory = {
            "input_kind": "single_file",
            "cuda_source_files": ["main.cu"],
            "hip_source_files": [],
            "header_files": [],
            "build_system_detected": "none",
            "generated_makefile_fallback": True,
        }
        ctx.project_scan = {
            "category": None,
            "message": "CUDA project detected.",
            "input_kind": "single_file",
            "compile_strategy": "generated_single_file_makefile",
            "cu_files": ["main.cu"],
            "hip_files": [],
            "cpp_files": [],
            "cuh_files": [],
            "header_files": [],
            "build_system_detected": "none",
            "project_inventory": ctx.project_inventory,
            "file_count": 1,
            "entrypoint_count": 1,
        }

        await generate_markdown_report(mid, ctx)

        md = (ws / "reports" / "migration_report.md").read_text(encoding="utf-8")
        assert "Input Kind" in md
        assert "single_file" in md
        assert "Generated Makefile Fallback" in md
        assert "hipcc main.hip -o output" in md

        # validation confidence fields
        assert "Validation Confidence" in md
        assert "Runtime Validation Enabled" in md
        assert "Runtime Validation Status" in md
        assert "NOT_RUN" in md
        assert "Profiling Status" in md
