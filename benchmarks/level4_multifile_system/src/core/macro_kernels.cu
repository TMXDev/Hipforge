#include "hipforge_level4/math/vector_ops.cuh"

namespace hipforge::level4::math {
namespace {

#define HIPFORGE_L4_DEFINE_AXPY_KERNEL(TYPE, SUFFIX)                                  \
  __global__ void macro_axpy_##SUFFIX##_kernel(const TYPE* x, const TYPE* y, TYPE* out, \
                                               TYPE alpha, int count) {               \
    const int index = blockIdx.x * blockDim.x + threadIdx.x;                          \
    if (index < count) {                                                              \
      out[index] = alpha * x[index] + y[index];                                       \
    }                                                                                 \
  }

HIPFORGE_L4_DEFINE_AXPY_KERNEL(float, float)
HIPFORGE_L4_DEFINE_AXPY_KERNEL(double, double)

}  // namespace

void launch_macro_axpy_float(const float* x, const float* y, float* out, float alpha, int count, cudaStream_t stream) {
  const int blocks = (count + config::kBlockSize - 1) / config::kBlockSize;
  macro_axpy_float_kernel<<<blocks, config::kBlockSize, 0, stream>>>(x, y, out, alpha, count);
  L4_CUDA_CHECK(cudaPeekAtLastError());
}

void launch_macro_axpy_double(const double* x, const double* y, double* out, double alpha, int count, cudaStream_t stream) {
  const int blocks = (count + config::kBlockSize - 1) / config::kBlockSize;
  macro_axpy_double_kernel<<<blocks, config::kBlockSize, 0, stream>>>(x, y, out, alpha, count);
  L4_CUDA_CHECK(cudaPeekAtLastError());
}

}  // namespace hipforge::level4::math

