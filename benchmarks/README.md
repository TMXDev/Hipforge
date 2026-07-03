# HIPForge CUDA Migration Benchmarks

This directory contains adversarial CUDA projects intended to exercise CUDA-to-HIP migration pipelines.

Each level is generated as a standalone project with its own build metadata, validation output, and migration difficulty notes.

Generated projects:

- `level1_core_cuda`: core CUDA kernels and runtime APIs.
- `level2_advanced_runtime`: advanced CUDA runtime features, including cooperative groups, texture/surface objects, constant memory, dynamic shared memory, events, streams, async copies, and CUDA graphs.
- `level3_modern_cuda_cpp`: C++17 templates, RAII, move semantics, smart pointers, and class hierarchies.
- `level4_multifile_system`: nested includes, static library targets, macro-generated kernels, and cross-file launches.
- `level5_production_algorithms`: production-style image, stencil, sparse, Monte Carlo, neural, and particle kernels.
- `level6_extreme_migration_stress`: macro-heavy launch wrappers, custom allocators, device function pointers, constexpr recursion, and nested namespaces.

Current autonomous QA target set: `level2_advanced_runtime` through `level6_extreme_migration_stress`.
