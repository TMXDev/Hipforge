#pragma once

#include <cuda_runtime.h>

namespace hipforge::level1::kernels {

constexpr int kVectorBlockSize = 256;
constexpr int kReductionBlockSize = 256;
constexpr int kScanElements = 1024;
constexpr int kScanThreads = 512;
constexpr int kHistogramBins = 256;
constexpr int kHistogramBlockSize = 256;
constexpr int kMatrixTile = 16;
constexpr int kStencilBlockSize = 256;

int reduction_partial_count(int element_count);

void launch_vector_add(const float* a, const float* b, float* out, int count, cudaStream_t stream);

void launch_reduce_sum(const float* input, float* partials, int element_count, cudaStream_t stream);

void launch_exclusive_scan_1024(const int* input, int* output, cudaStream_t stream);

void launch_histogram_u8(const unsigned char* input,
                         unsigned int* bins,
                         int element_count,
                         cudaStream_t stream);

void launch_matrix_multiply_tiled(const float* a,
                                  const float* b,
                                  float* c,
                                  int matrix_size,
                                  cudaStream_t stream);

void launch_shared_window_average(const float* input, float* output, int count, cudaStream_t stream);

void launch_unified_scale(float* values, float scale, int count, cudaStream_t stream);

}  // namespace hipforge::level1::kernels

