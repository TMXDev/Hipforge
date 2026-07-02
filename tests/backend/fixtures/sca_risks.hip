// SCA test fixture — HIP source containing deliberate migration risk patterns.
// Used by tests/backend/test_sca.py to verify the Semantic Compatibility Analyzer.
//
// Patterns present (from docs/10_COMPILATION_PIPELINE.md):
//   1. Inline PTX              — asm volatile block (INLINE_PTX)
//   2. Texture References      — cudaCreateTextureObject (TEXTURE_REFERENCES)
//   3. Cooperative Groups      — cooperative_groups / cg::thread_block (COOPERATIVE_GROUPS)
//   4. Tensor Core intrinsics  — wmma:: namespace (TENSOR_CORE_INTRINSICS)
//   5. Thrust                  — #include <thrust/device_vector.h> (THRUST_USAGE)
//   6. CUB                     — #include <cub/cub.cuh> (CUB_USAGE)
//   7. Dynamic Shared Memory   — extern __shared__ float (DYNAMIC_SHARED_MEMORY)
//   8. Surface References      — surf2Dread (SURFACE_REFERENCES)
//   9. CUDA Graphs             — hipGraphCreate (CUDA_GRAPHS)
//  10. warpSize symbol         — warpSize (WARP_SIZE_ASSUMPTION_SYMBOL)

#include <hip/hip_runtime.h>
#include <cooperative_groups.h>
#include <thrust/device_vector.h>
#include <cub/cub.cuh>
#include <mma.h>

namespace cg = cooperative_groups;
using namespace nvcuda;

// Inline PTX — completely unsupported on AMD
__device__ void ptx_example(unsigned int* addr) {
    asm volatile("atom.global.add.u32 %0, [%1], 1;" : "=r"(*addr) : "l"(addr));
}

// Dynamic shared memory — valid but may have aliasing issues
__global__ void shared_mem_kernel(float* out, int n) {
    extern __shared__ float sdata[];
    int tid = threadIdx.x;
    if (tid < n) sdata[tid] = out[tid];
    __syncthreads();
    out[tid] = sdata[tid] * 2.0f;
}

// Cooperative groups — limited AMD support
__global__ void coop_kernel(int* data) {
    cg::thread_block block = cg::this_thread_block();
    block.sync();
    data[threadIdx.x] = threadIdx.x;
}

// Tensor Core / WMMA — NVIDIA-only
__global__ void wmma_kernel(float* c) {
    wmma::fragment<wmma::matrix_a, 16, 16, 16, __half, wmma::row_major> a_frag;
    wmma::fill_fragment(a_frag, 0.0f);
}

// Surface references — no HIP equivalent
__global__ void surf_kernel(hipSurfaceObject_t surf) {
    float val;
    surf2Dread(&val, surf, 0, 0);
}

// CUDA/HIP Graphs — limited ROCm support
void graph_example() {
    hipGraph_t graph;
    hipGraphCreate(&graph, 0);
}

// Texture object
void texture_example() {
    hipTextureObject_t tex;
    cudaCreateTextureObject(&tex, nullptr, nullptr, nullptr);
}

// warpSize usage — architecture-dependent
__global__ void warp_kernel(int* out) {
    int lane = threadIdx.x % warpSize;
    out[lane] = lane;
}
