#include "hipforge_level5/algorithms.cuh"

#include "hipforge_level5/runtime.hpp"

namespace hipforge::level5::algorithms {
namespace {

constexpr int kBlock = 256;

__device__ int clampi(int value, int lo, int hi) {
  return value < lo ? lo : (value > hi ? hi : value);
}

__device__ unsigned int xorshift32(unsigned int state) {
  state ^= state << 13;
  state ^= state >> 17;
  state ^= state << 5;
  return state;
}

__global__ void image_blur_kernel(const float* input, float* output, int width, int height) {
  const int x = blockIdx.x * blockDim.x + threadIdx.x;
  const int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= width || y >= height) {
    return;
  }
  float acc = 0.0f;
  for (int dy = -1; dy <= 1; ++dy) {
    for (int dx = -1; dx <= 1; ++dx) {
      const int sx = clampi(x + dx, 0, width - 1);
      const int sy = clampi(y + dy, 0, height - 1);
      acc += input[sy * width + sx];
    }
  }
  output[y * width + x] = acc / 9.0f;
}

__global__ void heat_step_kernel(const float* current, float* next, int width, int height, float alpha) {
  const int x = blockIdx.x * blockDim.x + threadIdx.x;
  const int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= width || y >= height) {
    return;
  }
  const int left = clampi(x - 1, 0, width - 1);
  const int right = clampi(x + 1, 0, width - 1);
  const int up = clampi(y - 1, 0, height - 1);
  const int down = clampi(y + 1, 0, height - 1);
  const float center = current[y * width + x];
  const float laplacian = current[y * width + left] + current[y * width + right] +
                          current[up * width + x] + current[down * width + x] - 4.0f * center;
  next[y * width + x] = center + alpha * laplacian;
}

__global__ void csr_spmv_kernel(const int* row_offsets, const int* columns, const float* values, const float* x, float* y, int rows) {
  const int row = blockIdx.x * blockDim.x + threadIdx.x;
  if (row >= rows) {
    return;
  }
  float sum = 0.0f;
  for (int offset = row_offsets[row]; offset < row_offsets[row + 1]; ++offset) {
    sum += values[offset] * x[columns[offset]];
  }
  y[row] = sum;
}

__global__ void monte_carlo_pi_kernel(unsigned int* hits, int samples_per_thread, unsigned int seed) {
  const int tid = blockIdx.x * blockDim.x + threadIdx.x;
  unsigned int state = seed ^ (tid * 747796405u + 2891336453u);
  unsigned int local_hits = 0;
  for (int i = 0; i < samples_per_thread; ++i) {
    state = xorshift32(state);
    const float x = static_cast<float>(state & 0x00FFFFFFu) / static_cast<float>(0x01000000u);
    state = xorshift32(state);
    const float y = static_cast<float>(state & 0x00FFFFFFu) / static_cast<float>(0x01000000u);
    if (x * x + y * y <= 1.0f) {
      ++local_hits;
    }
  }
  hits[tid] = local_hits;
}

__global__ void affine_relu_kernel(const float* input, const float* weights, const float* bias, float* output, int batch, int in_features, int out_features) {
  const int index = blockIdx.x * blockDim.x + threadIdx.x;
  const int total = batch * out_features;
  if (index >= total) {
    return;
  }
  const int b = index / out_features;
  const int o = index % out_features;
  float sum = bias[o];
  for (int i = 0; i < in_features; ++i) {
    sum += input[b * in_features + i] * weights[o * in_features + i];
  }
  output[index] = sum > 0.0f ? sum : 0.0f;
}

__global__ void particle_integrate_kernel(float4* positions, float4* velocities, float dt, int count) {
  const int index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index >= count) {
    return;
  }
  float4 p = positions[index];
  const float4 v = velocities[index];
  p.x += v.x * dt;
  p.y += v.y * dt;
  p.z += v.z * dt;
  positions[index] = p;
}

}  // namespace

void launch_image_blur(const float* input, float* output, int width, int height) {
  const dim3 threads(16, 16);
  const dim3 blocks((width + 15) / 16, (height + 15) / 16);
  image_blur_kernel<<<blocks, threads>>>(input, output, width, height);
  L5_CUDA_CHECK(cudaPeekAtLastError());
}

void launch_heat_step(const float* current, float* next, int width, int height, float alpha) {
  const dim3 threads(16, 16);
  const dim3 blocks((width + 15) / 16, (height + 15) / 16);
  heat_step_kernel<<<blocks, threads>>>(current, next, width, height, alpha);
  L5_CUDA_CHECK(cudaPeekAtLastError());
}

void launch_csr_spmv(const int* row_offsets, const int* columns, const float* values, const float* x, float* y, int rows) {
  const int blocks = (rows + kBlock - 1) / kBlock;
  csr_spmv_kernel<<<blocks, kBlock>>>(row_offsets, columns, values, x, y, rows);
  L5_CUDA_CHECK(cudaPeekAtLastError());
}

void launch_monte_carlo_pi(unsigned int* hits, int samples_per_thread, int thread_count, unsigned int seed) {
  const int blocks = (thread_count + kBlock - 1) / kBlock;
  monte_carlo_pi_kernel<<<blocks, kBlock>>>(hits, samples_per_thread, seed);
  L5_CUDA_CHECK(cudaPeekAtLastError());
}

void launch_affine_relu(const float* input, const float* weights, const float* bias, float* output, int batch, int in_features, int out_features) {
  const int total = batch * out_features;
  const int blocks = (total + kBlock - 1) / kBlock;
  affine_relu_kernel<<<blocks, kBlock>>>(input, weights, bias, output, batch, in_features, out_features);
  L5_CUDA_CHECK(cudaPeekAtLastError());
}

void launch_particle_integrate(float4* positions, float4* velocities, float dt, int count) {
  const int blocks = (count + kBlock - 1) / kBlock;
  particle_integrate_kernel<<<blocks, kBlock>>>(positions, velocities, dt, count);
  L5_CUDA_CHECK(cudaPeekAtLastError());
}

}  // namespace hipforge::level5::algorithms

