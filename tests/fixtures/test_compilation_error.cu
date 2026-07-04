#include <cuda_runtime.h>
__global__ void vectorAdd(float* a, float* b, float* c, int n) {
    int i = threadIdx.x + blockIdx.x * blockDim.x;
    if (i < n) {
        c[i] = a[i] + b[i];
    }
}
void trigger_error() {
    #ifndef __CUDACC__
    #error "ROCM_COMPILER_ERROR: This must be removed by the patch agent"
    #endif
}
int main() {
    return 0;
}
