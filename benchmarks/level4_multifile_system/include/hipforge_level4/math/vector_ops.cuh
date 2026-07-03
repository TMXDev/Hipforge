#pragma once

#include "hipforge_level4/config/build_config.cuh"
#include "hipforge_level4/detail/error.hpp"

namespace hipforge::level4::math {

void launch_macro_axpy_float(const float* x, const float* y, float* out, float alpha, int count, cudaStream_t stream);
void launch_macro_axpy_double(const double* x, const double* y, double* out, double alpha, int count, cudaStream_t stream);
void launch_cross_file_normalize(const float* input, float* output, float denominator, int count, cudaStream_t stream);
void launch_cross_file_pack4(const float* input, float4* output, int tuple_count, cudaStream_t stream);

}  // namespace hipforge::level4::math

