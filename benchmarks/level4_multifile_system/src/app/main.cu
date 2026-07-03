#include "hipforge_level4/detail/error.hpp"
#include "hipforge_level4/launch/launcher.hpp"
#include "hipforge_level4/math/vector_ops.cuh"
#include "hipforge_level4/utils/init.h"

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {

void require(bool condition, const char* message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

template <typename T>
void copy_to_device(T* dst, const std::vector<T>& src) {
  L4_CUDA_CHECK(cudaMemcpy(dst, src.data(), src.size() * sizeof(T), cudaMemcpyHostToDevice));
}

template <typename T>
std::vector<T> copy_to_host(const T* src, int count) {
  std::vector<T> out(count);
  L4_CUDA_CHECK(cudaMemcpy(out.data(), src, out.size() * sizeof(T), cudaMemcpyDeviceToHost));
  return out;
}

void run_macro_generated_kernels() {
  constexpr int count = 2048;
  auto x = hipforge::level4::utils::make_signal(count, 0.25f);
  auto y = hipforge::level4::utils::make_signal(count, 0.5f);
  hipforge::level4::launch::DeviceWorkspace dx(count * sizeof(float));
  hipforge::level4::launch::DeviceWorkspace dy(count * sizeof(float));
  hipforge::level4::launch::DeviceWorkspace dout(count * sizeof(float));
  copy_to_device(static_cast<float*>(dx.get()), x);
  copy_to_device(static_cast<float*>(dy.get()), y);
  hipforge::level4::math::launch_macro_axpy_float(
      static_cast<float*>(dx.get()), static_cast<float*>(dy.get()), static_cast<float*>(dout.get()), 3.0f, count, nullptr);
  auto out = copy_to_host(static_cast<float*>(dout.get()), count);
  for (int i = 0; i < count; ++i) {
    require(std::fabs(out[i] - (3.0f * x[i] + y[i])) < 1.0e-5f, "macro axpy failed");
  }
  std::cout << "[PASS] macro_generated_kernels\n";
}

void run_cross_file_pipeline() {
  constexpr int count = 1024;
  constexpr int tuples = count / 4;
  auto input = hipforge::level4::utils::make_signal(count, 1.0f);
  hipforge::level4::launch::DeviceWorkspace din(count * sizeof(float));
  hipforge::level4::launch::DeviceWorkspace dnorm(count * sizeof(float));
  hipforge::level4::launch::DeviceWorkspace dpack(tuples * sizeof(float4));
  copy_to_device(static_cast<float*>(din.get()), input);
  hipforge::level4::math::launch_cross_file_normalize(static_cast<float*>(din.get()), static_cast<float*>(dnorm.get()), 2.0f, count, nullptr);
  hipforge::level4::math::launch_cross_file_pack4(static_cast<float*>(dnorm.get()), static_cast<float4*>(dpack.get()), tuples, nullptr);
  auto normalized = copy_to_host(static_cast<float*>(dnorm.get()), count);
  for (int i = 0; i < count; ++i) {
    require(std::fabs(normalized[i] - input[i] * 0.5f) < 1.0e-5f, "normalize failed");
  }
  std::cout << "[PASS] cross_file_pipeline\n";
}

}  // namespace

int main() {
  try {
    std::cout << "HIPForge Level 4 Multi-File CUDA System Benchmark\n";
    int devices = 0;
    L4_CUDA_CHECK(cudaGetDeviceCount(&devices));
    require(devices > 0, "no CUDA devices detected");
    run_macro_generated_kernels();
    run_cross_file_pipeline();
    L4_CUDA_CHECK(cudaDeviceReset());
    std::cout << "ALL LEVEL 4 CUDA CHECKS PASSED\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "[FAIL] " << error.what() << "\n";
    return 1;
  }
}

