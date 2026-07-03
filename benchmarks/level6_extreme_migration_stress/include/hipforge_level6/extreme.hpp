#pragma once

#include <cuda_runtime.h>

#include <array>
#include <cstddef>
#include <sstream>
#include <stdexcept>
#include <type_traits>
#include <utility>

namespace hipforge::level6::deep::runtime {

inline void check_cuda(cudaError_t result, const char* expression, const char* file, int line) {
  if (result == cudaSuccess) {
    return;
  }
  std::ostringstream message;
  message << expression << " failed at " << file << ":" << line << ": "
          << cudaGetErrorString(result);
  throw std::runtime_error(message.str());
}

#define HF6_CHECK(EXPR) ::hipforge::level6::deep::runtime::check_cuda((EXPR), #EXPR, __FILE__, __LINE__)

template <int N>
struct StaticFactorial {
  static constexpr int value = N * StaticFactorial<N - 1>::value;
};

template <>
struct StaticFactorial<0> {
  static constexpr int value = 1;
};

enum class Operation : int {
  Add = 0,
  Subtract = 1,
  Multiply = 2,
  Clamp = 3,
  Fma = 4,
  DispatchSquare = 5,
  DispatchCube = 6,
  ReservedA = 7,
  ReservedB = 8
};

template <typename T>
struct DeviceAllocator {
  using value_type = T;

  T* allocate(std::size_t count) const {
    T* ptr = nullptr;
    HF6_CHECK(cudaMalloc(reinterpret_cast<void**>(&ptr), count * sizeof(T)));
    return ptr;
  }

  void deallocate(T* ptr) const noexcept {
    if (ptr != nullptr) {
      cudaFree(ptr);
    }
  }
};

template <typename T, typename Allocator = DeviceAllocator<T>>
class UniqueDeviceArray {
 public:
  explicit UniqueDeviceArray(std::size_t count) : count_(count), ptr_(allocator_.allocate(count)) {}

  UniqueDeviceArray(const UniqueDeviceArray&) = delete;
  UniqueDeviceArray& operator=(const UniqueDeviceArray&) = delete;

  UniqueDeviceArray(UniqueDeviceArray&& other) noexcept
      : count_(other.count_), ptr_(other.ptr_), allocator_(other.allocator_) {
    other.count_ = 0;
    other.ptr_ = nullptr;
  }

  UniqueDeviceArray& operator=(UniqueDeviceArray&& other) noexcept {
    if (this != &other) {
      reset();
      count_ = other.count_;
      ptr_ = other.ptr_;
      allocator_ = other.allocator_;
      other.count_ = 0;
      other.ptr_ = nullptr;
    }
    return *this;
  }

  ~UniqueDeviceArray() { reset(); }

  T* get() { return ptr_; }
  const T* get() const { return ptr_; }
  std::size_t count() const { return count_; }

  void copy_from_host(const T* src) {
    HF6_CHECK(cudaMemcpy(ptr_, src, count_ * sizeof(T), cudaMemcpyHostToDevice));
  }

  void copy_to_host(T* dst) const {
    HF6_CHECK(cudaMemcpy(dst, ptr_, count_ * sizeof(T), cudaMemcpyDeviceToHost));
  }

 private:
  void reset() noexcept {
    allocator_.deallocate(ptr_);
    ptr_ = nullptr;
    count_ = 0;
  }

  std::size_t count_{0};
  T* ptr_{nullptr};
  Allocator allocator_{};
};

namespace device_math {

template <typename T>
__host__ __device__ constexpr T clamp(T value, T lo, T hi) {
  return value < lo ? lo : (value > hi ? hi : value);
}

template <typename T, Operation Op>
struct Operator;

template <typename T>
struct Operator<T, Operation::Add> {
  __host__ __device__ T operator()(T a, T b) const { return a + b; }
};

template <typename T>
struct Operator<T, Operation::Multiply> {
  __host__ __device__ T operator()(T a, T b) const { return a * b; }
};

template <typename T>
struct Operator<T, Operation::Clamp> {
  __host__ __device__ T operator()(T a, T b) const { return clamp(a + b, T{-4}, T{4}); }
};

}  // namespace device_math

namespace kernels {

void upload_coefficients(const float* coeffs, int count);
void launch_macro_pipeline(const float* a, const float* b, float* out, int count, cudaStream_t stream);
void launch_allocator_pipeline(const float* input, float* output, int count, cudaStream_t stream);
void launch_function_pointer_dispatch(const float* input, float* output, int count, int op_index, cudaStream_t stream);

}  // namespace kernels
}  // namespace hipforge::level6::deep::runtime

#define HF6_KERNEL_NAME(BASE, OP) BASE##_##OP##_kernel
#define HF6_LAUNCH_GRID(COUNT, BLOCK) dim3(((COUNT) + (BLOCK)-1) / (BLOCK))
#define HF6_DECLARE_BINARY_KERNEL(BASE, OP_ENUM, OP_NAME)                                      \
  __global__ void HF6_KERNEL_NAME(BASE, OP_NAME)(const float* a, const float* b, float* out, int count) { \
    const int index = blockIdx.x * blockDim.x + threadIdx.x;                                  \
    if (index < count) {                                                                       \
      ::hipforge::level6::deep::runtime::device_math::Operator<float, OP_ENUM> op;             \
      out[index] = op(a[index], b[index]);                                                     \
    }                                                                                          \
  }

