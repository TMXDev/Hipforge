import os
import re
import subprocess
import logging
from typing import Dict, Any
from pathlib import Path

logger = logging.getLogger("hipify_runner")

def post_process_and_fallback_translate(content: str) -> str:
    """
    Cleans up common CUDA APIs, headers, and types to HIP equivalents.
    Acts as a post-processor for hipify-clang outputs and a fallback translator.
    """
    replacements = {
        r"\bcudaMalloc\b": "hipMalloc",
        r"\bcudaFree\b": "hipFree",
        r"\bcudaMemcpy\b": "hipMemcpy",
        r"\bcudaMemcpyHostToDevice\b": "hipMemcpyHostToDevice",
        r"\bcudaMemcpyDeviceToHost\b": "hipMemcpyDeviceToHost",
        r"\bcudaMemcpyDeviceToDevice\b": "hipMemcpyDeviceToDevice",
        r"\bcudaMemcpyDefault\b": "hipMemcpyDefault",
        r"\bcudaSuccess\b": "hipSuccess",
        r"\bcudaError_t\b": "hipError_t",
        r"\bcudaPeekAtLastError\b": "hipPeekAtLastError",
        r"\bcudaGetDeviceCount\b": "hipGetDeviceCount",
        r"\bcudaGetDevice\b": "hipGetDevice",
        r"\bcudaSetDevice\b": "hipSetDevice",
        r"\bcudaDeviceSynchronize\b": "hipDeviceSynchronize",
        r"\bcudaStream_t\b": "hipStream_t",
        r"\bcudaStreamCreate\b": "hipStreamCreate",
        r"\bcudaStreamCreateWithFlags\b": "hipStreamCreateWithFlags",
        r"\bcudaStreamNonBlocking\b": "hipStreamNonBlocking",
        r"\bcudaStreamSynchronize\b": "hipStreamSynchronize",
        r"\bcudaStreamDestroy\b": "hipStreamDestroy",
        r"\bcudaEvent_t\b": "hipEvent_t",
        r"\bcudaEventCreate\b": "hipEventCreate",
        r"\bcudaEventDestroy\b": "hipEventDestroy",
        r"\bcudaEventRecord\b": "hipEventRecord",
        r"\bcudaEventSynchronize\b": "hipEventSynchronize",
        r"\bcudaEventElapsedTime\b": "hipEventElapsedTime",
        r"\bcudaGetLastError\b": "hipGetLastError",
        r"\bcudaGetErrorString\b": "hipGetErrorString",
        r"\bcudaDeviceProp\b": "hipDeviceProp_t",
        r"\bcudaGetDeviceProperties\b": "hipGetDeviceProperties",
        r"\bcudaDeviceReset\b": "hipDeviceReset",
        r"\bcudaMallocHost\b": "hipHostMalloc",
        r"\bcudaFreeHost\b": "hipHostFree",
        r"\bcudaTextureObject_t\b": "hipTextureObject_t",
        r"\bcudaSurfaceObject_t\b": "hipSurfaceObject_t",
        r"\bcudaArraySurfaceLoadStore\b": "hipArraySurfaceLoadStore",
        r"\bcudaStreamBeginCapture\b": "hipStreamBeginCapture",
        r"\bcudaStreamCaptureModeGlobal\b": "hipStreamCaptureModeGlobal",
        r"\bcudaStreamEndCapture\b": "hipStreamEndCapture",
        r"\bcudaGraphLaunch\b": "hipGraphLaunch",
        r"\bcudaGraph_t\b": "hipGraph_t",
        r"\bcudaGraphExec_t\b": "hipGraphExec_t",
        r"\bcudaGraphInstantiate\b": "hipGraphInstantiate",
        r"\bcudaGraphExecDestroy\b": "hipGraphExecDestroy",
        r"\bcudaGraphDestroy\b": "hipGraphDestroy",
        r"\bcudaChannelFormatDesc\b": "hipChannelFormatDesc",
        r"\bcudaCreateChannelDesc\b": "hipCreateChannelDesc",
        r"\bcudaMallocArray\b": "hipMallocArray",
        r"\bcudaArray_t\b": "hipArray_t",
        r"\bcudaMemcpy2DToArray\b": "hipMemcpy2DToArray",
        r"\bcudaMemcpy2DFromArray\b": "hipMemcpy2DFromArray",
        r"\bcudaFreeArray\b": "hipFreeArray",
        r"\bcudaResourceDesc\b": "hipResourceDesc",
        r"\bcudaResourceTypeArray\b": "hipResourceTypeArray",
        r"\bcudaTextureDesc\b": "hipTextureDesc",
        r"\bcudaAddressModeClamp\b": "hipAddressModeClamp",
        r"\bcudaFilterModePoint\b": "hipFilterModePoint",
        r"\bcudaReadModeElementType\b": "hipReadModeElementType",
        r"\bcudaCreateTextureObject\b": "hipCreateTextureObject",
        r"\bcudaDestroyTextureObject\b": "hipDestroyTextureObject",
        r"\bcudaCreateSurfaceObject\b": "hipCreateSurfaceObject",
        r"\bcudaDestroySurfaceObject\b": "hipDestroySurfaceObject",
        r"<cuda_runtime\.h>": "<hip/hip_runtime.h>",
        r"<cuda_runtime_api\.h>": "<hip/hip_runtime_api.h>",
        r"<cuda\.h>": "<hip/hip_runtime.h>",
        r"<device_launch_parameters\.h>": "<hip/hip_runtime.h>",
        r"<cuda_fp16\.h>": "<hip/hip_fp16.h>",
        r"<cuda_bf16\.h>": "<hip/hip_bfloat16.h>",
        r"<cuda_profiler_api\.h>": "<hip/hip_runtime.h>",
        r"\bcudaMallocAsync\b": "hipMallocAsync",
        r"\bcudaFreeAsync\b": "hipFreeAsync",
        r"\bcudaMemcpyAsync\b": "hipMemcpyAsync",
        r"\bcudaMemset\b": "hipMemset",
        r"\bcudaMemsetAsync\b": "hipMemsetAsync",
        r"\bcudaMemset2D\b": "hipMemset2D",
        r"\bcudaMemset2DAsync\b": "hipMemset2DAsync",
        r"\bcudaMemset3D\b": "hipMemset3D",
        r"\bcudaMemset3DAsync\b": "hipMemset3DAsync",
        r"\bcudaStreamQuery\b": "hipStreamQuery",
        r"\bcudaStreamWaitEvent\b": "hipStreamWaitEvent",
        r"\bcudaDeviceCanAccessPeer\b": "hipDeviceCanAccessPeer",
        r"\bcudaDeviceEnablePeerAccess\b": "hipDeviceEnablePeerAccess",
        r"\bcudaDeviceDisablePeerAccess\b": "hipDeviceDisablePeerAccess",
        r"\bcudaHostRegister\b": "hipHostRegister",
        r"\bcudaHostUnregister\b": "hipHostUnregister",
        r"\bcudaHostGetDevicePointer\b": "hipHostGetDevicePointer",
        r"\bcudaMallocManaged\b": "hipMallocManaged",
        r"\bcudaPointerGetAttributes\b": "hipPointerGetAttributes",
        r"\bcudaFuncGetAttributes\b": "hipFuncGetAttributes",
        r"\bcudaFuncSetCacheConfig\b": "hipFuncSetCacheConfig",
        r"\bcudaDeviceSetCacheConfig\b": "hipFuncSetCacheConfig",
        r"\bcudaDeviceGetCacheConfig\b": "hipDeviceGetCacheConfig",
        r"\bcudaDeviceGetLimit\b": "hipDeviceGetLimit",
        r"\bcudaDeviceSetLimit\b": "hipDeviceSetLimit",
        r"\bcudaGetErrorName\b": "hipGetErrorName",
        r"\bcudaArray_const\b": "hipArray_const",
        r"\bcudaMipmappedArray\b": "hipMipmappedArray",
        r"\bcudaMipmappedArray_t\b": "hipMipmappedArray_t",
        r"\bcudaMalloc3D\b": "hipMalloc3D",
        r"\bcudaMalloc3DArray\b": "hipMalloc3DArray",
        r"\bcudaMallocMipmappedArray\b": "hipMallocMipmappedArray",
        r"\bcudaFreeMipmappedArray\b": "hipFreeMipmappedArray",
        r"\bcudaMemcpy3D\b": "hipMemcpy3D",
        r"\bcudaMemcpy3DPeer\b": "hipMemcpy3DPeer",
        r"\bcudaMemcpy3DAsync\b": "hipMemcpy3DAsync",
        r"\bcudaMemcpy3DPeerAsync\b": "hipMemcpy3DPeerAsync",
        r"\bcudaMemcpyPeer\b": "hipMemcpyPeer",
        r"\bcudaMemcpyPeerAsync\b": "hipMemcpyPeerAsync",
        r"\bcudaMemcpyToSymbol\b": "hipMemcpyToSymbol",
        r"\bcudaMemcpyFromSymbol\b": "hipMemcpyFromSymbol",
        r"\bcudaOccupancyMaxPotentialBlockSize\b": "hipOccupancyMaxPotentialBlockSize",
        r"\bcudaOccupancyMaxActiveBlocksPerMultiprocessor\b": "hipOccupancyMaxActiveBlocksPerMultiprocessor",
        r"\bCUdevice\b": "hipDevice_t",
        r"\bCUcontext\b": "hipCtx_t",
        r"\bCUmodule\b": "hipModule_t",
        r"\bCUfunction\b": "hipFunction_t",
        r"\bCUstream\b": "hipStream_t",
        r"\bCUevent\b": "hipEvent_t",
        r"\bCUdeviceptr\b": "hipDeviceptr_t",
        r"\bCUresult\b": "hipError_t",
        r"\bcuInit\b": "hipInit",
        r"\bcuDeviceGet\b": "hipDeviceGet",
        r"\bcuDeviceGetCount\b": "hipDeviceGetCount",
        r"\bcuDeviceGetName\b": "hipDeviceGetName",
        r"\bcuDeviceTotalMem\b": "hipDeviceTotalMem",
        r"\bcuCtxCreate\b": "hipCtxCreate",
        r"\bcuCtxDestroy\b": "hipCtxDestroy",
        r"\bcuCtxPushCurrent\b": "hipCtxPushCurrent",
        r"\bcuCtxPopCurrent\b": "hipCtxPopCurrent",
        r"\bcuCtxSetCurrent\b": "hipCtxSetCurrent",
        r"\bcuCtxGetCurrent\b": "hipCtxGetCurrent",
        r"\bcuCtxSynchronize\b": "hipCtxSynchronize",
        r"\bcuModuleLoad\b": "hipModuleLoad",
        r"\bcuModuleLoadData\b": "hipModuleLoadData",
        r"\bcuModuleUnload\b": "hipModuleUnload",
        r"\bcuModuleGetFunction\b": "hipModuleGetFunction",
        r"\bcuModuleGetGlobal\b": "hipModuleGetGlobal",
        r"\bcuMemAlloc\b": "hipMalloc",
        r"\bcuMemFree\b": "hipFree",
        r"\bcuMemcpyHtoD\b": "hipMemcpyHtoD",
        r"\bcuMemcpyDtoH\b": "hipMemcpyDtoH",
        r"\bcuMemcpyDtoD\b": "hipMemcpyDtoD",
        r"\bcuMemcpyHtoDAsync\b": "hipMemcpyHtoDAsync",
        r"\bcuMemcpyDtoHAsync\b": "hipMemcpyDtoHAsync",
        r"\bcuLaunchKernel\b": "hipModuleLaunchKernel",
        r"\bcuStreamCreate\b": "hipStreamCreate",
        r"\bcuStreamDestroy\b": "hipStreamDestroy",
        r"\bcuStreamSynchronize\b": "hipStreamSynchronize",
        r"\bcuEventCreate\b": "hipEventCreate",
        r"\bcuEventDestroy\b": "hipEventDestroy",
        r"\bcuEventRecord\b": "hipEventRecord",
        r"\bcuEventSynchronize\b": "hipEventSynchronize",
        r"\bcuEventElapsedTime\b": "hipEventElapsedTime",
        # ── cuBLAS → rocBLAS ─────────────────────────────────────────
        r"<cublas_v2\.h>": "<rocblas/rocblas.h>",
        r"<cublas\.h>": "<rocblas/rocblas.h>",
        r"\bcublasHandle_t\b": "rocblas_handle",
        r"\bcublasStatus_t\b": "rocblas_status",
        r"\bcublasOperation_t\b": "rocblas_operation",
        r"\bcublasCreate\b": "rocblas_create_handle",
        r"\bcublasDestroy\b": "rocblas_destroy_handle",
        r"\bcublasSetStream\b": "rocblas_set_stream",
        r"\bcublasGetStream\b": "rocblas_get_stream",
        r"\bcublasSgemm\b": "rocblas_sgemm",
        r"\bcublasDgemm\b": "rocblas_dgemm",
        r"\bcublasCgemm\b": "rocblas_cgemm",
        r"\bcublasZgemm\b": "rocblas_zgemm",
        r"\bcublasHgemm\b": "rocblas_hgemm",
        r"\bcublasSgemv\b": "rocblas_sgemv",
        r"\bcublasDgemv\b": "rocblas_dgemv",
        r"\bcublasSaxpy\b": "rocblas_saxpy",
        r"\bcublasDaxpy\b": "rocblas_daxpy",
        r"\bcublasScopy\b": "rocblas_scopy",
        r"\bcublasDcopy\b": "rocblas_dcopy",
        r"\bcublasSdot\b": "rocblas_sdot",
        r"\bcublasDdot\b": "rocblas_ddot",
        r"\bcublasSnrm2\b": "rocblas_snrm2",
        r"\bcublasDnrm2\b": "rocblas_dnrm2",
        r"\bcublasSscal\b": "rocblas_sscal",
        r"\bcublasDscal\b": "rocblas_dscal",
        r"\bcublasIsamin\b": "rocblas_isamin",
        r"\bcublasIdamin\b": "rocblas_idamin",
        r"\bcublasIsamax\b": "rocblas_isamax",
        r"\bcublasIdamax\b": "rocblas_idamax",
        r"\bcublasSgemmBatched\b": "rocblas_sgemm_batched",
        r"\bcublasDgemmBatched\b": "rocblas_dgemm_batched",
        r"\bcublasSgemmStridedBatched\b": "rocblas_sgemm_strided_batched",
        r"\bcublasDgemmStridedBatched\b": "rocblas_dgemm_strided_batched",
        r"\bcublasStrsm\b": "rocblas_strsm",
        r"\bcublasDtrsm\b": "rocblas_dtrsm",
        r"\bcublasSsyrk\b": "rocblas_ssyrk",
        r"\bcublasDsyrk\b": "rocblas_dsyrk",
        r"\bCUBLAS_OP_N\b": "rocblas_operation_none",
        r"\bCUBLAS_OP_T\b": "rocblas_operation_transpose",
        r"\bCUBLAS_OP_C\b": "rocblas_operation_conjugate_transpose",
        r"\bCUBLAS_STATUS_SUCCESS\b": "rocblas_status_success",
        # ── cuFFT → rocFFT ───────────────────────────────────────────
        r"<cufft\.h>": "<rocfft/rocfft.h>",
        r"<cufftXt\.h>": "<rocfft/rocfft.h>",
        r"\bcufftHandle\b": "rocfft_plan",
        r"\bcufftResult\b": "rocfft_status",
        r"\bcufftDestroy\b": "rocfft_plan_destroy",
        r"\bcufftExecC2C\b": "rocfft_execute",
        r"\bcufftExecR2C\b": "rocfft_execute",
        r"\bcufftExecC2R\b": "rocfft_execute",
        r"\bcufftExecZ2Z\b": "rocfft_execute",
        r"\bcufftExecD2Z\b": "rocfft_execute",
        r"\bcufftExecZ2D\b": "rocfft_execute",
        # ── cuRAND → rocRAND ─────────────────────────────────────────
        r"<curand\.h>": "<rocrand/rocrand.h>",
        r"<curand_kernel\.h>": "<rocrand/rocrand_kernel.h>",
        r"\bcurandGenerator_t\b": "rocrand_generator",
        r"\bcurandStatus_t\b": "rocrand_status",
        r"\bcurandCreateGenerator\b": "rocrand_create_generator",
        r"\bcurandDestroyGenerator\b": "rocrand_destroy_generator",
        r"\bcurandSetPseudoRandomGeneratorSeed\b": "rocrand_set_seed",
        r"\bcurandGenerateUniform\b": "rocrand_generate_uniform",
        r"\bcurandGenerateUniformDouble\b": "rocrand_generate_uniform_double",
        r"\bcurandGenerateNormal\b": "rocrand_generate_normal",
        r"\bcurandGenerateNormalDouble\b": "rocrand_generate_normal_double",
        r"\bcurandSetStream\b": "rocrand_set_stream",
        r"\bCURAND_RNG_PSEUDO_DEFAULT\b": "ROCRAND_RNG_PSEUDO_DEFAULT",
        r"\bCURAND_RNG_PSEUDO_XORWOW\b": "ROCRAND_RNG_PSEUDO_XORWOW",
        r"\bCURAND_RNG_PSEUDO_MRG32K3A\b": "ROCRAND_RNG_PSEUDO_MRG32K3A",
        r"\bCURAND_RNG_PSEUDO_PHILOX4_32_10\b": "ROCRAND_RNG_PSEUDO_PHILOX4_32_10",
        r"\bCURAND_STATUS_SUCCESS\b": "ROCRAND_STATUS_SUCCESS",
        # ── cuSPARSE → rocSPARSE ─────────────────────────────────────
        r"<cusparse\.h>": "<rocsparse/rocsparse.h>",
        r"\bcusparseHandle_t\b": "rocsparse_handle",
        r"\bcusparseStatus_t\b": "rocsparse_status",
        r"\bcusparseCreate\b": "rocsparse_create_handle",
        r"\bcusparseDestroy\b": "rocsparse_destroy_handle",
        r"\bcusparseSetStream\b": "rocsparse_set_stream",
        r"\bCUSPARSE_STATUS_SUCCESS\b": "rocsparse_status_success",
        # ── cuDNN → MIOpen ───────────────────────────────────────────
        # ponytail: MIOpen is not a 1:1 drop-in for cuDNN; these are
        # best-effort type/handle mappings. The AI agents will fix the
        # remaining API shape differences. upgrade path: full cuDNN→MIOpen AST rewriter
        r"<cudnn\.h>": "<miopen/miopen.h>",
        r"<cudnn_v8\.h>": "<miopen/miopen.h>",
        r"\bcudnnHandle_t\b": "miopenHandle_t",
        r"\bcudnnStatus_t\b": "miopenStatus_t",
        r"\bcudnnCreate\b": "miopenCreate",
        r"\bcudnnDestroy\b": "miopenDestroy",
        r"\bcudnnSetStream\b": "miopenSetStream",
        r"\bcudnnTensorDescriptor_t\b": "miopenTensorDescriptor_t",
        r"\bcudnnCreateTensorDescriptor\b": "miopenCreateTensorDescriptor",
        r"\bcudnnDestroyTensorDescriptor\b": "miopenDestroyTensorDescriptor",
        r"\bcudnnFilterDescriptor_t\b": "miopenTensorDescriptor_t",
        r"\bcudnnConvolutionDescriptor_t\b": "miopenConvolutionDescriptor_t",
        r"\bcudnnCreateConvolutionDescriptor\b": "miopenCreateConvolutionDescriptor",
        r"\bcudnnDestroyConvolutionDescriptor\b": "miopenDestroyConvolutionDescriptor",
        r"\bcudnnPoolingDescriptor_t\b": "miopenPoolingDescriptor_t",
        r"\bcudnnActivationDescriptor_t\b": "miopenActivationDescriptor_t",
        r"\bcudnnBatchNormMode_t\b": "miopenBatchNormMode_t",
        r"\bCUDNN_STATUS_SUCCESS\b": "miopenStatusSuccess",
        r"\bCUDNN_DATA_FLOAT\b": "miopenFloat",
        r"\bCUDNN_DATA_HALF\b": "miopenHalf",
        # ── cuSOLVER → rocSOLVER ─────────────────────────────────────
        r"<cusolverDn\.h>": "<rocsolver/rocsolver.h>",
        r"\bcusolverDnHandle_t\b": "rocblas_handle",
        r"\bcusolverDnCreate\b": "rocblas_create_handle",
        r"\bcusolverDnDestroy\b": "rocblas_destroy_handle",
        r"\bcusolverDnSetStream\b": "rocblas_set_stream",
        # ── NCCL → RCCL (same API surface) ───────────────────────────
        r"<nccl\.h>": "<rccl/rccl.h>",
        # ── Linker flags in Makefiles/build scripts ──────────────────
        r"-lcublas\b": "-lrocblas",
        r"-lcufft\b": "-lrocfft",
        r"-lcurand\b": "-lrocrand",
        r"-lcusparse\b": "-lrocsparse",
        r"-lcudnn\b": "-lMIOpen",
        r"-lcusolver\b": "-lrocsolver",
        r"-lnccl\b": "-lrccl",
    }

    processed = content
    for pattern, repl in replacements.items():
        processed = re.sub(pattern, repl, processed)

    # Ensure active mask is 64-bit for variable wavefront sizes (CDNA/RDNA compatibility)
    processed = re.sub(
        r"\b(__shfl|__ballot)(_up|_down|_xor)?_sync\(\s*0xffffffff\b",
        r"\1\2_sync(0xffffffffffffffffULL",
        processed
    )

    # Ensure warp size parameter in shuffles is dynamic (warpSize) instead of hardcoded 32
    processed = re.sub(
        r"\b(__shfl)(_up|_down|_xor)?_sync\(\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*32\s*\)",
        r"\1\2_sync(\3, \4, \5, warpSize)",
        processed
    )

    return processed

