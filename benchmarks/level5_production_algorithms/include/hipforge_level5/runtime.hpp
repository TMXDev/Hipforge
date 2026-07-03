#pragma once

#include <cuda_runtime.h>

#include <cstddef>
#include <sstream>
#include <stdexcept>

namespace hipforge::level5 {

inline void check_cuda(cudaError_t result, const char* expression, const char* file, int line) {
  if (result == cudaSuccess) {
    return;
  }
  std::ostringstream message;
  message << expression << " failed at " << file << ":" << line << ": "
          << cudaGetErrorString(result);
  throw std::runtime_error(message.str());
}

#define L5_CUDA_CHECK(expression) \
  ::hipforge::level5::check_cuda((expression), #expression, __FILE__, __LINE__)

template <typename T>
class DeviceBuffer {
 public:
  explicit DeviceBuffer(std::size_t count) : count_(count) {
    if (count_ != 0) {
      L5_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&ptr_), count_ * sizeof(T)));
    }
  }
  DeviceBuffer(const DeviceBuffer&) = delete;
  DeviceBuffer& operator=(const DeviceBuffer&) = delete;
  ~DeviceBuffer() {
    if (ptr_ != nullptr) {
      cudaFree(ptr_);
    }
  }
  T* get() { return ptr_; }
  const T* get() const { return ptr_; }
  std::size_t count() const { return count_; }
  void copy_from_host(const T* src) {
    L5_CUDA_CHECK(cudaMemcpy(ptr_, src, count_ * sizeof(T), cudaMemcpyHostToDevice));
  }
  void copy_to_host(T* dst) const {
    L5_CUDA_CHECK(cudaMemcpy(dst, ptr_, count_ * sizeof(T), cudaMemcpyDeviceToHost));
  }

 private:
  T* ptr_{nullptr};
  std::size_t count_{0};
};

}  // namespace hipforge::level5

