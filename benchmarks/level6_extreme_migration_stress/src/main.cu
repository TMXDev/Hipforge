#include "hipforge_level6/extreme.hpp"

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {

namespace hf6 = hipforge::level6::deep::runtime;

void require(bool condition, const char* message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

void run_macro_launch_wrappers() {
  constexpr int count = 1024;
  std::vector<float> a(count), b(count), out(count);
  for (int i = 0; i < count; ++i) {
    a[i] = static_cast<float>((i % 11) - 5);
    b[i] = static_cast<float>((i % 7) - 3) * 0.25f;
  }
  hf6::UniqueDeviceArray<float> da(count);
  hf6::UniqueDeviceArray<float> db(count);
  hf6::UniqueDeviceArray<float> dout(count);
  da.copy_from_host(a.data());
  db.copy_from_host(b.data());
  hf6::kernels::launch_macro_pipeline(da.get(), db.get(), dout.get(), count, nullptr);
  dout.copy_to_host(out.data());
  for (int i = 0; i < count; ++i) {
    const float expected = hf6::device_math::clamp(a[i] + b[i] + b[i], -4.0f, 4.0f);
    require(std::fabs(out[i] - expected) < 1.0e-5f, "macro launch wrapper mismatch");
  }
  std::cout << "[PASS] macro_launch_wrappers\n";
}

void run_allocator_pipeline() {
  constexpr int count = 512;
  const float coeffs[8] = {1.0f, 0.5f, 0.25f, 0.125f, 0.1f, 0.2f, 0.3f, 0.4f};
  std::vector<float> input(count), output(count);
  for (int i = 0; i < count; ++i) {
    input[i] = static_cast<float>(i % 13) * 0.125f;
  }
  hf6::kernels::upload_coefficients(coeffs, 8);
  hf6::UniqueDeviceArray<float> din(count);
  hf6::UniqueDeviceArray<float> dout(count);
  din.copy_from_host(input.data());
  hf6::kernels::launch_allocator_pipeline(din.get(), dout.get(), count, nullptr);
  dout.copy_to_host(output.data());
  require(output[3] > 6.0f, "allocator pipeline mismatch");
  std::cout << "[PASS] allocator_pipeline\n";
}

void run_device_function_pointer_dispatch() {
  constexpr int count = 256;
  std::vector<float> input(count), output(count);
  for (int i = 0; i < count; ++i) {
    input[i] = static_cast<float>(i % 9) * 0.5f;
  }
  hf6::UniqueDeviceArray<float> din(count);
  hf6::UniqueDeviceArray<float> dout(count);
  din.copy_from_host(input.data());
  hf6::kernels::launch_function_pointer_dispatch(din.get(), dout.get(), count, 1, nullptr);
  dout.copy_to_host(output.data());
  require(std::fabs(output[5] - input[5] * input[5] * input[5]) < 1.0e-5f, "function pointer dispatch mismatch");
  std::cout << "[PASS] device_function_pointer_dispatch\n";
}

}  // namespace

int main() {
  try {
    std::cout << "HIPForge Level 6 Extreme Migration Stress Benchmark\n";
    int devices = 0;
    HF6_CHECK(cudaGetDeviceCount(&devices));
    require(devices > 0, "no CUDA devices detected");
    run_macro_launch_wrappers();
    run_allocator_pipeline();
    run_device_function_pointer_dispatch();
    HF6_CHECK(cudaDeviceReset());
    std::cout << "ALL LEVEL 6 CUDA CHECKS PASSED\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "[FAIL] " << error.what() << "\n";
    return 1;
  }
}