def needs_hipify(content: str) -> bool:
    """
    Check if the file content actually contains CUDA APIs, headers, or syntax
    that requires hipify-clang translation.
    """
    cuda_keywords = [
        "cuda", "cu", "__global__", "__device__", "__shared__", "<<<", ">>>",
        "blockidx", "threadidx", "blockdim", "griddim", "warpsize"
    ]
    content_lower = content.lower()
    return any(kw in content_lower for kw in cuda_keywords)

class HipifyRunner:
    """Real runner that executes the actual hipify-clang command line tool with regex post-processing and heuristic fallback."""

    def _infer_workspace_path(self, source_path: str) -> str | None:
        """Infer the migration workspace root from a workspace/input/... source path."""
        try:
            path = Path(source_path).resolve()
            for parent in path.parents:
                if parent.name == "input":
                    return str(parent.parent)
        except Exception:
            return None
        return None

    def _hipify_compile_args(self, source_path: str) -> list[str]:
        workspace_path = self._infer_workspace_path(source_path)
        if not workspace_path:
            return []

        input_dir = Path(workspace_path) / "input"
        include_dir = input_dir / "include"
        args = ["-I", str(input_dir)]
        if include_dir.exists():
            args.extend(["-I", str(include_dir)])

        extra_includes = getattr(self, "extra_include_dirs", None) or []
        for d in extra_includes:
            if d != str(input_dir) and d != str(include_dir):
                args.extend(["-I", d])

        arch = getattr(self, "cuda_parser_arch", None)
        if arch:
            args.append(f"--cuda-gpu-arch={arch}")

        cuda_path = getattr(self, "cuda_toolkit_path", None)
        if cuda_path:
            args.append(f"--cuda-path={cuda_path}")

        return args

    def _post_process_output(self, output_path: str) -> None:
        with open(output_path, "r", encoding="utf-8") as f:
            translated_content = f.read()
        final_content = post_process_and_fallback_translate(translated_content)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_content)

    def _run_sandboxed_hipify(self, source_path: str, output_path: str) -> Dict[str, Any] | None:
        workspace_path = self._infer_workspace_path(source_path)
        if not workspace_path:
            return None

        from app.compiler.sandbox import run_sandboxed_compiler

        logger.warning("Host hipify-clang unavailable or failed. Retrying with sandboxed hipify-clang.")
        sandbox_result = run_sandboxed_compiler(
            workspace_path,
            ["hipify-clang", source_path, "-o", output_path, "--", *self._hipify_compile_args(source_path)],
        )
        if sandbox_result["returncode"] != 0:
            return {
                "success": False,
                "output_path": output_path,
                "stdout": sandbox_result.get("stdout", ""),
                "stderr": sandbox_result.get("stderr", "") or "sandboxed hipify-clang failed",
            }

        try:
            self._post_process_output(output_path)
        except Exception as e:
            logger.warning("Sandboxed hipify post-processing failed: %s", e)

        return {
            "success": True,
            "output_path": output_path,
            "stdout": sandbox_result.get("stdout", "") + "\n[Sandbox HIPIFY] hipify-clang completed.",
            "stderr": sandbox_result.get("stderr", ""),
        }

    def _get_cache_path(self, source_path: str, content: str) -> tuple[Path, str]:
        """Compute the cache file path based on content hash."""
        import hashlib
        h = hashlib.sha256(content.encode("utf-8")).hexdigest()
        workspace_path = self._infer_workspace_path(source_path)
        if workspace_path:
            cache_dir = Path(workspace_path) / ".cache" / "hipify"
        else:
            cache_dir = Path(os.path.dirname(os.path.abspath(source_path))) / ".cache" / "hipify"
        return cache_dir / f"{h}.hip", h

    def run_hipify(
        self,
        source_path: str,
        output_path: str,
        extra_include_dirs: list[str] = None,
        cuda_parser_arch: str = None,
        cuda_toolkit_path: str = None,
    ) -> Dict[str, Any]:
        """
        Runs the real hipify-clang tool as a subprocess on the given source file.
        Applies a regex post-processor to ensure logical conversion of API symbols.
        Falls back to heuristic regex-based translation if hipify-clang is missing or fails.
        """
        self.extra_include_dirs = extra_include_dirs
        self.cuda_parser_arch = cuda_parser_arch
        self.cuda_toolkit_path = cuda_toolkit_path
        logger.info(f"Running translation on {source_path} -> {output_path}")

        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # Read source file content
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                source_content = f.read()
        except Exception as e:
            err_msg = f"Failed to read source file: {str(e)}"
            logger.error(err_msg)
            return {
                "success": False,
                "output_path": output_path,
                "stdout": "",
                "stderr": err_msg
            }

        # Check cache first (ponytail: caching to avoid redundant 30s Docker spawns)
        try:
            cache_file, content_hash = self._get_cache_path(source_path, source_content)
            if cache_file.exists():
                logger.info(f"[HIPIFY Cache Hit] Reusing cached translation for {source_path}")
                os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                with open(cache_file, "r", encoding="utf-8") as cf:
                    cached_translated = cf.read()
                with open(output_path, "w", encoding="utf-8") as out_f:
                    out_f.write(cached_translated)
                return {
                    "success": True,
                    "output_path": output_path,
                    "stdout": f"[Cache Hit] Successfully loaded from cache ({content_hash}).",
                    "stderr": ""
                }
        except Exception as e:
            logger.warning(f"Failed to read from hipify cache: {e}")

        # Check if the file actually needs hipify-clang (ponytail: bypass if no CUDA keywords)
        if not needs_hipify(source_content):
            logger.info(f"[HIPIFY Skip] {source_path} does not contain CUDA keywords. Translating via fallback (fast path).")
            translated = post_process_and_fallback_translate(source_content)
            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(translated)
                # Write to cache
                try:
                    cache_file, content_hash = self._get_cache_path(source_path, source_content)
                    os.makedirs(cache_file.parent, exist_ok=True)
                    with open(cache_file, "w", encoding="utf-8") as cf:
                        cf.write(translated)
                except Exception as ce:
                    logger.warning(f"Failed to write to cache: {ce}")

                return {
                    "success": True,
                    "output_path": output_path,
                    "stdout": "Translated successfully via fallback (no CUDA keywords)",
                    "stderr": "",
                }
            except Exception as e:
                err_msg = f"Failed to write output: {str(e)}"
                logger.error(err_msg)
                return {
                    "success": False,
                    "output_path": output_path,
                    "stdout": "",
                    "stderr": err_msg,
                }

        use_mock_compiler = os.getenv("USE_MOCK_COMPILER", "false").lower() == "true"
        if use_mock_compiler:
            try:
                from unittest.mock import Mock
                use_mock_compiler = not isinstance(subprocess.run, Mock)
            except Exception:
                pass

        if use_mock_compiler:
            if "HIPFORGE_MOCK_COMPILE_ERROR" in source_content:
                return {
                    "success": False,
                    "output_path": output_path,
                    "stdout": "",
                    "stderr": "error: hipify-clang mock failure triggered",
                }
            translated = post_process_and_fallback_translate(source_content)
            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(translated)
                return {
                    "success": True,
                    "output_path": output_path,
                    "stdout": "Translated successfully (mock hipify-clang)",
                    "stderr": "",
                }
            except Exception as e:
                err_msg = f"Mock hipify failed to write output: {str(e)}"
                logger.error(err_msg)
                return {
                    "success": False,
                    "output_path": output_path,
                    "stdout": "",
                    "stderr": err_msg,
                }

        cmd = ["hipify-clang", source_path, "-o", output_path, "--", *self._hipify_compile_args(source_path)]

        from app.config.settings import settings
        timeout_sec = getattr(settings, "TIMEOUT_HIPIFY", 30)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_sec
            )

            if result.returncode == 0:
                # Success path with post-processing
                try:
                    self._post_process_output(output_path)

                    # Write to cache
                    try:
                        with open(output_path, "r", encoding="utf-8") as f:
                            final_translated = f.read()
                        cache_file, content_hash = self._get_cache_path(source_path, source_content)
                        os.makedirs(cache_file.parent, exist_ok=True)
                        with open(cache_file, "w", encoding="utf-8") as cf:
                            cf.write(final_translated)
                    except Exception as ce:
                        logger.warning(f"Failed to write to cache: {ce}")

                    return {
                        "success": True,
                        "output_path": output_path,
                        "stdout": result.stdout + "\n[Post-Processing] Successfully cleaned up CUDA/HIP API symbols.",
                        "stderr": result.stderr
                    }
                except Exception as e:
                    logger.warning(f"Post-processing failed: {str(e)}. Returning original translation.")
                    return {
                        "success": True,
                        "output_path": output_path,
                        "stdout": result.stdout,
                        "stderr": result.stderr
                    }
            else:
                sandboxed = self._run_sandboxed_hipify(source_path, output_path)
                if sandboxed is not None:
                    if sandboxed.get("success"):
                        # Cache sandboxed success
                        try:
                            with open(output_path, "r", encoding="utf-8") as f:
                                final_translated = f.read()
                            cache_file, content_hash = self._get_cache_path(source_path, source_content)
                            os.makedirs(cache_file.parent, exist_ok=True)
                            with open(cache_file, "w", encoding="utf-8") as cf:
                                cf.write(final_translated)
                        except Exception as ce:
                            logger.warning(f"Failed to write to cache: {ce}")
                    return sandboxed
                return {
                    "success": False,
                    "output_path": output_path,
                    "stdout": result.stdout,
                    "stderr": result.stderr or "hipify-clang returned failure",
                }
        except subprocess.TimeoutExpired as te:
            err_msg = f"hipify-clang stage timed out after {timeout_sec} seconds."
            logger.error(err_msg)
            return {
                "success": False,
                "output_path": output_path,
                "stdout": "",
                "stderr": err_msg,
                "timeout": True
            }
        except (FileNotFoundError, subprocess.SubprocessError):
            sandboxed = self._run_sandboxed_hipify(source_path, output_path)
            if sandboxed is not None:
                if sandboxed.get("success"):
                    # Cache sandboxed success
                    try:
                        with open(output_path, "r", encoding="utf-8") as f:
                            final_translated = f.read()
                        cache_file, content_hash = self._get_cache_path(source_path, source_content)
                        os.makedirs(cache_file.parent, exist_ok=True)
                        with open(cache_file, "w", encoding="utf-8") as cf:
                            cf.write(final_translated)
                    except Exception as ce:
                        logger.warning(f"Failed to write to cache: {ce}")
                return sandboxed
            return {
                "success": False,
                "output_path": output_path,
                "stdout": "",
                "stderr": "hipify-clang not found",
            }

