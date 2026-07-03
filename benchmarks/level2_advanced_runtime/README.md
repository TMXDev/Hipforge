# HIPForge Level 2: Advanced CUDA Runtime Benchmark

This project targets CUDA runtime features that often migrate incorrectly even when simple kernels translate cleanly. It uses modern CUDA object APIs for textures, surfaces, graphs, streams, events, pinned transfers, dynamic shared memory, constant memory, cooperative groups, warp intrinsics, and atomics.

The code is intentionally organized as a small production component: host-side RAII wrappers own runtime resources, kernels are hidden behind launch functions, and every benchmark validates numerical behavior.

## Folder Structure

```text
level2_advanced_runtime/
  CMakeLists.txt
  README.md
  metadata.json
  include/
    hipforge_level2/
      advanced_kernels.cuh
      runtime.hpp
  src/
    advanced_kernels.cu
    main.cu
```

## Build Instructions

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=70
cmake --build build --config Release
./build/level2_advanced_runtime
```

For Windows with Ninja:

```powershell
cmake -S . -B build -G "Ninja" -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=70
cmake --build build --config Release
.\build\level2_advanced_runtime.exe
```

Set `CMAKE_CUDA_ARCHITECTURES` for the target NVIDIA GPU, for example `75`, `80`, `86`, or `89`.

## Expected Output

Timings vary by device. A successful run should look like:

```text
HIPForge Level 2 Advanced CUDA Runtime Benchmark
Device: <GPU name>
[PASS] warp_shuffle_reduction ...
[PASS] cooperative_groups_dynamic_shared ...
[PASS] constant_texture_surface ...
[PASS] multistream_async_graphs ...
ALL LEVEL 2 CUDA CHECKS PASSED
```

## CUDA Features Exercised

- Warp shuffle intrinsics with `__shfl_down_sync`
- Cooperative Groups `thread_block`
- Constant memory and `cudaMemcpyToSymbol`
- Texture objects backed by CUDA arrays
- Surface objects and `surf2Dwrite`
- Atomics in block-level reductions
- Dynamic shared memory launch sizing
- Multiple nonblocking streams
- CUDA events for timing
- Pinned host memory
- Asynchronous `cudaMemcpyAsync`
- CUDA stream capture, graph instantiation, and graph launch
- Cross-file launch wrappers

## Difficulty Rating

Level 2 of 6. The algorithms remain validation-oriented, but the runtime API surface is substantially wider than Level 1.

## Estimated Migration Difficulty

| Target | Score | Notes |
| --- | ---: | --- |
| HIPIFY | 6/10 | Texture/surface objects, graph APIs, cooperative groups, constant symbols, and stream capture require precise API mapping. |
| Compiler | 6/10 | Header and library translation must preserve CUDA object types, launch wrappers, graph instantiation overloads, and dynamic shared memory. |
| AI Repair | 7/10 | Repair agents may replace texture/surface objects with raw pointers, remove graph capture, mishandle `cudaMemcpyToSymbol`, or change synchronization semantics. |
| Human Engineer | 5/10 | A GPU engineer can migrate this, but semantic validation requires attention to object lifetime, stream ordering, and image coordinate conventions. |

## Failure Modes This Project Is Designed To Expose

- Leaving `cudaTextureObject_t`, `cudaSurfaceObject_t`, or CUDA array APIs unmigrated
- Incorrect `cudaMemcpyToSymbol` handling for constant memory
- Broken `cooperative_groups` include or namespace conversion
- Mis-translated `__shfl_down_sync` masks
- Dynamic shared memory launch arguments dropped or reordered
- Incorrect graph instantiation overload after CUDA-to-HIP conversion
- Stream capture replaced by immediate execution
- Pinned async transfer degraded to synchronous pageable transfer
- Surface write byte addressing converted incorrectly
- Texture coordinate behavior changed during migration
- Event timing moved outside the actual asynchronous work

