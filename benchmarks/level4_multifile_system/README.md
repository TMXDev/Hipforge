# HIPForge Level 4: Multi-File CUDA System Benchmark

This project exercises build-system migration and cross-file organization. It contains nested include directories, a static library, macro-generated kernels, configuration headers, C++ utility sources, and launches split across multiple CUDA translation units.

## Build Instructions

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=70
cmake --build build --config Release
./build/level4_multifile_system
```

## Expected Output

```text
HIPForge Level 4 Multi-File CUDA System Benchmark
[PASS] macro_generated_kernels
[PASS] cross_file_pipeline
ALL LEVEL 4 CUDA CHECKS PASSED
```

## Features Exercised

- Multi-directory source layout
- Static CUDA library linked into an executable
- Nested includes and configuration headers
- Macro-generated kernels
- Cross-file kernel launch wrappers
- CMake target propagation
- Mixed `.cpp`, `.cu`, `.cuh`, `.hpp`, and `.h` files

## Estimated Migration Difficulty

HIPIFY: 7/10, Compiler: 8/10, AI Repair: 8/10, Human Engineer: 6/10.