def discover_include_dirs(input_dir: Path) -> list[str]:
    # ponytail: find project-local include paths, secure against escaping symlinks/junctions
    discovered = set()
    input_dir_abs = input_dir.resolve()

    def is_safe_and_relative(p: Path) -> bool:
        try:
            resolved = p.resolve()
            return resolved.is_relative_to(input_dir_abs)
        except Exception:
            return False

    for name in ("include", "src"):
        candidate = input_dir_abs / name
        if candidate.is_dir() and is_safe_and_relative(candidate):
            discovered.add(str(candidate.resolve()))
            try:
                for p in candidate.rglob("*"):
                    if p.is_dir() and is_safe_and_relative(p):
                        discovered.add(str(p.resolve()))
            except Exception:
                pass

    for p in input_dir_abs.rglob("*"):
        if not is_safe_and_relative(p):
            continue
        if p.is_file() and (p.name.lower() in ("makefile", "cmakelists.txt") or p.suffix.lower() in (".mk", ".cmake")):
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                matches = re.findall(r'-I\s*([^\s"\']+)', content)
                for m in matches:
                    m = m.strip()
                    resolved_path = (p.parent / m).resolve()
                    if resolved_path.is_dir() and resolved_path.is_relative_to(input_dir_abs):
                        discovered.add(str(resolved_path))
            except Exception:
                pass

    supported_extensions = (".cu", ".hip", ".cpp", ".c", ".cuh", ".hpp", ".h")
    for p in input_dir_abs.rglob("*"):
        if not is_safe_and_relative(p):
            continue
        if p.is_file() and p.suffix.lower() in supported_extensions:
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                includes = re.findall(r'#\s*include\s*"([^"]+)"', content)
                for inc in includes:
                    inc_path = Path(inc)
                    for candidate_file in input_dir_abs.rglob(inc_path.name):
                        if not is_safe_and_relative(candidate_file):
                            continue
                        if candidate_file.is_file():
                            parts_inc = inc_path.parts
                            parts_cand = candidate_file.parts
                            if len(parts_cand) >= len(parts_inc):
                                match = True
                                for i in range(1, len(parts_inc) + 1):
                                    if parts_cand[-i] != parts_inc[-i]:
                                        match = False
                                        break
                                if match:
                                    inc_base = candidate_file.parents[len(parts_inc) - 1]
                                    if inc_base.is_dir() and is_safe_and_relative(inc_base):
                                        discovered.add(str(inc_base.resolve()))
            except Exception:
                pass

    # Final validation pass to be absolutely sure no escape occurred
    valid_discovered = set()
    for path_str in discovered:
        try:
            resolved_path = Path(path_str).resolve()
            if resolved_path.is_relative_to(input_dir_abs):
                valid_discovered.add(str(resolved_path))
        except Exception:
            pass

    valid_discovered.add(str(input_dir_abs))
    return sorted(list(valid_discovered))


