#pragma once

#include <cuda_runtime.h>

namespace hipforge::level2::kernels {

constexpr int kWarpThreads = 256;
constexpr int kCooperativeThreads = 256;
constexpr int kGraphThreads = 256;
constexpr int kConvolutionRadius = 1;
constexpr int kConvolutionDiameter = 3;
constexpr int kConvolutionCoefficients = kConvolutionDiameter * kConvolutionDiameter;

int warp_partial_count(int element_count);
int cooperative_partial_count(int element_count);

void upload_convolution_filter(const float* filter);

void launch_warp_shuffle_reduce(const float* input,
                                float* partials,
                                int element_count,
                                cudaStream_t stream);

void launch_cooperative_dynamic_reduce(const float* input,
                                       float* block_sums,
                                       float* global_sum,
                                       int element_count,
                                       cudaStream_t stream);

void launch_texture_surface_convolution(cudaTextureObject_t input_texture,
                                        cudaSurfaceObject_t output_surface,
                                        int width,
                                        int height,
                                        cudaStream_t stream);

void launch_graph_transform(const float* input,
                            float* output,
                            float scale,
                            float bias,
                            int element_count,
                            cudaStream_t stream);

}  // namespace hipforge::level2::kernels

