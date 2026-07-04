#include <cuda_runtime.h>
__global__ void vectorAdd(float* a, float* b, float* c, int n) {
    int i = threadIdx.x + blockIdx.x * blockDim.x;
    if (i < n) {
        c[i] = a[i] + b[i];
    }
}
void call_it() {
    #ifdef __HIP_PLATFORM_AMD__
    // Syntax error only visible to hipcc compiler after translation
    this is a compilation error trigger;
    #endif
}
int main() {
    return 0;
}
