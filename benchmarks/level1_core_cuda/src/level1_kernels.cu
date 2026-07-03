#include "hipforge_level1/kernels.cuh"

#include "hipforge_level1/cuda_check.hpp"

namespace hipforge::level1::kernels {
namespace {

__global__ void vector_add_kernel(const float* a, const float* b, float* out, int count) {
  const int index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index < count) {
    out[index] = a[index] + b[index];
  }
}

__global__ void reduce_sum_kernel(const float* input, float* partials, int element_count) {
  __shared__ float scratch[kReductionBlockSize];

  const int thread_index = threadIdx.x;
  const int first = blockIdx.x * (blockDim.x * 2) + threadIdx.x;
  const int second = first + blockDim.x;

  float sum = 0.0f;
  if (first < element_count) {
    sum += input[first];
  }
  if (second < element_count) {
    sum += input[second];
  }

  scratch[thread_index] = sum;
  __syncthreads();

  for (int stride = blockDim.x / 2; stride > 0; stride >>= 1) {
    if (thread_index < stride) {
      scratch[thread_index] += scratch[thread_index + stride];
    }
    __syncthreads();
  }

  if (thread_index == 0) {
    partials[blockIdx.x] = scratch[0];
  }
}

__global__ void exclusive_scan_1024_kernel(const int* input, int* output) {
  __shared__ int scratch[kScanElements];

  const int first = threadIdx.x;
  const int second = threadIdx.x + kScanThreads;

  scratch[first] = input[first];
  scratch[second] = input[second];

  int offset = 1;
  for (int active = kScanElements >> 1; active > 0; active >>= 1) {
    __syncthreads();
    if (threadIdx.x < active) {
      const int ai = offset * ((threadIdx.x << 1) + 1) - 1;
      const int bi = offset * ((threadIdx.x << 1) + 2) - 1;
      scratch[bi] += scratch[ai];
    }
    offset <<= 1;
  }

  if (threadIdx.x == 0) {
    scratch[kScanElements - 1] = 0;
  }

  for (int active = 1; active < kScanElements; active <<= 1) {
    offset >>= 1;
    __syncthreads();
    if (threadIdx.x < active) {
      const int ai = offset * ((threadIdx.x << 1) + 1) - 1;
      const int bi = offset * ((threadIdx.x << 1) + 2) - 1;
      const int saved = scratch[ai];
      scratch[ai] = scratch[bi];
      scratch[bi] += saved;
    }
  }

  __syncthreads();
  output[first] = scratch[first];
  output[second] = scratch[second];
}

__global__ void histogram_u8_kernel(const unsigned char* input,
                                    unsigned int* bins,
                                    int element_count) {
  __shared__ unsigned int local_bins[kHistogramBins];

  for (int bin = threadIdx.x; bin < kHistogramBins; bin += blockDim.x) {
    local_bins[bin] = 0;
  }
  __syncthreads();

  for (int index = blockIdx.x * blockDim.x + threadIdx.x; index < element_count;
       index += blockDim.x * gridDim.x) {
    atomicAdd(&local_bins[static_cast<int>(input[index])], 1U);
  }
  __syncthreads();

  for (int bin = threadIdx.x; bin < kHistogramBins; bin += blockDim.x) {
    const unsigned int count = local_bins[bin];
    if (count > 0) {
      atomicAdd(&bins[bin], count);
    }
  }
}

__global__ void matrix_multiply_tiled_kernel(const float* a,
                                             const float* b,
                                             float* c,
                                             int matrix_size) {
  __shared__ float tile_a[kMatrixTile][kMatrixTile];
  __shared__ float tile_b[kMatrixTile][kMatrixTile];

  const int row = blockIdx.y * kMatrixTile + threadIdx.y;
  const int column = blockIdx.x * kMatrixTile + threadIdx.x;

  float accumulator = 0.0f;
  for (int tile = 0; tile < matrix_size; tile += kMatrixTile) {
    const int tiled_column = tile + threadIdx.x;
    const int tiled_row = tile + threadIdx.y;

    tile_a[threadIdx.y][threadIdx.x] =
        (row < matrix_size && tiled_column < matrix_size) ? a[row * matrix_size + tiled_column]
                                                          : 0.0f;
    tile_b[threadIdx.y][threadIdx.x] =
        (tiled_row < matrix_size && column < matrix_size) ? b[tiled_row * matrix_size + column]
                                                          : 0.0f;
    __syncthreads();

    for (int k = 0; k < kMatrixTile; ++k) {
      accumulator += tile_a[threadIdx.y][k] * tile_b[k][threadIdx.x];
    }
    __syncthreads();
  }

  if (row < matrix_size && column < matrix_size) {
    c[row * matrix_size + column] = accumulator;
  }
}

__global__ void shared_window_average_kernel(const float* input, float* output, int count) {
  __shared__ float tile[kStencilBlockSize + 2];

  const int base = blockIdx.x * blockDim.x;
  const int global = base + threadIdx.x;
  const int local = threadIdx.x + 1;

  const int clamped_center = (global < count) ? global : (count - 1);
  tile[local] = input[clamped_center];

  if (threadIdx.x == 0) {
    const int left = (base > 0) ? (base - 1) : 0;
    tile[0] = input[left];
  }

  if (threadIdx.x == blockDim.x - 1) {
    const int right_candidate = base + blockDim.x;
    const int right = (right_candidate < count) ? right_candidate : (count - 1);
    tile[local + 1] = input[right];
  }

  __syncthreads();

  if (global < count) {
    output[global] = (tile[local - 1] + tile[local] + tile[local + 1]) / 3.0f;
  }
}

__global__ void unified_scale_kernel(float* values, float scale, int count) {
  const int index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index < count) {
    values[index] *= scale;
  }
}

}  // namespace

