#pragma once

#include <cuda_runtime.h>

#include <cstddef>
#include <sstream>
#include <stdexcept>
#include <string>

namespace hipforge::level2 {

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
  ::hipforge::level2::check_cuda((expression), #expression, __FILE__, __LINE__)

class Stream {
 public:
  Stream() { CUDA_CHECK(cudaStreamCreateWithFlags(&stream_, cudaStreamNonBlocking)); }

  Stream(const Stream&) = delete;
  Stream& operator=(const Stream&) = delete;

  Stream(Stream&& other) noexcept : stream_(other.stream_) { other.stream_ = nullptr; }

  Stream& operator=(Stream&& other) noexcept {
    if (this != &other) {
      destroy();
      stream_ = other.stream_;
      other.stream_ = nullptr;
    }
    return *this;
  }

  ~Stream() { destroy(); }

  cudaStream_t get() const { return stream_; }

  void synchronize() const { CUDA_CHECK(cudaStreamSynchronize(stream_)); }

 private:
  void destroy() noexcept {
    if (stream_ != nullptr) {
      cudaStreamDestroy(stream_);
      stream_ = nullptr;
    }
  }

  cudaStream_t stream_{nullptr};
};

class Event {
 public:
  Event() { CUDA_CHECK(cudaEventCreate(&event_)); }

  Event(const Event&) = delete;
  Event& operator=(const Event&) = delete;

  Event(Event&& other) noexcept : event_(other.event_) { other.event_ = nullptr; }

  Event& operator=(Event&& other) noexcept {
    if (this != &other) {
      destroy();
      event_ = other.event_;
      other.event_ = nullptr;
    }
    return *this;
  }

  ~Event() { destroy(); }

  cudaEvent_t get() const { return event_; }

  void record(cudaStream_t stream) { CUDA_CHECK(cudaEventRecord(event_, stream)); }

  void synchronize() const { CUDA_CHECK(cudaEventSynchronize(event_)); }

 private:
  void destroy() noexcept {
    if (event_ != nullptr) {
      cudaEventDestroy(event_);
      event_ = nullptr;
    }
  }

  cudaEvent_t event_{nullptr};
};

inline float elapsed_milliseconds(const Event& start, const Event& stop) {
  stop.synchronize();
  float milliseconds = 0.0f;
  CUDA_CHECK(cudaEventElapsedTime(&milliseconds, start.get(), stop.get()));
  return milliseconds;
}

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

class Array2D {
 public:
  Array2D(int width, int height, unsigned int flags = 0) : width_(width), height_(height) {
    const cudaChannelFormatDesc channel = cudaCreateChannelDesc<float>();
    CUDA_CHECK(cudaMallocArray(&array_, &channel, width_, height_, flags));
  }

  Array2D(const Array2D&) = delete;
  Array2D& operator=(const Array2D&) = delete;

  Array2D(Array2D&& other) noexcept
      : array_(other.array_), width_(other.width_), height_(other.height_) {
    other.array_ = nullptr;
    other.width_ = 0;
    other.height_ = 0;
  }

  Array2D& operator=(Array2D&& other) noexcept {
    if (this != &other) {
      destroy();
      array_ = other.array_;
      width_ = other.width_;
      height_ = other.height_;
      other.array_ = nullptr;
      other.width_ = 0;
      other.height_ = 0;
    }
    return *this;
  }

  ~Array2D() { destroy(); }

  cudaArray_t get() const { return array_; }
  int width() const { return width_; }
  int height() const { return height_; }

  void copy_from_host(const float* source) {
    CUDA_CHECK(cudaMemcpy2DToArray(array_,
                                   0,
                                   0,
                                   source,
                                   static_cast<std::size_t>(width_) * sizeof(float),
                                   static_cast<std::size_t>(width_) * sizeof(float),
                                   height_,
                                   cudaMemcpyHostToDevice));
  }

  void copy_to_host(float* destination) const {
    CUDA_CHECK(cudaMemcpy2DFromArray(destination,
                                     static_cast<std::size_t>(width_) * sizeof(float),
                                     array_,
                                     0,
                                     0,
                                     static_cast<std::size_t>(width_) * sizeof(float),
                                     height_,
                                     cudaMemcpyDeviceToHost));
  }

 private:
  void destroy() noexcept {
    if (array_ != nullptr) {
      cudaFreeArray(array_);
      array_ = nullptr;
    }
  }

  cudaArray_t array_{nullptr};
  int width_{0};
  int height_{0};
};

class Texture2D {
 public:
  explicit Texture2D(cudaArray_t array) {
    cudaResourceDesc resource{};
    resource.resType = cudaResourceTypeArray;
    resource.res.array.array = array;

    cudaTextureDesc texture{};
    texture.addressMode[0] = cudaAddressModeClamp;
    texture.addressMode[1] = cudaAddressModeClamp;
    texture.filterMode = cudaFilterModePoint;
    texture.readMode = cudaReadModeElementType;
    texture.normalizedCoords = 0;

    CUDA_CHECK(cudaCreateTextureObject(&texture_, &resource, &texture, nullptr));
  }

  Texture2D(const Texture2D&) = delete;
  Texture2D& operator=(const Texture2D&) = delete;

  Texture2D(Texture2D&& other) noexcept : texture_(other.texture_) { other.texture_ = 0; }

  Texture2D& operator=(Texture2D&& other) noexcept {
    if (this != &other) {
      destroy();
      texture_ = other.texture_;
      other.texture_ = 0;
    }
    return *this;
  }

  ~Texture2D() { destroy(); }

  cudaTextureObject_t get() const { return texture_; }

 private:
  void destroy() noexcept {
    if (texture_ != 0) {
      cudaDestroyTextureObject(texture_);
      texture_ = 0;
    }
  }

  cudaTextureObject_t texture_{0};
};

class Surface2D {
 public:
  explicit Surface2D(cudaArray_t array) {
    cudaResourceDesc resource{};
    resource.resType = cudaResourceTypeArray;
    resource.res.array.array = array;

    CUDA_CHECK(cudaCreateSurfaceObject(&surface_, &resource));
  }

  Surface2D(const Surface2D&) = delete;
  Surface2D& operator=(const Surface2D&) = delete;

  Surface2D(Surface2D&& other) noexcept : surface_(other.surface_) { other.surface_ = 0; }

  Surface2D& operator=(Surface2D&& other) noexcept {
    if (this != &other) {
      destroy();
      surface_ = other.surface_;
      other.surface_ = 0;
    }
    return *this;
  }

  ~Surface2D() { destroy(); }

  cudaSurfaceObject_t get() const { return surface_; }

 private:
  void destroy() noexcept {
    if (surface_ != 0) {
      cudaDestroySurfaceObject(surface_);
      surface_ = 0;
    }
  }

  cudaSurfaceObject_t surface_{0};
};

class GraphExec {
 public:
  explicit GraphExec(cudaGraph_t graph) {
    CUDA_CHECK(cudaGraphInstantiate(&exec_, graph, nullptr, nullptr, 0));
  }

  GraphExec(const GraphExec&) = delete;
  GraphExec& operator=(const GraphExec&) = delete;

  GraphExec(GraphExec&& other) noexcept : exec_(other.exec_) { other.exec_ = nullptr; }

  GraphExec& operator=(GraphExec&& other) noexcept {
    if (this != &other) {
      destroy();
      exec_ = other.exec_;
      other.exec_ = nullptr;
    }
    return *this;
  }

  ~GraphExec() { destroy(); }

  cudaGraphExec_t get() const { return exec_; }

 private:
  void destroy() noexcept {
    if (exec_ != nullptr) {
      cudaGraphExecDestroy(exec_);
      exec_ = nullptr;
    }
  }

  cudaGraphExec_t exec_{nullptr};
};

class CapturedGraph {
 public:
  explicit CapturedGraph(cudaGraph_t graph) : graph_(graph) {}

  CapturedGraph(const CapturedGraph&) = delete;
  CapturedGraph& operator=(const CapturedGraph&) = delete;

  CapturedGraph(CapturedGraph&& other) noexcept : graph_(other.graph_) { other.graph_ = nullptr; }

  CapturedGraph& operator=(CapturedGraph&& other) noexcept {
    if (this != &other) {
      destroy();
      graph_ = other.graph_;
      other.graph_ = nullptr;
    }
    return *this;
  }

  ~CapturedGraph() { destroy(); }

  cudaGraph_t get() const { return graph_; }

 private:
  void destroy() noexcept {
    if (graph_ != nullptr) {
      cudaGraphDestroy(graph_);
      graph_ = nullptr;
    }
  }

  cudaGraph_t graph_{nullptr};
};

}  // namespace hipforge::level2
