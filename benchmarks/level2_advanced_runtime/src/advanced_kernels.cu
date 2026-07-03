#include "hipforge_level2/advanced_kernels.cuh"

#include "hipforge_level2/runtime.hpp"

#include <cooperative_groups.h>

namespace hipforge::level2::kernels {
namespace {

__constant__ float kConvolutionFilter[kConvolutionCoefficients];

__device__ float warp_sum(float value) {
  constexpr unsigned int kFullMask = 0xFFFFFFFFU;
  for (int offset = warpSize / 2; offset > 0; offset >>= 1) {
    value += __shfl_down_sync(kFullMask, value, offset);
  }
  return value;
}

__device__ int clamp_int(int value, int lower, int upper) {
  return value < lower ? lower : (value > upper ? upper : value);
}

__global__ void warp_shuffle_reduce_kernel(const float* input,
                                           float* partials,
                                           int element_count) {
  float thread_sum = 0.0f;
  for (int index = blockIdx.x * blockDim.x + threadIdx.x; index < element_count;
       index += blockDim.x * gridDim.x) {
    thread_sum += input[index];
  }

  const float reduced = warp_sum(thread_sum);
  const int lane = threadIdx.x & (warpSize - 1);
  const int warp_in_block = threadIdx.x / warpSize;
  const int warps_per_block = blockDim.x / warpSize;

  if (lane == 0) {
    partials[blockIdx.x * warps_per_block + warp_in_block] = reduced;
  }
}

__global__ void cooperative_dynamic_reduce_kernel(const float* input,
                                                  float* block_sums,
                                                  float* global_sum,
                                                  int element_count) {
  namespace cg = cooperative_groups;
  cg::thread_block block = cg::this_thread_block();
  extern __shared__ float scratch[];

  float local = 0.0f;
  for (int index = blockIdx.x * blockDim.x + threadIdx.x; index < element_count;
       index += blockDim.x * gridDim.x) {
    local += input[index];
  }

  scratch[threadIdx.x] = local;
  block.sync();

  for (int stride = blockDim.x / 2; stride > 0; stride >>= 1) {
    if (threadIdx.x < stride) {
      scratch[threadIdx.x] += scratch[threadIdx.x + stride];
    }
    block.sync();
  }

  if (threadIdx.x == 0) {
    block_sums[blockIdx.x] = scratch[0];
    atomicAdd(global_sum, scratch[0]);
  }
}

__global__ void texture_surface_convolution_kernel(cudaTextureObject_t input_texture,
                                                   cudaSurfaceObject_t output_surface,
                                                   int width,
                                                   int height) {
  const int x = blockIdx.x * blockDim.x + threadIdx.x;
  const int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= width || y >= height) {
    return;
  }

  float accumulator = 0.0f;
  for (int dy = -kConvolutionRadius; dy <= kConvolutionRadius; ++dy) {
    for (int dx = -kConvolutionRadius; dx <= kConvolutionRadius; ++dx) {
      const int sample_x = clamp_int(x + dx, 0, width - 1);
      const int sample_y = clamp_int(y + dy, 0, height - 1);
      const float pixel =
          tex2D<float>(input_texture, static_cast<float>(sample_x) + 0.5f,
                       static_cast<float>(sample_y) + 0.5f);
      const int filter_index = (dy + kConvolutionRadius) * kConvolutionDiameter +
                               (dx + kConvolutionRadius);
      accumulator += pixel * kConvolutionFilter[filter_index];
    }
  }

  surf2Dwrite(accumulator, output_surface, x * static_cast<int>(sizeof(float)), y);
}

__global__ void graph_transform_kernel(const float* input,
                                       float* output,
                                       float scale,
                                       float bias,
                                       int element_count) {
  for (int index = blockIdx.x * blockDim.x + threadIdx.x; index < element_count;
       index += blockDim.x * gridDim.x) {
    output[index] = input[index] * scale + bias;
  }
}

}  // namespace

int warp_partial_count(int element_count) {
  const int blocks = (element_count + kWarpThreads - 1) / kWarpThreads;
  const int warps_per_block = kWarpThreads / 32;
  return blocks * warps_per_block;
}

int cooperative_partial_count(int element_count) {
  return (element_count + kCooperativeThreads - 1) / kCooperativeThreads;
}

void upload_convolution_filter(const float* filter) {
  CUDA_CHECK(cudaMemcpyToSymbol(
      kConvolutionFilter, filter, kConvolutionCoefficients * sizeof(float), 0, cudaMemcpyHostToDevice));
}

void launch_warp_shuffle_reduce(const float* input,
                                float* partials,
                                int element_count,
                                cudaStream_t stream) {
  const int blocks = (element_count + kWarpThreads - 1) / kWarpThreads;
  warp_shuffle_reduce_kernel<<<blocks, kWarpThreads, 0, stream>>>(input, partials, element_count);
  CUDA_CHECK(cudaPeekAtLastError());
}

void launch_cooperative_dynamic_reduce(const float* input,
                                       float* block_sums,
                                       float* global_sum,
                                       int element_count,
                                       cudaStream_t stream) {
  const int blocks = cooperative_partial_count(element_count);
  const std::size_t dynamic_shared_bytes = kCooperativeThreads * sizeof(float);
  cooperative_dynamic_reduce_kernel<<<blocks, kCooperativeThreads, dynamic_shared_bytes, stream>>>(
      input, block_sums, global_sum, element_count);
  CUDA_CHECK(cudaPeekAtLastError());
}

void launch_texture_surface_convolution(cudaTextureObject_t input_texture,
                                        cudaSurfaceObject_t output_surface,
                                        int width,
                                        int height,
                                        cudaStream_t stream) {
  const dim3 threads(16, 16);
  const dim3 blocks((width + threads.x - 1) / threads.x, (height + threads.y - 1) / threads.y);
  texture_surface_convolution_kernel<<<blocks, threads, 0, stream>>>(
      input_texture, output_surface, width, height);
  CUDA_CHECK(cudaPeekAtLastError());
}

void launch_graph_transform(const float* input,
                            float* output,
                            float scale,
                            float bias,
                            int element_count,
                            cudaStream_t stream) {
  const int blocks = (element_count + kGraphThreads - 1) / kGraphThreads;
  graph_transform_kernel<<<blocks, kGraphThreads, 0, stream>>>(
      input, output, scale, bias, element_count);
  CUDA_CHECK(cudaPeekAtLastError());
}

}  // namespace hipforge::level2::kernels
