#pragma once

#include "hipforge_level3/runtime.hpp"

#include <array>
#include <cstddef>
#include <memory>
#include <vector>

namespace hipforge::level3 {

template <typename T, int Rank>
class Tensor {
 public:
  using Shape = std::array<int, Rank>;

  explicit Tensor(Shape shape) : shape_(shape), values_(element_count(shape)) {}

  Tensor(const Tensor&) = delete;
  Tensor& operator=(const Tensor&) = delete;
  Tensor(Tensor&&) noexcept = default;
  Tensor& operator=(Tensor&&) noexcept = default;

  T* data() { return values_.get(); }
  const T* data() const { return values_.get(); }
  std::size_t size() const { return values_.count(); }
  const Shape& shape() const { return shape_; }

 private:
  static constexpr std::size_t element_count(Shape shape) {
    std::size_t total = 1;
    for (int extent : shape) {
      total *= static_cast<std::size_t>(extent);
    }
    return total;
  }

  Shape shape_{};
  DeviceBuffer<T> values_;
};

template <typename T>
struct NumericTraits {
  static constexpr T zero() { return T{0}; }
  static constexpr T scale(T value, T factor) { return value * factor; }
};

template <>
struct NumericTraits<int> {
  static constexpr int zero() { return 0; }
  static constexpr int scale(int value, int factor) { return value * factor + 1; }
};

template <typename T>
struct HostDelete {
  void operator()(T* ptr) const noexcept { delete[] ptr; }
};

template <typename T>
using UniqueHostArray = std::unique_ptr<T[], HostDelete<T>>;

template <typename T>
UniqueHostArray<T> make_host_array(std::size_t count) {
  return UniqueHostArray<T>(new T[count]);
}

namespace kernels {

template <typename T>
void launch_saxpy(const T* x, const T* y, T* out, T alpha, int count, cudaStream_t stream);

template <typename T>
void launch_scaled_norm(const T* x, T* partials, T scale, int count, cudaStream_t stream);

int partial_count(int count);

}  // namespace kernels
}  // namespace hipforge::level3

