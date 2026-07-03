#include "hipforge_level6/extreme.hpp"

namespace hipforge::level6::deep::runtime::kernels {
namespace {

constexpr int kBlock = 128;
__constant__ float kCoefficients[8];

using UnaryOp = float (*)(float);

__device__ float square_op(float x) {
  return x * x;
}

__device__ float cube_op(float x) {
  return x * x * x;
}

__device__ UnaryOp kDeviceOps[] = {square_op, cube_op};

HF6_DECLARE_BINARY_KERNEL(macro_binary, Operation::Add, add)
HF6_DECLARE_BINARY_KERNEL(macro_binary, Operation::Multiply, multiply)
HF6_DECLARE_BINARY_KERNEL(macro_binary, Operation::Clamp, clamp)

__global__ void coefficient_pipeline_kernel(const float* input, float* output, int count) {
  const int index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index < count) {
    float value = input[index];
    #pragma unroll
    for (int i = 0; i < 4; ++i) {
      value = value * kCoefficients[i] + kCoefficients[i + 4];
    }
    output[index] = value + static_cast<float>(StaticFactorial<3>::value);
  }
}

__global__ void function_pointer_dispatch_kernel(const float* input, float* output, int count, int op_index) {
  const int index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index < count) {
    const int selected = device_math::clamp(op_index, 0, 1);
    output[index] = kDeviceOps[selected](input[index]);
  }
}

}  // namespace

void upload_coefficients(const float* coeffs, int count) {
  HF6_CHECK(cudaMemcpyToSymbol(kCoefficients, coeffs, count * sizeof(float), 0, cudaMemcpyHostToDevice));
}

void launch_macro_pipeline(const float* a, const float* b, float* out, int count, cudaStream_t stream) {
  macro_binary_add_kernel<<<HF6_LAUNCH_GRID(count, kBlock), kBlock, 0, stream>>>(a, b, out, count);
  HF6_CHECK(cudaPeekAtLastError());
  macro_binary_clamp_kernel<<<HF6_LAUNCH_GRID(count, kBlock), kBlock, 0, stream>>>(out, b, out, count);
  HF6_CHECK(cudaPeekAtLastError());
}

void launch_allocator_pipeline(const float* input, float* output, int count, cudaStream_t stream) {
  coefficient_pipeline_kernel<<<HF6_LAUNCH_GRID(count, kBlock), kBlock, 0, stream>>>(input, output, count);
  HF6_CHECK(cudaPeekAtLastError());
}

void launch_function_pointer_dispatch(const float* input, float* output, int count, int op_index, cudaStream_t stream) {
  function_pointer_dispatch_kernel<<<HF6_LAUNCH_GRID(count, kBlock), kBlock, 0, stream>>>(input, output, count, op_index);
  HF6_CHECK(cudaPeekAtLastError());
}

}  // namespace hipforge::level6::deep::runtime::kernels

