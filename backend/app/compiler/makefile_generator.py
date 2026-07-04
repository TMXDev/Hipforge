import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("makefile_generator")

MAKEFILE_TEMPLATE = """# HIPForge Auto-Generated Build Plan
# This file is regenerated on each migration run — do not edit.
# Generated from project scan: {strategy}
HIPCC ?= hipcc
ARCH ?= {arch}
CXXFLAGS ?= -O3
TARGET ?= output

SOURCES = {sources}

INCLUDES = {includes}

$(TARGET): $(SOURCES)
\t$(HIPCC) --offload-arch=$(ARCH) $(CXXFLAGS) $(INCLUDES) $(SOURCES) -o $(TARGET)

.PHONY: clean
clean:
\trm -f $(TARGET)
"""


def _relative_sources(scan: Dict, input_dir: Path) -> list:
    sources = []
    for f in scan.get("cu_files", []):
        p = Path(f)
        try:
            rel = p.relative_to(input_dir)
        except ValueError:
            rel = Path(p.name)
        rel = rel.with_suffix(".hip")
        sources.append(str(rel).replace("\\", "/"))
    for f in scan.get("hip_files", []):
        p = Path(f)
        try:
            rel = p.relative_to(input_dir)
        except ValueError:
            rel = Path(p.name)
        sources.append(str(rel).replace("\\", "/"))
    for f in scan.get("cpp_files", []):
        p = Path(f)
        try:
            rel = p.relative_to(input_dir)
        except ValueError:
            rel = Path(p.name)
        sources.append(str(rel).replace("\\", "/"))
    sources = sorted(set(sources))
    return sources


def generate_makefile_content(
    scan: Dict,
    target_arch: str = "gfx90a",
    input_dir: Path = None,
) -> str:
    if input_dir is None:
        input_dir = Path("input")
    sources = _relative_sources(scan, input_dir)
    includes = "-I. -I../input"
    strategy = scan.get("compile_strategy", "unknown")
    return MAKEFILE_TEMPLATE.format(
        strategy=strategy,
        arch=target_arch,
        sources=" \\\n\t".join(sources) if sources else "",
        includes=includes,
    )


def write_generated_makefile(
    workspace_path: Path,
    scan: Dict,
    target_arch: str = "gfx90a",
    input_dir: Path = None,
) -> Optional[Path]:
    generated_dir = workspace_path / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    if (generated_dir / "Makefile").exists() or (generated_dir / "makefile").exists():
        logger.info("[MAKEFILE] User Makefile found in generated/; skipping generated build plan.")
        return None

    if input_dir is None:
        input_dir = workspace_path / "input"

    content = generate_makefile_content(scan, target_arch, input_dir)
    out_path = generated_dir / "Makefile.hipforge"
    out_path.write_text(content, encoding="utf-8")
    logger.info("[MAKEFILE] Generated build plan: %s (%d sources)", out_path, len(scan.get("cu_files", [])) + len(scan.get("hip_files", [])) + len(scan.get("cpp_files", [])))
    return out_path
