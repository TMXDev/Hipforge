#pragma once

#include <cuda_runtime.h>

namespace hipforge::level5::algorithms {

void launch_image_blur(const float* input, float* output, int width, int height);
void launch_heat_step(const float* current, float* next, int width, int height, float alpha);
void launch_csr_spmv(const int* row_offsets, const int* columns, const float* values, const float* x, float* y, int rows);
void launch_monte_carlo_pi(unsigned int* hits, int samples_per_thread, int thread_count, unsigned int seed);
void launch_affine_relu(const float* input, const float* weights, const float* bias, float* output, int batch, int in_features, int out_features);
void launch_particle_integrate(float4* positions, float4* velocities, float dt, int count);

}  // namespace hipforge::level5::algorithms

