# HIPForge Level 1: Core CUDA Runtime Benchmark

This project is a production-styled Level 1 CUDA migration benchmark. It intentionally combines simple kernels with real host-side resource management, stream usage, timing events, pinned memory, and unified memory so migration tools must preserve runtime behavior instead of only translating isolated kernels.

## Folder Structure

```text
level1_core_cuda/
  CMakeLists.txt
  README.md
  metadata.json
  include/
    hipforge_level1/
      cuda_check.hpp
      kernels.cuh
  src/
    level1_kernels.cu
    main.cu
```

## Build Instructions

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=70
cmake --build build --config Release
./build/level1_core_cuda
```

For Visual Studio generators on Windows, run:

```powershell
cmake -S . -B build -G "Ninja" -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=70
cmake --build build --config Release
.\build\level1_core_cuda.exe
```

Change `CMAKE_CUDA_ARCHITECTURES` to match the available NVIDIA GPU, for example `75`, `80`, `86`, or `89`.

## Expected Output

Timings vary by GPU, but a successful run should look like this:

```text
HIPForge Level 1 CUDA Core Benchmark
Device: <GPU name>
[PASS] vector_add ...
[PASS] reduction ...
[PASS] prefix_sum ...
[PASS] histogram ...
[PASS] matrix_multiplication ...
[PASS] shared_memory_stencil ...
[PASS] streams_events_pinned_memory ...
[PASS] unified_memory ...
ALL LEVEL 1 CUDA CHECKS PASSED
```

## CUDA Features Exercised

- Vector add kernel launch and validation
- Multi-pass block reduction
- Single-block exclusive prefix sum
- Histogram with shared-memory accumulation and global atomics
- Tiled matrix multiplication using shared memory
- Dedicated shared-memory stencil with halo loading
- Multiple streams with asynchronous copies
- CUDA events for timing
- Pinned host memory with `cudaMallocHost`
- Unified memory with `cudaMallocManaged`
- Cross-file kernel organization
- Runtime API error checking and RAII resource wrappers

## Difficulty Rating

Level 1 of 6. The kernels are conceptually simple, but the project is deliberately structured like deployable CUDA code rather than a single-file sample.

## Estimated Migration Difficulty

| Target | Score | Notes |
| --- | ---: | --- |
| HIPIFY | 3/10 | Mostly direct runtime and kernel syntax conversion, but streams, events, pinned memory, managed memory, and namespaced wrappers must be preserved. |
| Compiler | 3/10 | Should compile if include paths, CUDA/HIP runtime headers, and launch syntax are translated correctly. |
| AI Repair | 4/10 | Repair loops may over-edit wrappers, remove synchronization, or mis-handle timing/event semantics. |
| Human Engineer | 2/10 | A GPU engineer should migrate this quickly, but validation makes subtle runtime mistakes visible. |

## Failure Modes This Project Is Designed To Expose

- Missing CUDA runtime API replacements in helper wrappers
- Incorrect handling of `.cuh` headers and cross-file kernel declarations
- Broken kernel launch translation inside wrapper functions
- Lost stream arguments during migration
- Replacing pinned-memory or unified-memory APIs with ordinary allocation
- Incorrect event timing migration
- Off-by-one bugs in shared-memory halo code after patch generation
- Silent validation failures caused by changed synchronization behavior

