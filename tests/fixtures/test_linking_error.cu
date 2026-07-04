#include <cuda_runtime.h>

// Declared but not defined. Fails linking on hipcc.
void undefined_function_call_that_fails_linking();

__global__ void vectorAdd(float* a, float* b, float* c, int n) {
    int i = threadIdx.x + blockIdx.x * blockDim.x;
    if (i < n) {
        c[i] = a[i] + b[i];
    }
}
int main() {
    // The patch agent must remove this call or define the function to compile successfully.
    undefined_function_call_that_fails_linking();
    return 0;
}
