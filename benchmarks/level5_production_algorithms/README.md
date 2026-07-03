# HIPForge Level 5: Production Algorithm Benchmark

This benchmark collects realistic GPU kernels from production domains: image filtering, finite-difference updates, sparse matrix-vector multiply, Monte Carlo simulation, neural-network activation, and particle integration.

## Build Instructions

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=70
cmake --build build --config Release
./build/level5_production_algorithms
```

## Expected Output

```text
HIPForge Level 5 Production Algorithm Benchmark
[PASS] image_processing
[PASS] finite_difference
[PASS] sparse_matrix
[PASS] monte_carlo
[PASS] neural_layer
[PASS] particle_system
ALL LEVEL 5 CUDA CHECKS PASSED
```

## Features Exercised

- 2D image convolution
- Finite-difference stencil update
- CSR sparse matrix-vector multiply
- Monte Carlo simulation with per-thread RNG
- Neural network affine/ReLU layer
- Particle integration
- Mixed integer and floating point kernels
- Algorithm-specific validation tolerances

## Estimated Migration Difficulty

HIPIFY: 7/10, Compiler: 7/10, AI Repair: 8/10, Human Engineer: 6/10.

