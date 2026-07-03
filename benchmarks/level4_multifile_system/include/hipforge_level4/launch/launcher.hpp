#pragma once

#include "hipforge_level4/detail/error.hpp"

#include <cstddef>
#include <utility>

namespace hipforge::level4::launch {

class DeviceWorkspace {
 public:
  explicit DeviceWorkspace(std::size_t bytes) : bytes_(bytes) {
    if (bytes_ > 0) {
      L4_CUDA_CHECK(cudaMalloc(&ptr_, bytes_));
    }
  }

  DeviceWorkspace(const DeviceWorkspace&) = delete;
  DeviceWorkspace& operator=(const DeviceWorkspace&) = delete;

  DeviceWorkspace(DeviceWorkspace&& other) noexcept : ptr_(other.ptr_), bytes_(other.bytes_) {
    other.ptr_ = nullptr;
    other.bytes_ = 0;
  }

  DeviceWorkspace& operator=(DeviceWorkspace&& other) noexcept {
    if (this != &other) {
      reset();
      ptr_ = other.ptr_;
      bytes_ = other.bytes_;
      other.ptr_ = nullptr;
      other.bytes_ = 0;
    }
    return *this;
  }

  ~DeviceWorkspace() { reset(); }

  void* get() { return ptr_; }
  std::size_t bytes() const { return bytes_; }

 private:
  void reset() noexcept {
    if (ptr_ != nullptr) {
      cudaFree(ptr_);
      ptr_ = nullptr;
    }
  }

  void* ptr_{nullptr};
  std::size_t bytes_{0};
};

}  // namespace hipforge::level4::launch

