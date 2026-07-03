#pragma once

#include <cuda_runtime.h>

#include <sstream>
#include <stdexcept>

namespace hipforge::level4::detail {

inline void check_cuda(cudaError_t result, const char* expression, const char* file, int line) {
  if (result == cudaSuccess) {
    return;
  }
  std::ostringstream message;
  message << expression << " failed at " << file << ":" << line << ": "
          << cudaGetErrorString(result);
  throw std::runtime_error(message.str());
}

#define L4_CUDA_CHECK(expression) \
  ::hipforge::level4::detail::check_cuda((expression), #expression, __FILE__, __LINE__)

}  // namespace hipforge::level4::detail

