#include "hipforge_level3/tensor.hpp"

#include <type_traits>

namespace hipforge::level3::kernels {
namespace {

constexpr int kBlockSize = 256;

template <typename T>
__global__ void saxpy_kernel(const T* x, const T* y, T* out, T alpha, int count) {
  const int index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index < count) {
    if constexpr (std::is_same<T, int>::value) {
      out[index] = NumericTraits<T>::scale(x[index], alpha) + y[index];
    } else {
      out[index] = alpha * x[index] + y[index];
    }
  }
}

template <typename T>
__global__ void scaled_norm_kernel(const T* x, T* partials, T scale, int count) {
  __shared__ T scratch[kBlockSize];
  const int local = threadIdx.x;
  const int index = blockIdx.x * blockDim.x + threadIdx.x;
  T value = NumericTraits<T>::zero();
  if (index < count) {
    const T scaled = NumericTraits<T>::scale(x[index], scale);
    value = scaled * scaled;
  }
  scratch[local] = value;
  __syncthreads();

  for (int stride = blockDim.x / 2; stride > 0; stride >>= 1) {
    if (local < stride) {
      scratch[local] += scratch[local + stride];
    }
    __syncthreads();
  }
  if (local == 0) {
    partials[blockIdx.x] = scratch[0];
  }
}

}  // namespace

int partial_count(int count) {
  return (count + kBlockSize - 1) / kBlockSize;
}

template <typename T>
void launch_saxpy(const T* x, const T* y, T* out, T alpha, int count, cudaStream_t stream) {
  const int blocks = (count + kBlockSize - 1) / kBlockSize;
  saxpy_kernel<T><<<blocks, kBlockSize, 0, stream>>>(x, y, out, alpha, count);
  CUDA_CHECK(cudaPeekAtLastError());
}

template <typename T>
void launch_scaled_norm(const T* x, T* partials, T scale, int count, cudaStream_t stream) {
  const int blocks = partial_count(count);
  scaled_norm_kernel<T><<<blocks, kBlockSize, 0, stream>>>(x, partials, scale, count);
  CUDA_CHECK(cudaPeekAtLastError());
}

template void launch_saxpy<float>(const float*, const float*, float*, float, int, cudaStream_t);
template void launch_saxpy<int>(const int*, const int*, int*, int, int, cudaStream_t);
template void launch_scaled_norm<float>(const float*, float*, float, int, cudaStream_t);

}  // namespace hipforge::level3::kernels
