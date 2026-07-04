# tests/e2e/projects.py
"""
Definitions and contents of the 6 test cases for the HIPForge E2E test harness.
"""

PROJECTS = {
    "vector_add": {
        "files": {
            "Makefile": """all:
\tnvcc vector_add.cu -o vector_add
""",
            "vector_add.cu": """#include <iostream>
#include <vector>
#include <cuda_runtime.h>

__global__ void vectorAdd(const float* a, const float* b, float* c, int n) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i < n) {
        c[i] = a[i] + b[i];
    }
}

int main() {
    const int N = 256;
    std::vector<float> h_a(N), h_b(N), h_c(N, 0.0f);
    for (int i = 0; i < N; ++i) {
        h_a[i] = i * 0.5f;
        h_b[i] = i * 2.0f;
    }

    int deviceCount = 0;
    cudaError_t err = cudaGetDeviceCount(&deviceCount);
    if (err == cudaSuccess && deviceCount > 0) {
        float *d_a, *d_b, *d_c;
        cudaMalloc(&d_a, N * sizeof(float));
        cudaMalloc(&d_b, N * sizeof(float));
        cudaMalloc(&d_c, N * sizeof(float));

        cudaMemcpy(d_a, h_a.data(), N * sizeof(float), cudaMemcpyHostToDevice);
        cudaMemcpy(d_b, h_b.data(), N * sizeof(float), cudaMemcpyHostToDevice);

        int threadsPerBlock = 256;
        int blocksPerGrid = (N + threadsPerBlock - 1) / threadsPerBlock;
        vectorAdd<<<blocksPerGrid, threadsPerBlock>>>(d_a, d_b, d_c, N);

        cudaMemcpy(h_c.data(), d_c, N * sizeof(float), cudaMemcpyDeviceToHost);

        cudaFree(d_a);
        cudaFree(d_b);
        cudaFree(d_c);
    } else {
        std::cout << "GPU NOT DETECTED: FALLING BACK TO CPU SIMULATION" << std::endl;
        for (int i = 0; i < N; ++i) {
            h_c[i] = h_a[i] + h_b[i];
        }
    }

    std::cout << "INPUT_A:";
    for (int i = 0; i < N; ++i) std::cout << (i ? "," : "") << h_a[i];
    std::cout << "\\nINPUT_B:";
    for (int i = 0; i < N; ++i) std::cout << (i ? "," : "") << h_b[i];
    std::cout << "\\nOUTPUT:";
    for (int i = 0; i < N; ++i) std::cout << (i ? "," : "") << h_c[i];
    std::cout << std::endl;
    return 0;
}
"""
        },
        "tolerance": {"abs": 1e-5, "rel": 1e-5},
        "forbidden_headers": ["cuda.h", "cuda_runtime.h", "device_launch_parameters.h"],
        "expected_result": "COMPLETED"
    },

    "gelu": {
        "files": {
            "Makefile": """all:
\tnvcc gelu.cu -o gelu
""",
            "gelu.cu": """#include <iostream>
#include <vector>
#include <cmath>
#include <cuda_runtime.h>

__global__ void geluKernel(const float* in, float* out, int n) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i < n) {
        float x = in[i];
        // GELU approximation: 0.5 * x * (1 + tanh(sqrt(2/pi) * (x + 0.044715 * x^3)))
        float c1 = 0.7978845608f; // sqrt(2/pi)
        float c2 = 0.044715f;
        float inner = c1 * (x + c2 * x * x * x);
        out[i] = 0.5f * x * (1.0f + tanhf(inner));
    }
}

int main() {
    const int N = 128;
    std::vector<float> h_in(N), h_out(N, 0.0f);
    for (int i = 0; i < N; ++i) {
        h_in[i] = (i - 64) * 0.1f;
    }

    int deviceCount = 0;
    cudaError_t err = cudaGetDeviceCount(&deviceCount);
    if (err == cudaSuccess && deviceCount > 0) {
        float *d_in, *d_out;
        cudaMalloc(&d_in, N * sizeof(float));
        cudaMalloc(&d_out, N * sizeof(float));

        cudaMemcpy(d_in, h_in.data(), N * sizeof(float), cudaMemcpyHostToDevice);

        int threadsPerBlock = 128;
        int blocksPerGrid = (N + threadsPerBlock - 1) / threadsPerBlock;
        geluKernel<<<blocksPerGrid, threadsPerBlock>>>(d_in, d_out, N);

        cudaMemcpy(h_out.data(), d_out, N * sizeof(float), cudaMemcpyDeviceToHost);

        cudaFree(d_in);
        cudaFree(d_out);
    } else {
        std::cout << "GPU NOT DETECTED: FALLING BACK TO CPU SIMULATION" << std::endl;
        for (int i = 0; i < N; ++i) {
            float x = h_in[i];
            float inner = 0.7978845608f * (x + 0.044715f * x * x * x);
            h_out[i] = 0.5f * x * (1.0f + std::tanh(inner));
        }
    }

    std::cout << "INPUT_A:";
    for (int i = 0; i < N; ++i) std::cout << (i ? "," : "") << h_in[i];
    std::cout << "\\nOUTPUT:";
    for (int i = 0; i < N; ++i) std::cout << (i ? "," : "") << h_out[i];
    std::cout << std::endl;
    return 0;
}
"""
        },
        "tolerance": {"abs": 1e-5, "rel": 1e-5},
        "forbidden_headers": ["cuda.h", "cuda_runtime.h", "device_launch_parameters.h"],
        "expected_result": "COMPLETED"
    },

    "tiled_matmul": {
        "files": {
            "Makefile": """all:
\tnvcc tiled_matmul.cu -o tiled_matmul
""",
            "tiled_matmul.cu": """#include <iostream>
#include <vector>
#include <cuda_runtime.h>

#define TILE_WIDTH 16

__global__ void matrixMulTiled(const float* A, const float* B, float* C, int width) {
    __shared__ float s_A[TILE_WIDTH][TILE_WIDTH];
    __shared__ float s_B[TILE_WIDTH][TILE_WIDTH];

    int bx = blockIdx.x;  int by = blockIdx.y;
    int tx = threadIdx.x; int ty = threadIdx.y;

    int row = by * TILE_WIDTH + ty;
    int col = bx * TILE_WIDTH + tx;

    float val = 0.0f;

    for (int ph = 0; ph < width / TILE_WIDTH; ++ph) {
        s_A[ty][tx] = A[row * width + ph * TILE_WIDTH + tx];
        s_B[ty][tx] = B[(ph * TILE_WIDTH + ty) * width + col];

        __syncthreads();

        for (int k = 0; k < TILE_WIDTH; ++k) {
            val += s_A[ty][k] * s_B[k][tx];
        }

        __syncthreads();
    }
    C[row * width + col] = val;
}

int main() {
    const int width = 32;
    const int size = width * width;
    std::vector<float> h_A(size), h_B(size), h_C(size, 0.0f);
    for (int i = 0; i < size; ++i) {
        h_A[i] = i * 0.01f;
        h_B[i] = (size - i) * 0.02f;
    }

    int deviceCount = 0;
    cudaError_t err = cudaGetDeviceCount(&deviceCount);
    if (err == cudaSuccess && deviceCount > 0) {
        float *d_A, *d_B, *d_C;
        cudaMalloc(&d_A, size * sizeof(float));
        cudaMalloc(&d_B, size * sizeof(float));
        cudaMalloc(&d_C, size * sizeof(float));

        cudaMemcpy(d_A, h_A.data(), size * sizeof(float), cudaMemcpyHostToDevice);
        cudaMemcpy(d_B, h_B.data(), size * sizeof(float), cudaMemcpyHostToDevice);

        dim3 dimBlock(TILE_WIDTH, TILE_WIDTH);
        dim3 dimGrid(width / TILE_WIDTH, width / TILE_WIDTH);

        matrixMulTiled<<<dimGrid, dimBlock>>>(d_A, d_B, d_C, width);

        cudaMemcpy(h_C.data(), d_C, size * sizeof(float), cudaMemcpyDeviceToHost);

        cudaFree(d_A);
        cudaFree(d_B);
        cudaFree(d_C);
    } else {
        std::cout << "GPU NOT DETECTED: FALLING BACK TO CPU SIMULATION" << std::endl;
        for (int r = 0; r < width; ++r) {
            for (int c = 0; c < width; ++c) {
                float val = 0.0f;
                for (int k = 0; k < width; ++k) {
                    val += h_A[r * width + k] * h_B[k * width + c];
                }
                h_C[r * width + c] = val;
            }
        }
    }

    std::cout << "INPUT_A:";
    for (int i = 0; i < size; ++i) std::cout << (i ? "," : "") << h_A[i];
    std::cout << "\\nINPUT_B:";
    for (int i = 0; i < size; ++i) std::cout << (i ? "," : "") << h_B[i];
    std::cout << "\\nOUTPUT:";
    for (int i = 0; i < size; ++i) std::cout << (i ? "," : "") << h_C[i];
    std::cout << std::endl;
    return 0;
}
"""
        },
        "tolerance": {"abs": 1e-4, "rel": 1e-4},
        "forbidden_headers": ["cuda.h", "cuda_runtime.h", "device_launch_parameters.h"],
        "expected_result": "COMPLETED"
    },

    "reduction": {
        "files": {
            "reduction.cu": """#include <iostream>
#include <vector>
#include <cuda_runtime.h>
#include "helper.cuh"

__global__ void warpReduceKernel(const float* in, float* out, int n) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    float val = (i < n) ? in[i] : 0.0f;
    val = warpReduceSum(val);
    if ((threadIdx.x & 31) == 0) {
        out[blockIdx.x * (blockDim.x / 32) + (threadIdx.x / 32)] = val;
    }
}

int main() {
    const int N = 256;
    std::vector<float> h_in(N), h_out(N / 32, 0.0f);
    for (int i = 0; i < N; ++i) {
        h_in[i] = i * 1.0f;
    }

    int deviceCount = 0;
    cudaError_t err = cudaGetDeviceCount(&deviceCount);
    if (err == cudaSuccess && deviceCount > 0) {
        float *d_in, *d_out;
        cudaMalloc(&d_in, N * sizeof(float));
        cudaMalloc(&d_out, (N / 32) * sizeof(float));

        cudaMemcpy(d_in, h_in.data(), N * sizeof(float), cudaMemcpyHostToDevice);

        warpReduceKernel<<<8, 32>>>(d_in, d_out, N);

        cudaMemcpy(h_out.data(), d_out, (N / 32) * sizeof(float), cudaMemcpyDeviceToHost);

        cudaFree(d_in);
        cudaFree(d_out);
    } else {
        std::cout << "GPU NOT DETECTED: FALLING BACK TO CPU SIMULATION" << std::endl;
        for (int b = 0; b < 8; ++b) {
            float sum = 0.0f;
            for (int t = 0; t < 32; ++t) {
                int i = b * 32 + t;
                sum += h_in[i];
            }
            h_out[b] = sum;
        }
    }

    std::cout << "INPUT_A:";
    for (int i = 0; i < N; ++i) std::cout << (i ? "," : "") << h_in[i];
    std::cout << "\\nOUTPUT:";
    for (size_t i = 0; i < h_out.size(); ++i) std::cout << (i ? "," : "") << h_out[i];
    std::cout << std::endl;
    return 0;
}
""",
            "helper.cuh": """#ifndef HELPER_CUH
#define HELPER_CUH

__device__ inline float warpReduceSum(float val) {
    for (int offset = 16; offset > 0; offset /= 2) {
        val += __shfl_down_sync(0xffffffff, val, offset);
    }
    return val;
}

#endif
"""
        },
        "tolerance": {"abs": 1e-5, "rel": 1e-5},
        "forbidden_headers": ["cuda.h", "cuda_runtime.h", "device_launch_parameters.h"],
        "expected_result": "COMPLETED"
    },

    "softmax": {
        "files": {
            "softmax.cu": """#include <iostream>
#include <vector>
#include <cmath>
#include <cuda.h>
#include <cuda_runtime.h>
#include <device_launch_parameters.h>

__global__ void softmaxKernel(const float* in, float* out, int n) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i < n) {
        float max_val = in[0];
        for (int k = 1; k < n; ++k) {
            if (in[k] > max_val) max_val = in[k];
        }
        float sum = 0.0f;
        for (int k = 0; k < n; ++k) {
            sum += expf(in[k] - max_val);
        }
        out[i] = expf(in[i] - max_val) / sum;
    }
}

int main() {
    const int N = 10;
    std::vector<float> h_in(N), h_out(N, 0.0f);
    for (int i = 0; i < N; ++i) {
        h_in[i] = i * 0.2f;
    }

    int deviceCount = 0;
    cudaError_t err = cudaGetDeviceCount(&deviceCount);
    if (err == cudaSuccess && deviceCount > 0) {
        float *d_in, *d_out;
        cudaMalloc(&d_in, N * sizeof(float));
        cudaMalloc(&d_out, N * sizeof(float));

        cudaMemcpy(d_in, h_in.data(), N * sizeof(float), cudaMemcpyHostToDevice);

        softmaxKernel<<<1, N>>>(d_in, d_out, N);

        cudaMemcpy(h_out.data(), d_out, N * sizeof(float), cudaMemcpyDeviceToHost);

        cudaFree(d_in);
        cudaFree(d_out);
    } else {
        std::cout << "GPU NOT DETECTED: FALLING BACK TO CPU SIMULATION" << std::endl;
        float max_val = h_in[0];
        for (int k = 1; k < N; ++k) {
            if (h_in[k] > max_val) max_val = h_in[k];
        }
        float sum = 0.0f;
        for (int k = 0; k < N; ++k) {
            sum += std::exp(h_in[k] - max_val);
        }
        for (int i = 0; i < N; ++i) {
            h_out[i] = std::exp(h_in[i] - max_val) / sum;
        }
    }

    std::cout << "INPUT_A:";
    for (int i = 0; i < N; ++i) std::cout << (i ? "," : "") << h_in[i];
    std::cout << "\\nOUTPUT:";
    for (int i = 0; i < N; ++i) std::cout << (i ? "," : "") << h_out[i];
    std::cout << std::endl;
    return 0;
}
"""
        },
        "tolerance": {"abs": 1e-5, "rel": 1e-5},
        "forbidden_headers": ["cuda.h", "cuda_runtime.h", "device_launch_parameters.h"],
        "expected_result": "COMPLETED"
    },

    "nested_project": {
        "files": {
            "include/common.h": """#ifndef COMMON_H
#define COMMON_H

#define VALUE_SCALE 2.5f

#endif
""",
            "include/special_#k.cuh": """#ifndef SPECIAL_H
#define SPECIAL_H
#include <cuda_runtime.h>

__global__ void nestedScaleKernel(const float* in, float* out, int n);

#endif
""",
            "src/special_char_#k.cu": """#include "../include/special_#k.cuh"
#include "../include/common.h"

__global__ void nestedScaleKernel(const float* in, float* out, int n) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i < n) {
        out[i] = in[i] * VALUE_SCALE;
    }
}
""",
            "src/main.cu": """#include <iostream>
#include <vector>
#include <cuda_runtime.h>
#include "../include/special_#k.cuh"
#include "../include/common.h"

int main() {
    const int N = 10;
    std::vector<float> h_in(N), h_out(N, 0.0f);
    for (int i = 0; i < N; ++i) {
        h_in[i] = i * 1.5f;
    }

    int deviceCount = 0;
    cudaError_t err = cudaGetDeviceCount(&deviceCount);
    if (err == cudaSuccess && deviceCount > 0) {
        float *d_in, *d_out;
        cudaMalloc(&d_in, N * sizeof(float));
        cudaMalloc(&d_out, N * sizeof(float));

        cudaMemcpy(d_in, h_in.data(), N * sizeof(float), cudaMemcpyHostToDevice);

        nestedScaleKernel<<<1, N>>>(d_in, d_out, N);

        cudaMemcpy(h_out.data(), d_out, N * sizeof(float), cudaMemcpyDeviceToHost);

        cudaFree(d_in);
        cudaFree(d_out);
    } else {
        std::cout << "GPU NOT DETECTED: FALLING BACK TO CPU SIMULATION" << std::endl;
        for (int i = 0; i < N; ++i) {
            h_out[i] = h_in[i] * VALUE_SCALE;
        }
    }

    std::cout << "INPUT_A:";
    for (int i = 0; i < N; ++i) std::cout << (i ? "," : "") << h_in[i];
    std::cout << "\\nOUTPUT:";
    for (int i = 0; i < N; ++i) std::cout << (i ? "," : "") << h_out[i];
    std::cout << std::endl;
    return 0;
}
"""
        },
        "tolerance": {"abs": 1e-5, "rel": 1e-5},
        "forbidden_headers": ["cuda.h", "cuda_runtime.h", "device_launch_parameters.h"],
        "expected_result": "COMPLETED"
    }
}
