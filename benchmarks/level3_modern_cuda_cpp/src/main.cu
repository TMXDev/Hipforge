#include "hipforge_level3/tensor.hpp"

#include <cmath>
#include <iostream>
#include <memory>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using hipforge::level3::DeviceBuffer;
using hipforge::level3::Stream;
using hipforge::level3::Tensor;
namespace kernels = hipforge::level3::kernels;

void require(bool condition, const std::string& message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

class BenchmarkCase {
 public:
  virtual ~BenchmarkCase() = default;
  virtual const char* name() const = 0;
  virtual void run() = 0;
};

class TemplatedSaxpyCase final : public BenchmarkCase {
 public:
  const char* name() const override { return "templated_saxpy"; }

  void run() override {
    constexpr int count = 4096;
    std::vector<float> x(count), y(count), out(count);
    auto fill = [](int i, float bias) { return static_cast<float>((i % 29) - 14) * 0.25f + bias; };
    for (int i = 0; i < count; ++i) {
      x[i] = fill(i, 1.0f);
      y[i] = fill(i, -0.5f);
    }

    Stream stream;
    Tensor<float, 1> device_x({count});
    Tensor<float, 1> device_y({count});
    Tensor<float, 1> device_out({count});
    device_x.data();
    CUDA_CHECK(cudaMemcpyAsync(device_x.data(), x.data(), count * sizeof(float), cudaMemcpyHostToDevice, stream.get()));
    CUDA_CHECK(cudaMemcpyAsync(device_y.data(), y.data(), count * sizeof(float), cudaMemcpyHostToDevice, stream.get()));
    kernels::launch_saxpy<float>(device_x.data(), device_y.data(), device_out.data(), 2.0f, count, stream.get());
    CUDA_CHECK(cudaMemcpyAsync(out.data(), device_out.data(), count * sizeof(float), cudaMemcpyDeviceToHost, stream.get()));
    stream.synchronize();

    for (int i = 0; i < count; ++i) {
      require(std::fabs(out[i] - (2.0f * x[i] + y[i])) < 1.0e-5f, "saxpy mismatch");
    }
  }
};

class SpecializedNormCase final : public BenchmarkCase {
 public:
  const char* name() const override { return "specialized_norm"; }

  void run() override {
    constexpr int count = 8192;
    std::vector<float> input(count);
    for (int i = 0; i < count; ++i) {
      input[i] = static_cast<float>((i % 17) - 8) * 0.125f;
    }
    const int partials_count = kernels::partial_count(count);
    std::vector<float> partials(partials_count);

    DeviceBuffer<float> device_input(count);
    DeviceBuffer<float> device_partials(partials_count);
    Stream stream;
    device_input.copy_from_host(input.data(), input.size(), stream.get());
    kernels::launch_scaled_norm<float>(device_input.get(), device_partials.get(), 1.5f, count, stream.get());
    device_partials.copy_to_host(partials.data(), partials.size(), stream.get());
    stream.synchronize();

    const double actual = std::accumulate(partials.begin(), partials.end(), 0.0);
    double expected = 0.0;
    for (float value : input) {
      expected += static_cast<double>(value * 1.5f) * static_cast<double>(value * 1.5f);
    }
    require(std::fabs(actual - expected) < 1.0e-3, "norm mismatch");
  }
};

class MoveOnlyTensorPipeline final : public BenchmarkCase {
 public:
  const char* name() const override { return "move_only_tensor_pipeline"; }

  void run() override {
    Tensor<float, 2> first({16, 16});
    Tensor<float, 2> moved(std::move(first));
    require(moved.size() == 256, "moved tensor has wrong size");
  }
};

}  // namespace

int main() {
  try {
    std::cout << "HIPForge Level 3 Modern CUDA C++ Benchmark\n";
    int device_count = 0;
    CUDA_CHECK(cudaGetDeviceCount(&device_count));
    require(device_count > 0, "no CUDA devices detected");

    std::vector<std::unique_ptr<BenchmarkCase>> cases;
    cases.emplace_back(std::make_unique<TemplatedSaxpyCase>());
    cases.emplace_back(std::make_unique<SpecializedNormCase>());
    cases.emplace_back(std::make_unique<MoveOnlyTensorPipeline>());

    for (const auto& test : cases) {
      test->run();
      std::cout << "[PASS] " << test->name() << "\n";
    }

    CUDA_CHECK(cudaDeviceReset());
    std::cout << "ALL LEVEL 3 CUDA CHECKS PASSED\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "[FAIL] " << error.what() << "\n";
    return 1;
  }
}

