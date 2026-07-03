# HIPForge Level 3: Modern CUDA C++ Benchmark

This benchmark stresses migration of C++17-heavy CUDA code. The kernels are wrapped behind templated launch APIs, host orchestration uses RAII and smart pointers, and behavior is validated through a small polymorphic benchmark harness.

## Folder Structure

```text
level3_modern_cuda_cpp/
  CMakeLists.txt
  README.md
  metadata.json
  include/hipforge_level3/
    runtime.hpp
    tensor.hpp
  src/
    main.cu
    modern_kernels.cu
```

## Build Instructions

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=70
cmake --build build --config Release
./build/level3_modern_cuda_cpp
```

## Expected Output

```text
HIPForge Level 3 Modern CUDA C++ Benchmark
[PASS] templated_saxpy
[PASS] specialized_norm
[PASS] move_only_tensor_pipeline
ALL LEVEL 3 CUDA CHECKS PASSED
```

## CUDA/C++ Features Exercised

- Class templates and explicit instantiation
- Template specialization
- `constexpr` and `if constexpr`
- RAII wrappers for device memory and streams
- Move-only GPU tensor ownership
- Host lambdas
- `std::vector`, `std::array`, `std::unique_ptr`
- Exceptions outside kernels
- Namespaces and polymorphic host-side benchmark classes
- Cross-file templated launch declarations

## Estimated Migration Difficulty

| Target | Score |
| --- | ---: |
| HIPIFY | 6/10 |
| Compiler | 6/10 |
| AI Repair | 7/10 |
| Human Engineer | 5/10 |

