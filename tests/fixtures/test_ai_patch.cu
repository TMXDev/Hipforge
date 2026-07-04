#include <cuda_runtime.h>
__global__ void add(float* a, float* b, float* c, int n) {
    int idx = threadIdx.x + blockIdx.x * blockDim.x;
    if (idx < n) {
        c[idx] = a[idx] + b[idx];
    }
}
void call_kernel(float* a, float* b, float* c, int n) {
    // Wrong API name to trigger compile error and AI patch agent
    cudaMemcpy_WRONG_NAME(c, a, n * sizeof(float), cudaMemcpyDeviceToDevice);
}
int main() {
    return 0;
}
