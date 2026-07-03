#include "hipforge_level1/cuda_check.hpp"
#include "hipforge_level1/kernels.cuh"

#include <cuda_runtime.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using hipforge::level1::CudaEventTimer;
using hipforge::level1::DeviceBuffer;
using hipforge::level1::ManagedBuffer;
using hipforge::level1::PinnedHostBuffer;
namespace kernels = hipforge::level1::kernels;

struct BenchmarkResult {
  std::string name;
  float milliseconds;
};

void require(bool condition, const std::string& message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

bool nearly_equal(float actual, float expected, float tolerance) {
  return std::fabs(actual - expected) <= tolerance;
}

void print_result(const BenchmarkResult& result) {
  std::cout << "[PASS] " << std::left << std::setw(30) << result.name << " "
            << std::right << std::fixed << std::setprecision(3) << result.milliseconds << " ms\n";
}

BenchmarkResult run_vector_add() {
  constexpr int kCount = 1 << 20;

  std::vector<float> host_a(kCount);
  std::vector<float> host_b(kCount);
  std::vector<float> host_out(kCount, 0.0f);

  for (int i = 0; i < kCount; ++i) {
    host_a[i] = static_cast<float>(i % 97) * 0.5f;
    host_b[i] = static_cast<float>(i % 29) * 1.25f;
  }

  DeviceBuffer<float> device_a(kCount);
  DeviceBuffer<float> device_b(kCount);
  DeviceBuffer<float> device_out(kCount);
  device_a.copy_from_host(host_a.data(), host_a.size());
  device_b.copy_from_host(host_b.data(), host_b.size());

  CudaEventTimer timer;
  timer.record_start();
  kernels::launch_vector_add(device_a.get(), device_b.get(), device_out.get(), kCount, nullptr);
  timer.record_stop();
  const float milliseconds = timer.elapsed_milliseconds();

  device_out.copy_to_host(host_out.data(), host_out.size());

  for (int i = 0; i < kCount; ++i) {
    require(nearly_equal(host_out[i], host_a[i] + host_b[i], 1.0e-5f),
            "vector_add validation failed");
  }

  return {"vector_add", milliseconds};
}

BenchmarkResult run_reduction() {
  constexpr int kCount = 1 << 20;

  std::vector<float> values(kCount);
  for (int i = 0; i < kCount; ++i) {
    values[i] = static_cast<float>((i % 13) + 1) * 0.125f;
  }
  const double expected = std::accumulate(values.begin(), values.end(), 0.0);

  DeviceBuffer<float> device_values(kCount);
  device_values.copy_from_host(values.data(), values.size());

  const int max_partials = kernels::reduction_partial_count(kCount);
  DeviceBuffer<float> partial_a(max_partials);
  DeviceBuffer<float> partial_b(max_partials);

  const float* current = device_values.get();
  float* output = partial_a.get();
  int current_count = kCount;

  CudaEventTimer timer;
  timer.record_start();
  while (current_count > 1) {
    kernels::launch_reduce_sum(current, output, current_count, nullptr);
    current = output;
    current_count = kernels::reduction_partial_count(current_count);
    output = (output == partial_a.get()) ? partial_b.get() : partial_a.get();
  }
  timer.record_stop();
  const float milliseconds = timer.elapsed_milliseconds();

  float actual = 0.0f;
  CUDA_CHECK(cudaMemcpy(&actual, current, sizeof(float), cudaMemcpyDeviceToHost));
  require(std::fabs(static_cast<double>(actual) - expected) < 64.0, "reduction validation failed");

  return {"reduction", milliseconds};
}

BenchmarkResult run_prefix_sum() {
  constexpr int kCount = kernels::kScanElements;

  std::vector<int> input(kCount);
  std::vector<int> output(kCount, 0);
  std::vector<int> expected(kCount, 0);

  for (int i = 0; i < kCount; ++i) {
    input[i] = (i % 5) + 1;
    expected[i] = (i == 0) ? 0 : expected[i - 1] + input[i - 1];
  }

  DeviceBuffer<int> device_input(kCount);
  DeviceBuffer<int> device_output(kCount);
  device_input.copy_from_host(input.data(), input.size());

  CudaEventTimer timer;
  timer.record_start();
  kernels::launch_exclusive_scan_1024(device_input.get(), device_output.get(), nullptr);
  timer.record_stop();
  const float milliseconds = timer.elapsed_milliseconds();

  device_output.copy_to_host(output.data(), output.size());
  require(output == expected, "prefix_sum validation failed");

  return {"prefix_sum", milliseconds};
}

BenchmarkResult run_histogram() {
  constexpr int kCount = 1 << 20;

  std::vector<unsigned char> input(kCount);
  std::array<unsigned int, kernels::kHistogramBins> expected{};
  std::array<unsigned int, kernels::kHistogramBins> output{};

  for (int i = 0; i < kCount; ++i) {
    const auto value = static_cast<unsigned char>((i * 37 + i / 11) & 0xFF);
    input[i] = value;
    ++expected[value];
  }

  DeviceBuffer<unsigned char> device_input(kCount);
  DeviceBuffer<unsigned int> device_bins(kernels::kHistogramBins);
  device_input.copy_from_host(input.data(), input.size());
  CUDA_CHECK(cudaMemset(device_bins.get(), 0, kernels::kHistogramBins * sizeof(unsigned int)));

  CudaEventTimer timer;
  timer.record_start();
  kernels::launch_histogram_u8(device_input.get(), device_bins.get(), kCount, nullptr);
  timer.record_stop();
  const float milliseconds = timer.elapsed_milliseconds();

  device_bins.copy_to_host(output.data(), output.size());
  require(output == expected, "histogram validation failed");

  return {"histogram", milliseconds};
}

BenchmarkResult run_matrix_multiplication() {
  constexpr int kSize = 64;
  constexpr int kCount = kSize * kSize;

  std::vector<float> a(kCount);
  std::vector<float> b(kCount);
  std::vector<float> c(kCount, 0.0f);
  std::vector<float> expected(kCount, 0.0f);

  for (int row = 0; row < kSize; ++row) {
    for (int column = 0; column < kSize; ++column) {
      a[row * kSize + column] = static_cast<float>((row + column) % 17) * 0.25f;
      b[row * kSize + column] = static_cast<float>((row * 3 + column) % 19) * 0.125f;
    }
  }

  for (int row = 0; row < kSize; ++row) {
    for (int column = 0; column < kSize; ++column) {
      double accumulator = 0.0;
      for (int k = 0; k < kSize; ++k) {
        accumulator += static_cast<double>(a[row * kSize + k]) *
                       static_cast<double>(b[k * kSize + column]);
      }
      expected[row * kSize + column] = static_cast<float>(accumulator);
    }
  }

  DeviceBuffer<float> device_a(kCount);
  DeviceBuffer<float> device_b(kCount);
  DeviceBuffer<float> device_c(kCount);
  device_a.copy_from_host(a.data(), a.size());
  device_b.copy_from_host(b.data(), b.size());

  CudaEventTimer timer;
  timer.record_start();
  kernels::launch_matrix_multiply_tiled(device_a.get(), device_b.get(), device_c.get(), kSize, nullptr);
  timer.record_stop();
  const float milliseconds = timer.elapsed_milliseconds();

  device_c.copy_to_host(c.data(), c.size());
  for (int i = 0; i < kCount; ++i) {
    require(nearly_equal(c[i], expected[i], 2.0e-3f), "matrix_multiplication validation failed");
  }

  return {"matrix_multiplication", milliseconds};
}

BenchmarkResult run_shared_memory_stencil() {
  constexpr int kCount = 1 << 12;

  std::vector<float> input(kCount);
  std::vector<float> output(kCount, 0.0f);
  std::vector<float> expected(kCount, 0.0f);

  for (int i = 0; i < kCount; ++i) {
    input[i] = static_cast<float>((i * 5) % 113) * 0.25f;
  }

  for (int i = 0; i < kCount; ++i) {
    const float left = input[std::max(i - 1, 0)];
    const float right = input[std::min(i + 1, kCount - 1)];
    expected[i] = (left + input[i] + right) / 3.0f;
  }

  DeviceBuffer<float> device_input(kCount);
  DeviceBuffer<float> device_output(kCount);
  device_input.copy_from_host(input.data(), input.size());

  CudaEventTimer timer;
  timer.record_start();
  kernels::launch_shared_window_average(device_input.get(), device_output.get(), kCount, nullptr);
  timer.record_stop();
  const float milliseconds = timer.elapsed_milliseconds();

  device_output.copy_to_host(output.data(), output.size());
  for (int i = 0; i < kCount; ++i) {
    require(nearly_equal(output[i], expected[i], 1.0e-5f), "shared_memory_stencil validation failed");
  }

  return {"shared_memory_stencil", milliseconds};
}

BenchmarkResult run_streams_events_pinned_memory() {
  constexpr int kCount = 1 << 20;
  constexpr int kStreamCount = 2;
  constexpr int kChunk = kCount / kStreamCount;

  PinnedHostBuffer<float> host_a(kCount);
  PinnedHostBuffer<float> host_b(kCount);
  PinnedHostBuffer<float> host_out(kCount);

  for (int i = 0; i < kCount; ++i) {
    host_a[i] = static_cast<float>(i % 101) * 0.5f;
    host_b[i] = static_cast<float>(i % 53) * 0.75f;
    host_out[i] = 0.0f;
  }

  std::array<cudaStream_t, kStreamCount> streams{};
  std::array<DeviceBuffer<float>, kStreamCount> device_a = {DeviceBuffer<float>(kChunk),
                                                            DeviceBuffer<float>(kChunk)};
  std::array<DeviceBuffer<float>, kStreamCount> device_b = {DeviceBuffer<float>(kChunk),
                                                            DeviceBuffer<float>(kChunk)};
  std::array<DeviceBuffer<float>, kStreamCount> device_out = {DeviceBuffer<float>(kChunk),
                                                              DeviceBuffer<float>(kChunk)};
  std::array<CudaEventTimer, kStreamCount> timers;

  for (auto& stream : streams) {
    CUDA_CHECK(cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking));
  }

  for (int stream_index = 0; stream_index < kStreamCount; ++stream_index) {
    const int offset = stream_index * kChunk;
    timers[stream_index].record_start(streams[stream_index]);
    CUDA_CHECK(cudaMemcpyAsync(device_a[stream_index].get(),
                               host_a.get() + offset,
                               kChunk * sizeof(float),
                               cudaMemcpyHostToDevice,
                               streams[stream_index]));
    CUDA_CHECK(cudaMemcpyAsync(device_b[stream_index].get(),
                               host_b.get() + offset,
                               kChunk * sizeof(float),
                               cudaMemcpyHostToDevice,
                               streams[stream_index]));
    kernels::launch_vector_add(device_a[stream_index].get(),
                               device_b[stream_index].get(),
                               device_out[stream_index].get(),
                               kChunk,
                               streams[stream_index]);
    CUDA_CHECK(cudaMemcpyAsync(host_out.get() + offset,
                               device_out[stream_index].get(),
                               kChunk * sizeof(float),
                               cudaMemcpyDeviceToHost,
                               streams[stream_index]));
    timers[stream_index].record_stop(streams[stream_index]);
  }

  float milliseconds = 0.0f;
  for (int stream_index = 0; stream_index < kStreamCount; ++stream_index) {
    milliseconds = std::max(milliseconds, timers[stream_index].elapsed_milliseconds());
    CUDA_CHECK(cudaStreamDestroy(streams[stream_index]));
  }

  for (int i = 0; i < kCount; ++i) {
    require(nearly_equal(host_out[i], host_a[i] + host_b[i], 1.0e-5f),
            "streams_events_pinned_memory validation failed");
  }

  return {"streams_events_pinned_memory", milliseconds};
}

