import os
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from app.compiler.project_scanner import (
    scan_project,
    check_nested_zip,
    project_summary_line,
    _find_entrypoints,
    NO_PROJECT_FILES,
    NON_CUDA_CPP_PROJECT,
    HEADER_ONLY_INPUT,
    EXISTING_HIP_PROJECT,
    MIXED_CUDA_HIP_PROJECT,
    NESTED_ARCHIVE_INPUT,
    MULTIPLE_ENTRYPOINTS,
    NO_ENTRYPOINT,
)


# ── helpers ──────────────────────────────────────────────────────────────

def _make_input(tmp_path, files):
    d = tmp_path / "input"
    d.mkdir(parents=True)
    for name, content in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return d


SAMPLE_CUDA = "#include <cuda_runtime.h>\n__global__ void add(int *a) { *a += 1; }\n"
SAMPLE_HIP = "#include <hip/hip_runtime.h>\n__global__ void add(int *a) { *a += 1; }\n"
SAMPLE_CPP = "#include <iostream>\nint main() { return 0; }\n"
SAMPLE_CPP_CUDA = "#include <iostream>\n#include <cuda_runtime.h>\nint main() { cudaMalloc(nullptr, 0); return 0; }\n"
SAMPLE_HEADER = "// some header\n"
MAKEFILE = "all: clean\nclean:\n\trm -f *.o\n"


# ── scan_project tests ───────────────────────────────────────────────────

class TestScanNoProjectFiles:
    def test_empty_directory(self, tmp_path):
        d = _make_input(tmp_path, {})
        scan = scan_project(d)
        assert scan["category"] == NO_PROJECT_FILES
        assert "No CUDA/HIP project files" in scan["message"]
        assert scan["compile_strategy"] == "fail_preflight"

    def test_random_files(self, tmp_path):
        d = _make_input(tmp_path, {"readme.txt": "hello", "data.csv": "a,b,c"})
        scan = scan_project(d)
        assert scan["category"] == NO_PROJECT_FILES
        assert scan["compile_strategy"] == "fail_preflight"


