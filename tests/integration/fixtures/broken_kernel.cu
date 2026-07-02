#include <hip/hip_runtime.h>

// CUDAFORGE_MOCK_COMPILE_ERROR
// This trigger keyword causes MockHipccRunner to fail compilation and produce mock compiler errors.

__global__ void broken_kernel(float* dst, float* src, int n) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < n) {
        dst[idx] = src[idx];
    }
}

void transfer_data(float* dst, float* src, int n, hipStream_t s) {
    hipMemcpyAsync_WRONG(dst, src, n * sizeof(float), hipMemcpyDeviceToDevice, s);
}
