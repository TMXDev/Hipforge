#include "hipforge_level5/algorithms.cuh"
#include "hipforge_level5/runtime.hpp"

#include <cmath>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <vector>

namespace {

using hipforge::level5::DeviceBuffer;
namespace algorithms = hipforge::level5::algorithms;

void require(bool condition, const char* message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

void run_image_processing() {
  constexpr int width = 32;
  constexpr int height = 24;
  constexpr int count = width * height;
  std::vector<float> input(count), output(count), expected(count);
  for (int i = 0; i < count; ++i) {
    input[i] = static_cast<float>((i * 13) % 251) / 251.0f;
  }
  auto clamp = [](int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); };
  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x) {
      float acc = 0.0f;
      for (int dy = -1; dy <= 1; ++dy) {
        for (int dx = -1; dx <= 1; ++dx) {
          acc += input[clamp(y + dy, 0, height - 1) * width + clamp(x + dx, 0, width - 1)];
        }
      }
      expected[y * width + x] = acc / 9.0f;
    }
  }
  DeviceBuffer<float> din(count);
  DeviceBuffer<float> dout(count);
  din.copy_from_host(input.data());
  algorithms::launch_image_blur(din.get(), dout.get(), width, height);
  dout.copy_to_host(output.data());
  for (int i = 0; i < count; ++i) {
    require(std::fabs(output[i] - expected[i]) < 1.0e-5f, "image blur mismatch");
  }
  std::cout << "[PASS] image_processing\n";
}

void run_finite_difference() {
  constexpr int width = 40;
  constexpr int height = 30;
  constexpr int count = width * height;
  std::vector<float> current(count), next(count);
  for (int i = 0; i < count; ++i) {
    current[i] = static_cast<float>((i * 7) % 113) * 0.01f;
  }
  DeviceBuffer<float> dcurrent(count);
  DeviceBuffer<float> dnext(count);
  dcurrent.copy_from_host(current.data());
  algorithms::launch_heat_step(dcurrent.get(), dnext.get(), width, height, 0.1f);
  dnext.copy_to_host(next.data());
  require(std::isfinite(next[count / 2]), "finite difference produced non-finite value");
  std::cout << "[PASS] finite_difference\n";
}

void run_sparse_matrix() {
  constexpr int rows = 8;
  const std::vector<int> row_offsets{0, 2, 4, 7, 9, 11, 14, 16, 18};
  const std::vector<int> columns{0, 1, 1, 2, 0, 2, 3, 3, 4, 4, 5, 1, 5, 6, 6, 7, 0, 7};
  std::vector<float> values(columns.size(), 0.5f);
  std::vector<float> x(rows), y(rows), expected(rows);
  for (int i = 0; i < rows; ++i) {
    x[i] = static_cast<float>(i + 1);
  }
  for (int row = 0; row < rows; ++row) {
    for (int offset = row_offsets[row]; offset < row_offsets[row + 1]; ++offset) {
      expected[row] += values[offset] * x[columns[offset]];
    }
  }
  DeviceBuffer<int> drows(row_offsets.size());
  DeviceBuffer<int> dcols(columns.size());
  DeviceBuffer<float> dvals(values.size());
  DeviceBuffer<float> dx(x.size());
  DeviceBuffer<float> dy(y.size());
  drows.copy_from_host(row_offsets.data());
  dcols.copy_from_host(columns.data());
  dvals.copy_from_host(values.data());
  dx.copy_from_host(x.data());
  algorithms::launch_csr_spmv(drows.get(), dcols.get(), dvals.get(), dx.get(), dy.get(), rows);
  dy.copy_to_host(y.data());
  for (int i = 0; i < rows; ++i) {
    require(std::fabs(y[i] - expected[i]) < 1.0e-5f, "spmv mismatch");
  }
  std::cout << "[PASS] sparse_matrix\n";
}

void run_monte_carlo() {
  constexpr int threads = 512;
  constexpr int samples = 128;
  std::vector<unsigned int> hits(threads);
  DeviceBuffer<unsigned int> dhits(threads);
  algorithms::launch_monte_carlo_pi(dhits.get(), samples, threads, 1234u);
  dhits.copy_to_host(hits.data());
  const unsigned long long total_hits = std::accumulate(hits.begin(), hits.end(), 0ull);
  const double pi = 4.0 * static_cast<double>(total_hits) / static_cast<double>(threads * samples);
  require(pi > 2.8 && pi < 3.5, "monte carlo estimate outside sanity range");
  std::cout << "[PASS] monte_carlo\n";
}

void run_neural_layer() {
  constexpr int batch = 4;
  constexpr int in_features = 8;
  constexpr int out_features = 6;
  std::vector<float> input(batch * in_features, 0.25f);
  std::vector<float> weights(out_features * in_features, 0.125f);
  std::vector<float> bias(out_features, -0.1f);
  std::vector<float> output(batch * out_features);
  DeviceBuffer<float> di(input.size());
  DeviceBuffer<float> dw(weights.size());
  DeviceBuffer<float> db(bias.size());
  DeviceBuffer<float> dout(output.size());
  di.copy_from_host(input.data());
  dw.copy_from_host(weights.data());
  db.copy_from_host(bias.data());
  algorithms::launch_affine_relu(di.get(), dw.get(), db.get(), dout.get(), batch, in_features, out_features);
  dout.copy_to_host(output.data());
  for (float value : output) {
    require(value > 0.0f, "affine relu mismatch");
  }
  std::cout << "[PASS] neural_layer\n";
}

void run_particle_system() {
  constexpr int count = 256;
  std::vector<float4> positions(count);
  std::vector<float4> velocities(count);
  for (int i = 0; i < count; ++i) {
    positions[i] = make_float4(static_cast<float>(i), 1.0f, 2.0f, 1.0f);
    velocities[i] = make_float4(0.5f, 0.25f, -0.5f, 0.0f);
  }
  DeviceBuffer<float4> dpos(count);
  DeviceBuffer<float4> dvel(count);
  dpos.copy_from_host(positions.data());
  dvel.copy_from_host(velocities.data());
  algorithms::launch_particle_integrate(dpos.get(), dvel.get(), 2.0f, count);
  dpos.copy_to_host(positions.data());
  require(std::fabs(positions[7].x - 8.0f) < 1.0e-5f, "particle integration mismatch");
  std::cout << "[PASS] particle_system\n";
}

}  // namespace

int main() {
  try {
    std::cout << "HIPForge Level 5 Production Algorithm Benchmark\n";
    int devices = 0;
    L5_CUDA_CHECK(cudaGetDeviceCount(&devices));
    require(devices > 0, "no CUDA devices detected");
    run_image_processing();
    run_finite_difference();
    run_sparse_matrix();
    run_monte_carlo();
    run_neural_layer();
    run_particle_system();
    L5_CUDA_CHECK(cudaDeviceReset());
    std::cout << "ALL LEVEL 5 CUDA CHECKS PASSED\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "[FAIL] " << error.what() << "\n";
    return 1;
  }
}