int reduction_partial_count(int element_count) {
  const int elements_per_block = kReductionBlockSize * 2;
  return (element_count + elements_per_block - 1) / elements_per_block;
}

void launch_vector_add(const float* a, const float* b, float* out, int count, cudaStream_t stream) {
  const int blocks = (count + kVectorBlockSize - 1) / kVectorBlockSize;
  vector_add_kernel<<<blocks, kVectorBlockSize, 0, stream>>>(a, b, out, count);
  CUDA_CHECK(cudaPeekAtLastError());
}

void launch_reduce_sum(const float* input, float* partials, int element_count, cudaStream_t stream) {
  const int blocks = reduction_partial_count(element_count);
  reduce_sum_kernel<<<blocks, kReductionBlockSize, 0, stream>>>(input, partials, element_count);
  CUDA_CHECK(cudaPeekAtLastError());
}

void launch_exclusive_scan_1024(const int* input, int* output, cudaStream_t stream) {
  exclusive_scan_1024_kernel<<<1, kScanThreads, 0, stream>>>(input, output);
  CUDA_CHECK(cudaPeekAtLastError());
}

void launch_histogram_u8(const unsigned char* input,
                         unsigned int* bins,
                         int element_count,
                         cudaStream_t stream) {
  const int blocks = 120;
  histogram_u8_kernel<<<blocks, kHistogramBlockSize, 0, stream>>>(input, bins, element_count);
  CUDA_CHECK(cudaPeekAtLastError());
}

void launch_matrix_multiply_tiled(const float* a,
                                  const float* b,
                                  float* c,
                                  int matrix_size,
                                  cudaStream_t stream) {
  const dim3 threads(kMatrixTile, kMatrixTile);
  const dim3 blocks((matrix_size + kMatrixTile - 1) / kMatrixTile,
                    (matrix_size + kMatrixTile - 1) / kMatrixTile);
  matrix_multiply_tiled_kernel<<<blocks, threads, 0, stream>>>(a, b, c, matrix_size);
  CUDA_CHECK(cudaPeekAtLastError());
}

void launch_shared_window_average(const float* input, float* output, int count, cudaStream_t stream) {
  const int blocks = (count + kStencilBlockSize - 1) / kStencilBlockSize;
  shared_window_average_kernel<<<blocks, kStencilBlockSize, 0, stream>>>(input, output, count);
  CUDA_CHECK(cudaPeekAtLastError());
}

void launch_unified_scale(float* values, float scale, int count, cudaStream_t stream) {
  const int blocks = (count + kVectorBlockSize - 1) / kVectorBlockSize;
  unified_scale_kernel<<<blocks, kVectorBlockSize, 0, stream>>>(values, scale, count);
  CUDA_CHECK(cudaPeekAtLastError());
}

}  // namespace hipforge::level1::kernels
