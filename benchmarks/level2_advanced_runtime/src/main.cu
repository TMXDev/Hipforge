#include "hipforge_level2/advanced_kernels.cuh"
#include "hipforge_level2/runtime.hpp"

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

using hipforge::level2::Array2D;
using hipforge::level2::CapturedGraph;
using hipforge::level2::DeviceBuffer;
using hipforge::level2::Event;
using hipforge::level2::GraphExec;
using hipforge::level2::PinnedHostBuffer;
using hipforge::level2::Stream;
using hipforge::level2::Surface2D;
using hipforge::level2::Texture2D;
namespace kernels = hipforge::level2::kernels;

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
  std::cout << "[PASS] " << std::left << std::setw(36) << result.name << " "
            << std::right << std::fixed << std::setprecision(3) << result.milliseconds << " ms\n";
}

BenchmarkResult run_warp_shuffle_reduction() {
  constexpr int kCount = 1 << 20;

  std::vector<float> input(kCount);
  for (int i = 0; i < kCount; ++i) {
    input[i] = static_cast<float>((i % 23) - 11) * 0.125f;
  }

  const double expected = std::accumulate(input.begin(), input.end(), 0.0);
  const int partial_count = kernels::warp_partial_count(kCount);

  DeviceBuffer<float> device_input(kCount);
  DeviceBuffer<float> device_partials(partial_count);
  std::vector<float> partials(partial_count, 0.0f);
  device_input.copy_from_host(input.data(), input.size());

  Event start;
  Event stop;
  start.record(nullptr);
  kernels::launch_warp_shuffle_reduce(device_input.get(), device_partials.get(), kCount, nullptr);
  stop.record(nullptr);
  const float milliseconds = hipforge::level2::elapsed_milliseconds(start, stop);

  device_partials.copy_to_host(partials.data(), partials.size());
  const double actual = std::accumulate(partials.begin(), partials.end(), 0.0);
  require(std::fabs(actual - expected) < 16.0, "warp_shuffle_reduction validation failed");

  return {"warp_shuffle_reduction", milliseconds};
}

BenchmarkResult run_cooperative_groups_dynamic_shared() {
  constexpr int kCount = 1 << 19;

  std::vector<float> input(kCount);
  for (int i = 0; i < kCount; ++i) {
    input[i] = static_cast<float>((i % 37) + 1) * 0.0625f;
  }

  const double expected = std::accumulate(input.begin(), input.end(), 0.0);
  const int partial_count = kernels::cooperative_partial_count(kCount);

  DeviceBuffer<float> device_input(kCount);
  DeviceBuffer<float> device_block_sums(partial_count);
  DeviceBuffer<float> device_global_sum(1);
  std::vector<float> block_sums(partial_count, 0.0f);
  device_input.copy_from_host(input.data(), input.size());
  CUDA_CHECK(cudaMemset(device_global_sum.get(), 0, sizeof(float)));

  Event start;
  Event stop;
  start.record(nullptr);
  kernels::launch_cooperative_dynamic_reduce(
      device_input.get(), device_block_sums.get(), device_global_sum.get(), kCount, nullptr);
  stop.record(nullptr);
  const float milliseconds = hipforge::level2::elapsed_milliseconds(start, stop);

  float atomic_total = 0.0f;
  device_block_sums.copy_to_host(block_sums.data(), block_sums.size());
  CUDA_CHECK(cudaMemcpy(&atomic_total, device_global_sum.get(), sizeof(float), cudaMemcpyDeviceToHost));

  const double block_total = std::accumulate(block_sums.begin(), block_sums.end(), 0.0);
  require(std::fabs(block_total - expected) < 16.0,
          "cooperative_groups_dynamic_shared block reduction validation failed");
  require(std::fabs(static_cast<double>(atomic_total) - expected) < 32.0,
          "cooperative_groups_dynamic_shared atomic validation failed");

  return {"cooperative_groups_dynamic_shared", milliseconds};
}

BenchmarkResult run_constant_texture_surface() {
  constexpr int kWidth = 96;
  constexpr int kHeight = 80;
  constexpr int kPixels = kWidth * kHeight;

  const std::array<float, kernels::kConvolutionCoefficients> filter = {
      0.0625f, 0.125f, 0.0625f,
      0.1250f, 0.250f, 0.1250f,
      0.0625f, 0.125f, 0.0625f};

  std::vector<float> image(kPixels);
  std::vector<float> output(kPixels, 0.0f);
  std::vector<float> expected(kPixels, 0.0f);

  for (int y = 0; y < kHeight; ++y) {
    for (int x = 0; x < kWidth; ++x) {
      image[y * kWidth + x] = static_cast<float>((x * 7 + y * 11 + (x * y) % 13) % 255) / 255.0f;
    }
  }

  for (int y = 0; y < kHeight; ++y) {
    for (int x = 0; x < kWidth; ++x) {
      float accumulator = 0.0f;
      for (int dy = -kernels::kConvolutionRadius; dy <= kernels::kConvolutionRadius; ++dy) {
        for (int dx = -kernels::kConvolutionRadius; dx <= kernels::kConvolutionRadius; ++dx) {
          const int sample_x = std::min(std::max(x + dx, 0), kWidth - 1);
          const int sample_y = std::min(std::max(y + dy, 0), kHeight - 1);
          const int filter_index = (dy + kernels::kConvolutionRadius) * kernels::kConvolutionDiameter +
                                   (dx + kernels::kConvolutionRadius);
          accumulator += image[sample_y * kWidth + sample_x] * filter[filter_index];
        }
      }
      expected[y * kWidth + x] = accumulator;
    }
  }

  kernels::upload_convolution_filter(filter.data());

  Array2D input_array(kWidth, kHeight);
  Array2D output_array(kWidth, kHeight, cudaArraySurfaceLoadStore);
  input_array.copy_from_host(image.data());
  Texture2D texture(input_array.get());
  Surface2D surface(output_array.get());

  Event start;
  Event stop;
  start.record(nullptr);
  kernels::launch_texture_surface_convolution(
      texture.get(), surface.get(), kWidth, kHeight, nullptr);
  stop.record(nullptr);
  const float milliseconds = hipforge::level2::elapsed_milliseconds(start, stop);

  output_array.copy_to_host(output.data());
  for (int i = 0; i < kPixels; ++i) {
    require(nearly_equal(output[i], expected[i], 1.0e-5f), "constant_texture_surface validation failed");
  }

  return {"constant_texture_surface", milliseconds};
}

