#pragma once

#include <cuda_runtime.h>

#include <cstddef>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace hipforge::level3 {

inline void check_cuda(cudaError_t result, const char* expression, const char* file, int line) {
  if (result == cudaSuccess) {
    return;
  }
  std::ostringstream message;
  message << expression << " failed at " << file << ":" << line << ": "
          << cudaGetErrorString(result);
  throw std::runtime_error(message.str());
}

#define CUDA_CHECK(expression) \
  ::hipforge::level3::check_cuda((expression), #expression, __FILE__, __LINE__)

class Stream {
 public:
  Stream() { CUDA_CHECK(cudaStreamCreateWithFlags(&stream_, cudaStreamNonBlocking)); }
  Stream(const Stream&) = delete;
  Stream& operator=(const Stream&) = delete;
  Stream(Stream&& other) noexcept : stream_(other.stream_) { other.stream_ = nullptr; }
  Stream& operator=(Stream&& other) noexcept {
    if (this != &other) {
      reset();
      stream_ = other.stream_;
      other.stream_ = nullptr;
    }
    return *this;
  }
  ~Stream() { reset(); }
  cudaStream_t get() const { return stream_; }
  void synchronize() const { CUDA_CHECK(cudaStreamSynchronize(stream_)); }

 private:
  void reset() noexcept {
    if (stream_ != nullptr) {
      cudaStreamDestroy(stream_);
      stream_ = nullptr;
    }
  }

  cudaStream_t stream_{nullptr};
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

  void copy_from_host(const T* source, std::size_t count, cudaStream_t stream = nullptr) {
    CUDA_CHECK(cudaMemcpyAsync(ptr_, source, count * sizeof(T), cudaMemcpyHostToDevice, stream));
  }

  void copy_to_host(T* destination, std::size_t count, cudaStream_t stream = nullptr) const {
    CUDA_CHECK(cudaMemcpyAsync(destination, ptr_, count * sizeof(T), cudaMemcpyDeviceToHost, stream));
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

}  // namespace hipforge::level3

