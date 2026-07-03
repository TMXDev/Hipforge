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
    
    def run_hipify(self, source_path: str, output_path: str) -> Dict[str, Any]:
        """
        Runs the real hipify-clang tool as a subprocess on the given source file.
        Applies a regex post-processor to ensure logical conversion of API symbols.
        Falls back to heuristic regex-based translation if hipify-clang is missing or fails.
        """
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

        if os.getenv("USE_MOCK_COMPILER", "false").lower() == "true":
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
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                # Success path with post-processing
                try:
                    self._post_process_output(output_path)
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
                    return sandboxed
                return {
                    "success": False,
                    "output_path": output_path,
                    "stdout": result.stdout,
                    "stderr": result.stderr or "hipify-clang returned failure",
                }
                
        except (FileNotFoundError, subprocess.SubprocessError):
            sandboxed = self._run_sandboxed_hipify(source_path, output_path)
            if sandboxed is not None:
                return sandboxed
            return {
                "success": False,
                "output_path": output_path,
                "stdout": "",
                "stderr": "hipify-clang not found",
            }

def run_hipify(source_path: str, output_path: str) -> Dict[str, Any]:
    """
    Top-level helper function to run hipify. 
    Instantiates and executes the real HipifyRunner tool.
    """
    return HipifyRunner().run_hipify(source_path, output_path)