class TestScanExistingHip:
    def test_only_hip_files(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.hip": SAMPLE_HIP})
        scan = scan_project(d)
        assert scan["category"] == EXISTING_HIP_PROJECT
        assert "Existing HIP project" in scan["message"]
        assert len(scan["hip_files"]) == 1
        assert len(scan["cu_files"]) == 0
        assert scan["compile_strategy"] == "generated_existing_hip_makefile"

    def test_multiple_hip_files(self, tmp_path):
        d = _make_input(tmp_path, {"a.hip": SAMPLE_HIP, "b.hip": SAMPLE_HIP})
        scan = scan_project(d)
        assert scan["category"] == EXISTING_HIP_PROJECT
        assert len(scan["hip_files"]) == 2
        assert scan["compile_strategy"] == "fail_preflight"


class TestScanMixedCudaHip:
    def test_cu_and_hip(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.cu": SAMPLE_CUDA, "kernel.hip": SAMPLE_HIP})
        scan = scan_project(d)
        assert scan["category"] == MIXED_CUDA_HIP_PROJECT
        assert "Mixed CUDA/HIP" in scan["message"]
        assert len(scan["cu_files"]) == 1
        assert len(scan["hip_files"]) == 1
        # Multiple source files without build system → fail_preflight
        assert scan["compile_strategy"] == "fail_preflight"

    def test_cu_and_hip_in_code(self, tmp_path):
        d = _make_input(tmp_path, {"main.cpp": SAMPLE_CPP_CUDA, "lib.hip": SAMPLE_HIP})
        scan = scan_project(d)
        assert scan["category"] == MIXED_CUDA_HIP_PROJECT
        assert scan["has_cuda_api"] is True


class TestScanSingleCuNoMakefile:
    def test_single_cu(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.cu": SAMPLE_CUDA})
        scan = scan_project(d)
        assert scan["single_entry_point"] is not None
        assert scan["compile_strategy"] == "generated_single_file_makefile"
        assert scan["has_multiple_source_files"] is False
        assert scan["category"] is None

    def test_single_cu_in_folder(self, tmp_path):
        d = _make_input(tmp_path, {"src/kernel.cu": SAMPLE_CUDA})
        scan = scan_project(d)
        assert scan["single_entry_point"] is not None
        assert scan["compile_strategy"] == "generated_single_file_makefile"

    def test_single_cu_with_header(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.cu": SAMPLE_CUDA, "utils.cuh": SAMPLE_HEADER})
        scan = scan_project(d)
        assert scan["single_entry_point"] is not None
        assert scan["compile_strategy"] == "generated_single_file_makefile"


class TestScanMultiCuNoMakefile:
    def test_multiple_cu_fails(self, tmp_path):
        d = _make_input(tmp_path, {"a.cu": SAMPLE_CUDA, "b.cu": SAMPLE_CUDA})
        scan = scan_project(d)
        assert scan["has_multiple_source_files"] is True
        assert scan["has_build_system"] is False
        assert scan["compile_strategy"] == "fail_preflight"

    def test_multiple_cu_with_makefile(self, tmp_path):
        d = _make_input(tmp_path, {"a.cu": SAMPLE_CUDA, "b.cu": SAMPLE_CUDA, "Makefile": MAKEFILE})
        scan = scan_project(d)
        assert scan["has_multiple_source_files"] is True
        assert scan["has_build_system"] is True
        assert scan["build_system_detected"] == "makefile"
        assert scan["compile_strategy"] == "makefile"

    def test_multiple_sources_cpp_no_build(self, tmp_path):
        d = _make_input(tmp_path, {"main.cu": SAMPLE_CUDA, "utils.cpp": SAMPLE_CPP})
        scan = scan_project(d)
        assert scan["has_multiple_source_files"] is True
        assert scan["has_build_system"] is False
        has_main = any("main(" in line for line in SAMPLE_CPP.splitlines())
        if has_main:
            assert scan["compile_strategy"] == "generated_multi_file_makefile"
        else:
            assert scan["compile_strategy"] == "fail_preflight"


class TestScanHeaderOnly:
    def test_headers_only(self, tmp_path):
        d = _make_input(tmp_path, {"api.h": SAMPLE_HEADER, "types.hpp": SAMPLE_HEADER})
        scan = scan_project(d)
        assert scan["category"] == HEADER_ONLY_INPUT
        assert scan["compile_strategy"] == "fail_preflight"

    def test_cuh_only(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.cuh": SAMPLE_CUDA})
        scan = scan_project(d)
        assert scan["category"] is None
        assert scan["compile_strategy"] == "direct_single_file"


class TestScanNonCudaCpp:
    def test_cpp_no_cuda(self, tmp_path):
        d = _make_input(tmp_path, {"main.cpp": SAMPLE_CPP})
        scan = scan_project(d)
        assert scan["category"] == NON_CUDA_CPP_PROJECT
        assert "regular C/C++ project" in scan["message"]
        assert scan["compile_strategy"] == "fail_preflight"

    def test_cpp_and_headers_no_cuda(self, tmp_path):
        d = _make_input(tmp_path, {"main.cpp": SAMPLE_CPP, "utils.h": SAMPLE_HEADER})
        scan = scan_project(d)
        assert scan["category"] == NON_CUDA_CPP_PROJECT

    def test_cpp_with_cuda_includes(self, tmp_path):
        d = _make_input(tmp_path, {"main.cpp": SAMPLE_CPP_CUDA})
        scan = scan_project(d)
        assert scan["has_cuda_api"] is True
        assert scan["category"] is None


class TestScanBuildSystem:
    def test_makefile(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.cu": SAMPLE_CUDA, "Makefile": MAKEFILE})
        scan = scan_project(d)
        assert scan["has_build_system"] is True
        assert scan["build_system_detected"] == "makefile"

    def test_cmakelists(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.cu": SAMPLE_CUDA, "CMakeLists.txt": MAKEFILE})
        scan = scan_project(d)
        assert scan["has_build_system"] is True
        assert scan["build_system_detected"] == "cmake"

    def test_build_script_mk(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.cu": SAMPLE_CUDA, "build.mk": "all:\n\techo"})
        scan = scan_project(d)
        assert scan["has_build_system"] is True
        assert scan["build_system_detected"] == "build_script"

    def test_cmake_with_multi_cu(self, tmp_path):
        d = _make_input(tmp_path, {"a.cu": SAMPLE_CUDA, "b.cu": SAMPLE_CUDA, "CMakeLists.txt": MAKEFILE})
        scan = scan_project(d)
        assert scan["has_build_system"] is True
        assert scan["build_system_detected"] == "cmake"
        assert scan["compile_strategy"] == "cmake"


# ── check_nested_zip tests ──────────────────────────────────────────────

class TestNestedZip:
    def test_nested_zip_detected(self, tmp_path):
        d = _make_input(tmp_path, {})
        inner_zip = d / "inner.zip"
        with zipfile.ZipFile(inner_zip, "w") as zf:
            zf.writestr("file.txt", "hello")
        outer_zip = d / "outer.zip"
        with zipfile.ZipFile(outer_zip, "w") as zf:
            zf.write(inner_zip, "inner.zip")
        inner_zip.unlink()
        assert check_nested_zip(d) is True

    def test_no_nested_zip(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.cu": SAMPLE_CUDA})
        assert check_nested_zip(d) is False

    def test_single_zip_no_nested(self, tmp_path):
        d = _make_input(tmp_path, {})
        zf_path = d / "project.zip"
        with zipfile.ZipFile(zf_path, "w") as zf:
            zf.writestr("kernel.cu", SAMPLE_CUDA)
        assert check_nested_zip(d) is False


# ── project_summary_line tests ───────────────────────────────────────────

class TestSummaryLine:
    def test_cuda_summary(self, tmp_path):
        d = _make_input(tmp_path, {"a.cu": SAMPLE_CUDA, "b.cuh": SAMPLE_CUDA})
        scan = scan_project(d)
        line = project_summary_line(scan)
        assert "1 CUDA file(s)" in line
        assert "1 CUDA header(s)" in line

    def test_hip_summary(self, tmp_path):
        d = _make_input(tmp_path, {"k.hip": SAMPLE_HIP})
        scan = scan_project(d)
        line = project_summary_line(scan)
        assert "1 HIP file(s)" in line

    def test_empty_summary(self, tmp_path):
        d = _make_input(tmp_path, {"readme.txt": "hi"})
        scan = scan_project(d)
        line = project_summary_line(scan)
        assert "0 CUDA file(s)" in line
        assert "0 HIP file(s)" in line


# ── end-to-end preflight integration (mock) ──────────────────────────────

class TestPreflightProjectScan:
    """Verify the preflight handler logic for project scans."""

    @pytest.fixture(autouse=True)
    def patch_redis(self, monkeypatch, redis_test_client):
        """Ensure Redis is mocked so preflight doesn't hang."""
        monkeypatch.setattr("app.redis.client.redis_client", redis_test_client)

    @pytest.mark.asyncio
    async def test_preflight_no_cuda_files_raises(self, tmp_path):
        from app.workflow_engine.context import WorkflowContext
        from app.workflow_engine.states import handle_preflight

        ws = tmp_path / "workspace"
        for d in ("input", "generated", "logs", "artifacts", "reports", "exports"):
            (ws / d).mkdir(parents=True)
        (ws / "input" / "readme.txt").write_text("hello", encoding="utf-8")

        ctx = WorkflowContext(migration_id="test-preflight-empty", workspace_path=str(ws))
        with pytest.raises(RuntimeError, match="No CUDA/HIP project files"):
            await handle_preflight(ctx)
        assert ctx.error_category == NO_PROJECT_FILES

    @pytest.mark.asyncio
    async def test_preflight_non_cuda_cpp_raises(self, tmp_path):
        from app.workflow_engine.context import WorkflowContext
        from app.workflow_engine.states import handle_preflight

        ws = tmp_path / "workspace"
        for d in ("input", "generated", "logs", "artifacts", "reports", "exports"):
            (ws / d).mkdir(parents=True)
        (ws / "input" / "main.cpp").write_text(SAMPLE_CPP, encoding="utf-8")

        ctx = WorkflowContext(migration_id="test-preflight-cpp", workspace_path=str(ws))
        with pytest.raises(RuntimeError, match="regular C/C\\+\\+ project"):
            await handle_preflight(ctx)
        assert ctx.error_category == NON_CUDA_CPP_PROJECT

    @pytest.mark.asyncio
    async def test_preflight_header_only_raises(self, tmp_path):
        from app.workflow_engine.context import WorkflowContext
        from app.workflow_engine.states import handle_preflight

        ws = tmp_path / "workspace"
        for d in ("input", "generated", "logs", "artifacts", "reports", "exports"):
            (ws / d).mkdir(parents=True)
        (ws / "input" / "api.h").write_text("#pragma once\n", encoding="utf-8")

        ctx = WorkflowContext(migration_id="test-preflight-header", workspace_path=str(ws))
        with pytest.raises(RuntimeError, match="header files"):
            await handle_preflight(ctx)
        assert ctx.error_category == HEADER_ONLY_INPUT

    @pytest.mark.asyncio
    async def test_preflight_multi_cu_no_build_raises(self, tmp_path):
        from app.workflow_engine.context import WorkflowContext
        from app.workflow_engine.states import handle_preflight

        ws = tmp_path / "workspace"
        for d in ("input", "generated", "logs", "artifacts", "reports", "exports"):
            (ws / d).mkdir(parents=True)
        (ws / "input" / "a.cu").write_text(SAMPLE_CUDA, encoding="utf-8")
        (ws / "input" / "b.cu").write_text(SAMPLE_CUDA, encoding="utf-8")

        ctx = WorkflowContext(migration_id="test-preflight-multi", workspace_path=str(ws))
        with pytest.raises(RuntimeError, match="No executable entry point"):
            await handle_preflight(ctx)
        assert ctx.error_category == NO_ENTRYPOINT

    @pytest.mark.asyncio
    async def test_preflight_single_cu_fails_env(self, tmp_path):
        """Single .cu passes project scan but fails at env diagnostics."""
        from app.workflow_engine.context import WorkflowContext
        from app.workflow_engine.states import handle_preflight

        ws = tmp_path / "workspace"
        for d in ("input", "generated", "logs", "artifacts", "reports", "exports"):
            (ws / d).mkdir(parents=True)
        (ws / "input" / "kernel.cu").write_text(SAMPLE_CUDA, encoding="utf-8")

        ctx = WorkflowContext(migration_id="test-preflight-ok", workspace_path=str(ws))
        with pytest.raises(RuntimeError):
            await handle_preflight(ctx)
        assert ctx.error_category not in (NO_PROJECT_FILES, NON_CUDA_CPP_PROJECT, HEADER_ONLY_INPUT)
        assert ctx.project_scan is not None
        assert ctx.project_scan["compile_strategy"] == "generated_single_file_makefile"

    @pytest.mark.asyncio
    async def test_preflight_existing_hip_passes_scan(self, tmp_path):
        """Existing HIP project passes project scan, fails at env diagnostics."""
        from app.workflow_engine.context import WorkflowContext
        from app.workflow_engine.states import handle_preflight

        ws = tmp_path / "workspace"
        for d in ("input", "generated", "logs", "artifacts", "reports", "exports"):
            (ws / d).mkdir(parents=True)
        (ws / "input" / "kernel.hip").write_text(SAMPLE_HIP, encoding="utf-8")

        ctx = WorkflowContext(migration_id="test-preflight-hip", workspace_path=str(ws))
        with pytest.raises(RuntimeError):
            await handle_preflight(ctx)
        assert ctx.error_category != EXISTING_HIP_PROJECT
        assert ctx.project_scan is not None
        assert ctx.project_scan["category"] == EXISTING_HIP_PROJECT

    @pytest.mark.asyncio
    async def test_preflight_sets_project_scan_on_context(self, tmp_path):
        from app.workflow_engine.context import WorkflowContext
        from app.workflow_engine.states import handle_preflight

        ws = tmp_path / "workspace"
        for d in ("input", "generated", "logs", "artifacts", "reports", "exports"):
            (ws / d).mkdir(parents=True)
        (ws / "input" / "kernel.cu").write_text(SAMPLE_CUDA, encoding="utf-8")

        ctx = WorkflowContext(migration_id="test-preflight-scan", workspace_path=str(ws))
        try:
            await handle_preflight(ctx)
        except RuntimeError:
            pass
        assert ctx.project_scan is not None
        assert "cu_files" in ctx.project_scan


# ── Entrypoint detection tests ───────────────────────────────────────────

WITH_MAIN = "int main(int argc, char **argv) { return 0; }\n"
WITH_VOID_MAIN = "void main(void) { }\n"
COMMENTED_MAIN = "// int main() { return 0; }\n"
BLOCK_COMMENT_MAIN = "/*\nint main() { return 0; }\n*/\n"
HELPER = "#include <iostream>\nvoid helper() { }\n"

SAMPLE_CUDA_WITH_MAIN = "#include <cuda_runtime.h>\n" + WITH_MAIN
SAMPLE_HIP_WITH_MAIN = "#include <hip/hip_runtime.h>\n" + WITH_MAIN


class TestEntrypointDetection:
    def test_detects_main_in_single_file(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.cu": SAMPLE_CUDA_WITH_MAIN})
        files = [f for f in d.rglob("*") if f.is_file()]
        eps = _find_entrypoints(files)
        assert len(eps) == 1

    def test_detects_void_main(self, tmp_path):
        d = _make_input(tmp_path, {"main.cu": WITH_VOID_MAIN})
        files = [f for f in d.rglob("*") if f.is_file()]
        eps = _find_entrypoints(files)
        assert len(eps) == 1

    def test_multiple_mains_detected(self, tmp_path):
        d = _make_input(tmp_path, {"a.cu": SAMPLE_CUDA_WITH_MAIN, "b.cu": SAMPLE_CUDA_WITH_MAIN})
        files = [f for f in d.rglob("*") if f.is_file()]
        eps = _find_entrypoints(files)
        assert len(eps) == 2

    def test_no_main_detected(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.cu": SAMPLE_CUDA})
        files = [f for f in d.rglob("*") if f.is_file()]
        eps = _find_entrypoints(files)
        assert len(eps) == 0

    def test_ignores_commented_main(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.cu": COMMENTED_MAIN})
        files = [f for f in d.rglob("*") if f.is_file()]
        eps = _find_entrypoints(files)
        assert len(eps) == 0

    def test_ignores_block_comment_main(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.cu": BLOCK_COMMENT_MAIN})
        files = [f for f in d.rglob("*") if f.is_file()]
        eps = _find_entrypoints(files)
        assert len(eps) == 0


# ── New compile strategy tests ────────────────────────────────────────────

class TestNewCompileStrategies:
    def test_single_cu_generated_single(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.cu": SAMPLE_CUDA})
        scan = scan_project(d)
        assert scan["compile_strategy"] == "generated_single_file_makefile"

    def test_single_hip_generated_existing(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.hip": SAMPLE_HIP})
        scan = scan_project(d)
        assert scan["compile_strategy"] == "generated_existing_hip_makefile"

    def test_multi_cu_one_main_generated_multi(self, tmp_path):
        d = _make_input(tmp_path, {"main.cu": SAMPLE_CUDA_WITH_MAIN, "util.cu": SAMPLE_CUDA})
        scan = scan_project(d)
        assert scan["compile_strategy"] == "generated_multi_file_makefile"
        assert scan["entrypoint_count"] == 1

    def test_multi_cu_two_mains_fails(self, tmp_path):
        d = _make_input(tmp_path, {"a.cu": SAMPLE_CUDA_WITH_MAIN, "b.cu": SAMPLE_CUDA_WITH_MAIN})
        scan = scan_project(d)
        assert scan["entrypoint_count"] == 2
        assert scan["compile_strategy"] == "fail_preflight"
        # MULTIPLE_ENTRYPOINTS is set by handle_preflight, not scan_project

    def test_mixed_cu_hip_one_main_generated_mixed(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.cu": SAMPLE_CUDA_WITH_MAIN, "lib.hip": SAMPLE_HIP})
        scan = scan_project(d)
        assert scan["compile_strategy"] == "generated_mixed_makefile"
        assert scan["entrypoint_count"] == 1

    def test_multi_cu_no_main_no_entrypoint(self, tmp_path):
        d = _make_input(tmp_path, {"a.cu": SAMPLE_CUDA, "b.cu": SAMPLE_CUDA})
        scan = scan_project(d)
        assert scan["entrypoint_count"] == 0
        assert scan["compile_strategy"] == "fail_preflight"
        # NO_ENTRYPOINT is set by handle_preflight, not scan_project

    def test_multi_cpp_no_main_no_entrypoint(self, tmp_path):
        d = _make_input(tmp_path, {"a.cpp": HELPER, "b.cpp": HELPER})
        scan = scan_project(d)
        assert scan["entrypoint_count"] == 0
        assert scan["compile_strategy"] == "fail_preflight"
        assert scan["category"] == NON_CUDA_CPP_PROJECT

    def test_multi_cu_one_main_with_cpp_generated_multi(self, tmp_path):
        d = _make_input(tmp_path, {"main.cu": SAMPLE_CUDA_WITH_MAIN, "utils.cpp": HELPER})
        scan = scan_project(d)
        assert scan["compile_strategy"] == "generated_multi_file_makefile"
        assert scan["entrypoint_count"] == 1

    def test_makefile_not_overwritten(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.cu": SAMPLE_CUDA, "Makefile": MAKEFILE})
        scan = scan_project(d)
        assert scan["compile_strategy"] == "makefile"
        assert scan["has_build_system"] is True
        assert scan["build_system_detected"] == "makefile"

    def test_cmake_not_overwritten(self, tmp_path):
        d = _make_input(tmp_path, {"kernel.cu": SAMPLE_CUDA, "CMakeLists.txt": MAKEFILE})
        scan = scan_project(d)
        assert scan["compile_strategy"] == "cmake"
        assert scan["has_build_system"] is True
        assert scan["build_system_detected"] == "cmake"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