CapturedGraph capture_transform_graph(cudaStream_t stream,
                                      const float* host_input,
                                      float* host_output,
                                      float* device_input,
                                      float* device_output,
                                      int element_count,
                                      float scale,
                                      float bias) {
  CUDA_CHECK(cudaStreamBeginCapture(stream, cudaStreamCaptureModeGlobal));
  CUDA_CHECK(cudaMemcpyAsync(device_input,
                             host_input,
                             static_cast<std::size_t>(element_count) * sizeof(float),
                             cudaMemcpyHostToDevice,
                             stream));
  kernels::launch_graph_transform(device_input, device_output, scale, bias, element_count, stream);
  CUDA_CHECK(cudaMemcpyAsync(host_output,
                             device_output,
                             static_cast<std::size_t>(element_count) * sizeof(float),
                             cudaMemcpyDeviceToHost,
                             stream));

  cudaGraph_t graph = nullptr;
  CUDA_CHECK(cudaStreamEndCapture(stream, &graph));
  return CapturedGraph(graph);
}

BenchmarkResult run_multistream_async_graphs() {
  constexpr int kStreamCount = 3;
  constexpr int kCount = kStreamCount * (1 << 18);
  constexpr int kChunk = kCount / kStreamCount;
  constexpr float kScale = 1.5f;
  constexpr float kBias = -0.25f;

  PinnedHostBuffer<float> host_input(kCount);
  PinnedHostBuffer<float> host_output(kCount);

  for (int i = 0; i < kCount; ++i) {
    host_input[i] = static_cast<float>((i % 127) - 63) * 0.03125f;
    host_output[i] = 0.0f;
  }

  std::array<Stream, kStreamCount> streams;
  std::array<DeviceBuffer<float>, kStreamCount> device_input = {
      DeviceBuffer<float>(kChunk), DeviceBuffer<float>(kChunk), DeviceBuffer<float>(kChunk)};
  std::array<DeviceBuffer<float>, kStreamCount> device_output = {
      DeviceBuffer<float>(kChunk), DeviceBuffer<float>(kChunk), DeviceBuffer<float>(kChunk)};

  std::array<CapturedGraph, kStreamCount> graphs = {
      capture_transform_graph(streams[0].get(),
                              host_input.get(),
                              host_output.get(),
                              device_input[0].get(),
                              device_output[0].get(),
                              kChunk,
                              kScale,
                              kBias),
      capture_transform_graph(streams[1].get(),
                              host_input.get() + kChunk,
                              host_output.get() + kChunk,
                              device_input[1].get(),
                              device_output[1].get(),
                              kChunk,
                              kScale,
                              kBias),
      capture_transform_graph(streams[2].get(),
                              host_input.get() + 2 * kChunk,
                              host_output.get() + 2 * kChunk,
                              device_input[2].get(),
                              device_output[2].get(),
                              kChunk,
                              kScale,
                              kBias)};

  std::array<GraphExec, kStreamCount> execs = {
      GraphExec(graphs[0].get()), GraphExec(graphs[1].get()), GraphExec(graphs[2].get())};

  std::array<Event, kStreamCount> start_events;
  std::array<Event, kStreamCount> stop_events;

  for (int stream_index = 0; stream_index < kStreamCount; ++stream_index) {
    start_events[stream_index].record(streams[stream_index].get());
    CUDA_CHECK(cudaGraphLaunch(execs[stream_index].get(), streams[stream_index].get()));
    stop_events[stream_index].record(streams[stream_index].get());
  }

  float milliseconds = 0.0f;
  for (int stream_index = 0; stream_index < kStreamCount; ++stream_index) {
    milliseconds =
        std::max(milliseconds, hipforge::level2::elapsed_milliseconds(
                                   start_events[stream_index], stop_events[stream_index]));
  }

  for (int i = 0; i < kCount; ++i) {
    const float expected = host_input[i] * kScale + kBias;
    require(nearly_equal(host_output[i], expected, 1.0e-5f), "multistream_async_graphs validation failed");
  }

  return {"multistream_async_graphs", milliseconds};
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

    std::cout << "HIPForge Level 2 Advanced CUDA Runtime Benchmark\n";
    std::cout << "Device: " << properties.name << "\n";

    std::vector<BenchmarkResult> results;
    results.push_back(run_warp_shuffle_reduction());
    results.push_back(run_cooperative_groups_dynamic_shared());
    results.push_back(run_constant_texture_surface());
    results.push_back(run_multistream_async_graphs());

    for (const auto& result : results) {
      print_result(result);
    }

    CUDA_CHECK(cudaDeviceReset());
    std::cout << "ALL LEVEL 2 CUDA CHECKS PASSED\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "[FAIL] " << error.what() << "\n";
    return 1;
  }
}
