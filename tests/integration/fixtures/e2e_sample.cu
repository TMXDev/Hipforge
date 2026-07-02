/*
 * e2e_sample.cu
 *
 * HIPForge E2E test fixture — a CUDA source file that:
 *   1. Contains recognisable CUDA API calls so hipify-clang (mock) has content to process.
 *   2. Contains CUDAFORGE_MOCK_COMPILE_ERROR to trigger mock hipcc failure on first attempt.
 *   3. Is small enough to be processed quickly in CI.
 */

#include <cuda_runtime.h>
#include <stdio.h>

// CUDAFORGE_MOCK_COMPILE_ERROR
// This sentinel causes MockHipccRunner to fail the first compilation attempt,
// exercising the full ANALYZING -> PATCHING -> RESEARCHING -> COMPILING repair loop.

__global__ void vector_add(float* a, float* b, float* c, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        c[i] = a[i] + b[i];
    }
}

int main(void) {
    int n = 1024;
    size_t bytes = n * sizeof(float);

    float *d_a, *d_b, *d_c;
    cudaMalloc(&d_a, bytes);
    cudaMalloc(&d_b, bytes);
    cudaMalloc(&d_c, bytes);

    float *h_a = (float*)malloc(bytes);
    float *h_b = (float*)malloc(bytes);
    float *h_c = (float*)malloc(bytes);

    for (int i = 0; i < n; i++) {
        h_a[i] = (float)i;
        h_b[i] = (float)(n - i);
    }

    cudaMemcpy(d_a, h_a, bytes, cudaMemcpyHostToDevice);
    cudaMemcpy(d_b, h_b, bytes, cudaMemcpyHostToDevice);

    int threads = 256;
    int blocks = (n + threads - 1) / threads;
    vector_add<<<blocks, threads>>>(d_a, d_b, d_c, n);

    cudaMemcpy(h_c, d_c, bytes, cudaMemcpyDeviceToHost);

    printf("c[0] = %f\n", h_c[0]);

    cudaFree(d_a);
    cudaFree(d_b);
    cudaFree(d_c);
    free(h_a);
    free(h_b);
    free(h_c);

    return 0;
}