BenchmarkResult run_unified_memory() {
  constexpr int kCount = 1 << 18;
  constexpr float kScale = 1.75f;

  ManagedBuffer<float> values(kCount);
  for (int i = 0; i < kCount; ++i) {
    values[i] = static_cast<float>((i % 31) - 15) * 0.5f;
  }

  CudaEventTimer timer;
  timer.record_start();
  kernels::launch_unified_scale(values.get(), kScale, kCount, nullptr);
  timer.record_stop();
  const float milliseconds = timer.elapsed_milliseconds();
  CUDA_CHECK(cudaDeviceSynchronize());

  for (int i = 0; i < kCount; ++i) {
    const float expected = static_cast<float>((i % 31) - 15) * 0.5f * kScale;
    require(nearly_equal(values[i], expected, 1.0e-5f), "unified_memory validation failed");
  }

  return {"unified_memory", milliseconds};
}

}  // namespace

int main() {
  try {
    int device_count = 0;
    CUDA_CHECK(cudaGetDeviceCount(&device_count));
    require(device_count > 0, "no CUDA devices detected");

    int device = 0;
    CUDA_CHECK(cudaSetDevice(device));

    cudaDeviceProp properties{};
    CUDA_CHECK(cudaGetDeviceProperties(&properties, device));

    std::cout << "HIPForge Level 1 CUDA Core Benchmark\n";
    std::cout << "Device: " << properties.name << "\n";

    std::vector<BenchmarkResult> results;
    results.push_back(run_vector_add());
    results.push_back(run_reduction());
    results.push_back(run_prefix_sum());
    results.push_back(run_histogram());
    results.push_back(run_matrix_multiplication());
    results.push_back(run_shared_memory_stencil());
    results.push_back(run_streams_events_pinned_memory());
    results.push_back(run_unified_memory());

    for (const auto& result : results) {
      print_result(result);
    }

    CUDA_CHECK(cudaDeviceReset());
    std::cout << "ALL LEVEL 1 CUDA CHECKS PASSED\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "[FAIL] " << error.what() << "\n";
    return 1;
  }
}

