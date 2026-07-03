#include "hipforge_level4/math/vector_ops.cuh"

namespace hipforge::level4::math {
namespace {

__global__ void normalize_kernel(const float* input, float* output, float denominator, int count) {
  const int index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index < count) {
    output[index] = input[index] / denominator;
  }
}

__global__ void pack4_kernel(const float* input, float4* output, int tuple_count) {
  const int tuple = blockIdx.x * blockDim.x + threadIdx.x;
  if (tuple < tuple_count) {
    const int base = tuple * config::kVectorWidth;
    output[tuple] = make_float4(input[base], input[base + 1], input[base + 2], input[base + 3]);
  }
}

}  // namespace

void launch_cross_file_normalize(const float* input, float* output, float denominator, int count, cudaStream_t stream) {
  const int blocks = (count + config::kBlockSize - 1) / config::kBlockSize;
  normalize_kernel<<<blocks, config::kBlockSize, 0, stream>>>(input, output, denominator, count);
  L4_CUDA_CHECK(cudaPeekAtLastError());
}

void launch_cross_file_pack4(const float* input, float4* output, int tuple_count, cudaStream_t stream) {
  const int blocks = (tuple_count + config::kBlockSize - 1) / config::kBlockSize;
  pack4_kernel<<<blocks, config::kBlockSize, 0, stream>>>(input, output, tuple_count);
  L4_CUDA_CHECK(cudaPeekAtLastError());
}

}  // namespace hipforge::level4::math

