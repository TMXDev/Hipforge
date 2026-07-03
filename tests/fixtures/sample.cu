#include <cuda_runtime.h>
// HIPFORGE_MOCK_COMPILE_ERROR
__global__ void vectorAdd(float* a, float* b, float* c, int n) {
    int i = threadIdx.x + blockIdx.x * blockDim.x;
    if (i < n) {
        c[i] = a[i] + b[i];
    }
}
int main() {
    return 0;
}
