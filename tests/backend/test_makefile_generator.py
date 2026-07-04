from pathlib import Path
import pytest

from app.compiler.makefile_generator import (
    generate_makefile_content,
    write_generated_makefile,
)

SAMPLE_CU = "kernel.cu"
SAMPLE_HIP = "kernel.hip"
SAMPLE_CPP = "utils.cpp"
TARGET_ARCH = "gfx942"


def _make_scan(cu=None, hip=None, cpp=None, cuh=None, header=None, strategy="generated_single_file_makefile"):
    return {
        "cu_files": cu or [],
        "hip_files": hip or [],
        "cpp_files": cpp or [],
        "cuh_files": cuh or [],
        "header_files": header or [],
        "compile_strategy": strategy,
    }


class TestGenerateMakefileContent:
    def test_single_cu_content(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / SAMPLE_CU).write_text("// test", encoding="utf-8")

        scan = _make_scan(cu=[str(input_dir / SAMPLE_CU)], strategy="generated_single_file_makefile")
        content = generate_makefile_content(scan, TARGET_ARCH, input_dir)

        assert "generated_single_file_makefile" in content
        assert "gfx942" in content
        assert "kernel.hip" in content
        assert "-I." in content
        assert "-I../input" in content

    def test_single_hip_content(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / SAMPLE_HIP).write_text("// test", encoding="utf-8")

        scan = _make_scan(hip=[str(input_dir / SAMPLE_HIP)], strategy="generated_existing_hip_makefile")
        content = generate_makefile_content(scan, TARGET_ARCH, input_dir)

        assert "kernel.hip" in content
        assert "gfx942" in content
        assert "HIPCC" in content

    def test_multi_file_content(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        for name in ("main.cu", "util.cu", "helper.cpp"):
            (input_dir / name).write_text("// test", encoding="utf-8")

        cu_files = [str(input_dir / "main.cu"), str(input_dir / "util.cu")]
        cpp_files = [str(input_dir / "helper.cpp")]
        scan = _make_scan(cu=cu_files, cpp=cpp_files, strategy="generated_multi_file_makefile")
        content = generate_makefile_content(scan, TARGET_ARCH, input_dir)

        assert "main.hip" in content
        assert "util.hip" in content
        assert "helper.cpp" in content
        assert "gfx942" in content

    def test_mixed_content(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        for name in ("kernel.cu", "lib.hip"):
            (input_dir / name).write_text("// test", encoding="utf-8")

        cu_files = [str(input_dir / "kernel.cu")]
        hip_files = [str(input_dir / "lib.hip")]
        scan = _make_scan(cu=cu_files, hip=hip_files, strategy="generated_mixed_makefile")
        content = generate_makefile_content(scan, TARGET_ARCH, input_dir)

        assert "kernel.hip" in content
        assert "lib.hip" in content

    def test_no_sources_empty_sources(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        scan = _make_scan(strategy="generated_single_file_makefile")
        content = generate_makefile_content(scan, TARGET_ARCH, input_dir)
        assert "SOURCES =" in content

    def test_header_only_no_scanned_sources(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "api.h").write_text("// header", encoding="utf-8")
        scan = _make_scan(header=[str(input_dir / "api.h")], strategy="analyze_only")
        content = generate_makefile_content(scan, TARGET_ARCH, input_dir)
        assert "SOURCES =" in content


class TestWriteGeneratedMakefile:
    def test_writes_to_generated_dir(self, tmp_path):
        workspace = tmp_path / "workspace"
        (workspace / "generated").mkdir(parents=True)
        input_dir = workspace / "input"
        input_dir.mkdir()
        (input_dir / "kernel.cu").write_text("// test", encoding="utf-8")

        scan = _make_scan(
            cu=[str(input_dir / "kernel.cu")],
            strategy="generated_single_file_makefile",
        )
        result = write_generated_makefile(workspace, scan, TARGET_ARCH, input_dir)
        assert result is not None
        assert result.exists()
        assert result.name == "Makefile.hipforge"
        assert result.parent.name == "generated"

    def test_does_not_overwrite_user_makefile(self, tmp_path):
        workspace = tmp_path / "workspace"
        generated = workspace / "generated"
        generated.mkdir(parents=True)
        (generated / "Makefile").write_text("user Makefile", encoding="utf-8")
        input_dir = workspace / "input"
        input_dir.mkdir()
        (input_dir / "kernel.cu").write_text("// test", encoding="utf-8")

        scan = _make_scan(
            cu=[str(input_dir / "kernel.cu")],
            strategy="generated_single_file_makefile",
        )
        result = write_generated_makefile(workspace, scan, TARGET_ARCH, input_dir)
        assert result is None
        assert (generated / "Makefile").read_text(encoding="utf-8") == "user Makefile"

    def test_does_not_overwrite_user_makefile_lowercase(self, tmp_path):
        workspace = tmp_path / "workspace"
        generated = workspace / "generated"
        generated.mkdir(parents=True)
        (generated / "makefile").write_text("user Makefile", encoding="utf-8")
        input_dir = workspace / "input"
        input_dir.mkdir()
        (input_dir / "kernel.cu").write_text("// test", encoding="utf-8")

        scan = _make_scan(
            cu=[str(input_dir / "kernel.cu")],
            strategy="generated_single_file_makefile",
        )
        result = write_generated_makefile(workspace, scan, TARGET_ARCH, input_dir)
        assert result is None

    def test_content_is_human_readable(self, tmp_path):
        workspace = tmp_path / "workspace"
        (workspace / "generated").mkdir(parents=True)
        input_dir = workspace / "input"
        input_dir.mkdir()
        (input_dir / "kernel.cu").write_text("// test", encoding="utf-8")

        scan = _make_scan(
            cu=[str(input_dir / "kernel.cu")],
            strategy="generated_single_file_makefile",
        )
        result = write_generated_makefile(workspace, scan, TARGET_ARCH, input_dir)
        content = result.read_text(encoding="utf-8")
        assert content.startswith("# HIPForge")
        assert "HIPCC" in content
        assert "ARCH" in content
        assert "clean" in content

    def test_includes_target_arch(self, tmp_path):
        workspace = tmp_path / "workspace"
        (workspace / "generated").mkdir(parents=True)
        input_dir = workspace / "input"
        input_dir.mkdir()
        (input_dir / "kernel.cu").write_text("// test", encoding="utf-8")

        scan = _make_scan(
            cu=[str(input_dir / "kernel.cu")],
            strategy="generated_single_file_makefile",
        )
        result = write_generated_makefile(workspace, scan, TARGET_ARCH, input_dir)
        content = result.read_text(encoding="utf-8")
        assert "ARCH ?= gfx942" in content
        assert "--offload-arch=$(ARCH)" in content

    def test_is_reproducible(self, tmp_path):
        workspace = tmp_path / "workspace"
        (workspace / "generated").mkdir(parents=True)
        input_dir = workspace / "input"
        input_dir.mkdir()
        (input_dir / "kernel.cu").write_text("// test", encoding="utf-8")

        scan = _make_scan(
            cu=[str(input_dir / "kernel.cu")],
            strategy="generated_single_file_makefile",
        )
        c1 = write_generated_makefile(workspace, scan, TARGET_ARCH, input_dir).read_text(encoding="utf-8")
        c2 = write_generated_makefile(workspace, scan, TARGET_ARCH, input_dir).read_text(encoding="utf-8")
        assert c1 == c2