def detect_cuda_arch(input_dir: Path) -> str | None:
    # ponytail: detect CUDA compiler arch flags in project build system
    for p in input_dir.rglob("*"):
        if p.is_file() and (p.name.lower() in ("makefile", "cmakelists.txt") or p.suffix.lower() in (".mk", ".cmake")):
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                match = re.search(r'\b(sm|compute)_(\d+)\b', content)
                if match:
                    return f"sm_{match.group(2)}"
            except Exception:
                pass
    return None

def detect_cuda_toolkit_path() -> str | None:
    # ponytail: detect default CUDA path
    if os.getenv("CUDA_PATH"):
        return os.getenv("CUDA_PATH")
    if os.getenv("CUDA_TOOLKIT_ROOT_DIR"):
        return os.getenv("CUDA_TOOLKIT_ROOT_DIR")
    for path_str in ("/usr/local/cuda",):
        c = Path(path_str)
        if c.is_dir():
            return str(c)
    try:
        usr_local = Path("/usr/local")
        if usr_local.is_dir():
            for sub in usr_local.iterdir():
                if sub.is_dir() and sub.name.startswith("cuda-"):
                    return str(sub)
    except Exception:
        pass
    win_paths = [
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
    ]
    for wp in win_paths:
        p = Path(wp)
        if p.is_dir():
            try:
                for sub in p.iterdir():
                    if sub.is_dir():
                        return str(sub)
            except Exception:
                pass
    return None

def run_hipify(source_path: str, output_path: str, **kwargs) -> Dict[str, Any]:
    """
    Top-level helper function to run hipify.
    Instantiates and executes the real HipifyRunner tool.
    """
    return HipifyRunner().run_hipify(source_path, output_path, **kwargs)
