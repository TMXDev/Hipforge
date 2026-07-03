#pragma once

#include <cuda_runtime.h>

#include <cstddef>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

namespace hipforge::level1 {

inline void check_cuda(cudaError_t result, const char* expression, const char* file, int line) {
  if (result == cudaSuccess) {
    return;
  }

  std::ostringstream message;
  message << "CUDA call failed: " << expression << " at " << file << ":" << line << " -> "
          << cudaGetErrorString(result);
  throw std::runtime_error(message.str());
}

#define CUDA_CHECK(expression) \
  ::hipforge::level1::check_cuda((expression), #expression, __FILE__, __LINE__)

class CudaEventTimer {
 public:
  CudaEventTimer() {
    CUDA_CHECK(cudaEventCreate(&start_));
    CUDA_CHECK(cudaEventCreate(&stop_));
  }

  CudaEventTimer(const CudaEventTimer&) = delete;
  CudaEventTimer& operator=(const CudaEventTimer&) = delete;

  CudaEventTimer(CudaEventTimer&& other) noexcept : start_(other.start_), stop_(other.stop_) {
    other.start_ = nullptr;
    other.stop_ = nullptr;
  }

  CudaEventTimer& operator=(CudaEventTimer&& other) noexcept {
    if (this != &other) {
      destroy();
      start_ = other.start_;
      stop_ = other.stop_;
      other.start_ = nullptr;
      other.stop_ = nullptr;
    }
    return *this;
  }

  ~CudaEventTimer() { destroy(); }

  void record_start(cudaStream_t stream = nullptr) { CUDA_CHECK(cudaEventRecord(start_, stream)); }

  void record_stop(cudaStream_t stream = nullptr) { CUDA_CHECK(cudaEventRecord(stop_, stream)); }

  float elapsed_milliseconds() {
    CUDA_CHECK(cudaEventSynchronize(stop_));
    float milliseconds = 0.0f;
    CUDA_CHECK(cudaEventElapsedTime(&milliseconds, start_, stop_));
    return milliseconds;
  }

 private:
  void destroy() noexcept {
    if (start_ != nullptr) {
      cudaEventDestroy(start_);
      start_ = nullptr;
    }
    if (stop_ != nullptr) {
      cudaEventDestroy(stop_);
      stop_ = nullptr;
    }
  }

  cudaEvent_t start_{nullptr};
  cudaEvent_t stop_{nullptr};
};

template <typename T>
class DeviceBuffer {
 public:
  explicit DeviceBuffer(std::size_t count) : count_(count) {
    if (count_ > 0) {
      CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&ptr_), count_ * sizeof(T)));
    }
  }

  DeviceBuffer(const DeviceBuffer&) = delete;
  DeviceBuffer& operator=(const DeviceBuffer&) = delete;

  DeviceBuffer(DeviceBuffer&& other) noexcept : ptr_(other.ptr_), count_(other.count_) {
    other.ptr_ = nullptr;
    other.count_ = 0;
  }

  DeviceBuffer& operator=(DeviceBuffer&& other) noexcept {
    if (this != &other) {
      reset();
      ptr_ = other.ptr_;
      count_ = other.count_;
      other.ptr_ = nullptr;
      other.count_ = 0;
    }
    return *this;
  }

  ~DeviceBuffer() { reset(); }

  T* get() { return ptr_; }
  const T* get() const { return ptr_; }
  std::size_t count() const { return count_; }

  void copy_from_host(const T* source, std::size_t count) {
    CUDA_CHECK(cudaMemcpy(ptr_, source, count * sizeof(T), cudaMemcpyHostToDevice));
  }

  void copy_to_host(T* destination, std::size_t count) const {
    CUDA_CHECK(cudaMemcpy(destination, ptr_, count * sizeof(T), cudaMemcpyDeviceToHost));
  }

 private:
  void reset() noexcept {
    if (ptr_ != nullptr) {
      cudaFree(ptr_);
      ptr_ = nullptr;
    }
    count_ = 0;
  }

  T* ptr_{nullptr};
  std::size_t count_{0};
};

template <typename T>
class PinnedHostBuffer {
 public:
  explicit PinnedHostBuffer(std::size_t count) : count_(count) {
    if (count_ > 0) {
      CUDA_CHECK(cudaMallocHost(reinterpret_cast<void**>(&ptr_), count_ * sizeof(T)));
    }
  }

  PinnedHostBuffer(const PinnedHostBuffer&) = delete;
  PinnedHostBuffer& operator=(const PinnedHostBuffer&) = delete;

  PinnedHostBuffer(PinnedHostBuffer&& other) noexcept : ptr_(other.ptr_), count_(other.count_) {
    other.ptr_ = nullptr;
    other.count_ = 0;
  }

  PinnedHostBuffer& operator=(PinnedHostBuffer&& other) noexcept {
    if (this != &other) {
      reset();
      ptr_ = other.ptr_;
      count_ = other.count_;
      other.ptr_ = nullptr;
      other.count_ = 0;
    }
    return *this;
  }

  ~PinnedHostBuffer() { reset(); }

  T* get() { return ptr_; }
  const T* get() const { return ptr_; }
  T& operator[](std::size_t index) { return ptr_[index]; }
  const T& operator[](std::size_t index) const { return ptr_[index]; }
  std::size_t count() const { return count_; }

 private:
  void reset() noexcept {
    if (ptr_ != nullptr) {
      cudaFreeHost(ptr_);
      ptr_ = nullptr;
    }
    count_ = 0;
  }

  T* ptr_{nullptr};
  std::size_t count_{0};
};

template <typename T>
class ManagedBuffer {
 public:
  explicit ManagedBuffer(std::size_t count) : count_(count) {
    if (count_ > 0) {
      CUDA_CHECK(cudaMallocManaged(reinterpret_cast<void**>(&ptr_), count_ * sizeof(T)));
    }
  }

  ManagedBuffer(const ManagedBuffer&) = delete;
  ManagedBuffer& operator=(const ManagedBuffer&) = delete;

  ManagedBuffer(ManagedBuffer&& other) noexcept : ptr_(other.ptr_), count_(other.count_) {
    other.ptr_ = nullptr;
    other.count_ = 0;
  }

  ManagedBuffer& operator=(ManagedBuffer&& other) noexcept {
    if (this != &other) {
      reset();
      ptr_ = other.ptr_;
      count_ = other.count_;
      other.ptr_ = nullptr;
      other.count_ = 0;
    }
    return *this;
  }

  ~ManagedBuffer() { reset(); }

  T* get() { return ptr_; }
  const T* get() const { return ptr_; }
  T& operator[](std::size_t index) { return ptr_[index]; }
  const T& operator[](std::size_t index) const { return ptr_[index]; }
  std::size_t count() const { return count_; }

 private:
  void reset() noexcept {
    if (ptr_ != nullptr) {
      cudaFree(ptr_);
      ptr_ = nullptr;
    }
    count_ = 0;
  }

  T* ptr_{nullptr};
  std::size_t count_{0};
};

}  // namespace hipforge::level1

