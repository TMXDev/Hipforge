import re
import json
import logging
from pathlib import Path
from app.workflow_engine.context import WorkflowContext

logger = logging.getLogger("validator")

# Match identifiers starting with 'cuda', camelCase or uppercase with underscores.
# Example: cudaMalloc, cudaError_t, cudaMemcpyHostToDevice
CUDA_API_PATTERN = re.compile(r"\bcuda[A-Z_][a-zA-Z0-9_]*\b")

CUDA_TO_HIP_MAP = {
    "cudaMalloc": "hipMalloc",
    "cudaMallocManaged": "hipMallocManaged",
    "cudaFree": "hipFree",
    "cudaMemcpy": "hipMemcpy",
    "cudaMemcpyAsync": "hipMemcpyAsync",
    "cudaMemcpyToSymbol": "hipMemcpyToSymbol",
    "cudaMemcpyFromSymbol": "hipMemcpyFromSymbol",
    "cudaMemcpyDefault": "hipMemcpyDefault",
    "cudaMemcpyHostToDevice": "hipMemcpyHostToDevice",
    "cudaMemcpyDeviceToHost": "hipMemcpyDeviceToHost",
    "cudaMemcpyDeviceToDevice": "hipMemcpyDeviceToDevice",
    "cudaMemset": "hipMemset",
    "cudaPeekAtLastError": "hipPeekAtLastError",
    "cudaEventCreate": "hipEventCreate",
    "cudaEventCreateWithFlags": "hipEventCreateWithFlags",
    "cudaEventDestroy": "hipEventDestroy",
    "cudaEventRecord": "hipEventRecord",
    "cudaEventSynchronize": "hipEventSynchronize",
    "cudaEventElapsedTime": "hipEventElapsedTime",
    "cudaEvent_t": "hipEvent_t",
    "cudaStreamCreate": "hipStreamCreate",
    "cudaStreamCreateWithFlags": "hipStreamCreateWithFlags",
    "cudaStreamNonBlocking": "hipStreamNonBlocking",
    "cudaStreamSynchronize": "hipStreamSynchronize",
    "cudaStreamDestroy": "hipStreamDestroy",
    "cudaStream_t": "hipStream_t",
    "cudaLaunchKernel": "hipLaunchKernel",
    "cudaDeviceSynchronize": "hipDeviceSynchronize",
    "cudaGetDevice": "hipGetDevice",
    "cudaGetDeviceCount": "hipGetDeviceCount",
    "cudaSetDevice": "hipSetDevice",
    "cudaGetLastError": "hipGetLastError",
    "cudaGetErrorString": "hipGetErrorString",
    "cudaSuccess": "hipSuccess",
    "cudaError_t": "hipError_t",
    "cudaDeviceProp": "hipDeviceProp_t",
    "cudaGetDeviceProperties": "hipGetDeviceProperties",
    "cudaDeviceReset": "hipDeviceReset",
    "cudaHostAlloc": "hipHostAlloc",
    "cudaMallocHost": "hipHostMalloc",
    "cudaFreeHost": "hipHostFree",
    "cudaTextureObject_t": "hipTextureObject_t",
    "cudaSurfaceObject_t": "hipSurfaceObject_t",
    "cudaArraySurfaceLoadStore": "hipArraySurfaceLoadStore",
    "cudaStreamBeginCapture": "hipStreamBeginCapture",
    "cudaStreamCaptureModeGlobal": "hipStreamCaptureModeGlobal",
    "cudaStreamEndCapture": "hipStreamEndCapture",
    "cudaGraphLaunch": "hipGraphLaunch",
    "cudaGraph_t": "hipGraph_t",
    "cudaGraphExec_t": "hipGraphExec_t",
    "cudaGraphInstantiate": "hipGraphInstantiate",
    "cudaGraphExecDestroy": "hipGraphExecDestroy",
    "cudaGraphDestroy": "hipGraphDestroy",
    "cudaChannelFormatDesc": "hipChannelFormatDesc",
    "cudaCreateChannelDesc": "hipCreateChannelDesc",
    "cudaMallocArray": "hipMallocArray",
    "cudaArray_t": "hipArray_t",
    "cudaMemcpy2DToArray": "hipMemcpy2DToArray",
    "cudaMemcpy2DFromArray": "hipMemcpy2DFromArray",
    "cudaFreeArray": "hipFreeArray",
    "cudaResourceDesc": "hipResourceDesc",
    "cudaResourceTypeArray": "hipResourceTypeArray",
    "cudaTextureDesc": "hipTextureDesc",
    "cudaAddressModeClamp": "hipAddressModeClamp",
    "cudaFilterModePoint": "hipFilterModePoint",
    "cudaReadModeElementType": "hipReadModeElementType",
    "cudaCreateTextureObject": "hipCreateTextureObject",
    "cudaDestroyTextureObject": "hipDestroyTextureObject",
    "cudaCreateSurfaceObject": "hipCreateSurfaceObject",
    "cudaDestroySurfaceObject": "hipDestroySurfaceObject",
}


def scan_ast_for_cuda_apis(file_path: Path) -> dict:
    """
    Uses clang.cindex AST parsing to semantically detect unresolved CUDA APIs/types/constants,
    and merges them with regex-based scanning to ensure 100% coverage.
    """
    import os
    
    # 1. Run regex scan first to ensure all text occurrences are captured
    results = scan_file_for_cuda_apis(file_path)
    
    # 2. Try to run AST scan to get precise semantic line mapping and additional details
    try:
        import clang.cindex
        index = clang.cindex.Index.create()
        # Parse using standard C++ mode for header files and CUDA/HIP code compatibility
        args = ["-x", "c++", "-D__HIP_PLATFORM_AMD__=1"]
        tu = index.parse(str(file_path), args=args)
        
        canonical_path = os.path.realpath(file_path).lower()
        
        def traverse(node):
            if node.location.file:
                node_file = os.path.realpath(node.location.file.name).lower()
                if node_file == canonical_path:
                    # Check spelling and kind for CUDA references
                    spelling = node.spelling
                    displayname = node.displayname
                    
                    for symbol in (spelling, displayname):
                        if symbol and symbol.startswith("cuda"):
                            # Normalize/clean symbol name (e.g. remove template arguments or parameter list)
                            clean_symbol = symbol.split("<")[0].split("(")[0].strip()
                            if clean_symbol.startswith("cuda") and (len(clean_symbol) <= 4 or clean_symbol[4].isupper() or clean_symbol[4] == "_"):
                                line = node.location.line
                                if clean_symbol not in results:
                                    results[clean_symbol] = []
                                if line not in results[clean_symbol]:
                                    results[clean_symbol].append(line)
                                    
            for child in node.get_children():
                traverse(child)
                
        traverse(tu.cursor)
    except Exception as e:
        logger.debug(f"[AST Validation] AST parsing failed or libclang unavailable ({e}). Relying on regex.")
        
    return results


def scan_file_for_cuda_apis(file_path: Path) -> dict:
    """
    Scans a source file line-by-line for CUDA APIs.
    Returns a dict mapping CUDA API name -> list of 1-based line numbers.
    """
    results = {}
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        for line_num, line in enumerate(content.splitlines(), start=1):
            for match in CUDA_API_PATTERN.finditer(line):
                api_name = match.group(0)
                if api_name not in results:
                    results[api_name] = []
                results[api_name].append(line_num)
    except Exception as e:
        logger.error(f"Error scanning file {file_path} for CUDA APIs: {e}")
    return results


def replace_cuda_apis_in_file(file_path: Path, mapping: dict) -> int:
    """
    Deterministically replaces known CUDA APIs in a file with their HIP equivalents.
    Returns the total count of replacements made.
    """
    replacements_made = 0
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        new_content = content
        for cuda_api, hip_api in mapping.items():
            pattern = re.compile(rf"\b{cuda_api}\b")
            new_content, count = pattern.subn(hip_api, new_content)
            replacements_made += count
            
        if replacements_made > 0:
            file_path.write_text(new_content, encoding="utf-8")
    except Exception as e:
        logger.error(f"Error replacing CUDA APIs in file {file_path}: {e}")
    return replacements_made


async def validate_and_replace_cuda_apis(context: WorkflowContext):
    """
    Validation stage run immediately after hipify completes.
    Detects remaining CUDA APIs, performs safe deterministic replacements,
    and updates the context with migration validation metrics.
    """
    workspace = Path(context.workspace_path)
    input_dir = workspace / "input"
    generated_dir = workspace / "generated"
    
    # 1. Scan original uploaded files in input_dir using AST validation
    initial_cuda_apis = {}
    for file_path in input_dir.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in (".cu", ".cuh", ".hip", ".cpp", ".hpp", ".h"):
            apis = scan_ast_for_cuda_apis(file_path)
            for api, lines in apis.items():
                if api not in initial_cuda_apis:
                    initial_cuda_apis[api] = 0
                initial_cuda_apis[api] += len(lines)
                
    # 2. Scan generated files in generated_dir before validation replacements using AST validation
    generated_cuda_apis_before = {}
    for file_path in generated_dir.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in (".hip", ".cuh", ".cpp", ".hpp", ".h"):
            apis = scan_ast_for_cuda_apis(file_path)
            for api, lines in apis.items():
                if api not in generated_cuda_apis_before:
                    generated_cuda_apis_before[api] = 0
                generated_cuda_apis_before[api] += len(lines)
                
    # 3. Perform deterministic replacements in generated files
    replacements_count = 0
    for file_path in generated_dir.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in (".hip", ".cuh", ".cpp", ".hpp", ".h"):
            replacements_count += replace_cuda_apis_in_file(file_path, CUDA_TO_HIP_MAP)
            
    # 4. Scan generated files again to find remaining CUDA APIs using AST validation
    generated_cuda_apis_after = {}
    for file_path in generated_dir.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in (".hip", ".cuh", ".cpp", ".hpp", ".h"):
            apis = scan_ast_for_cuda_apis(file_path)
            for api, lines in apis.items():
                if api not in generated_cuda_apis_after:
                    generated_cuda_apis_after[api] = 0
                generated_cuda_apis_after[api] += len(lines)
                
    # Calculate metrics
    cuda_apis_detected = sum(initial_cuda_apis.values())
    cuda_apis_remaining = sum(generated_cuda_apis_after.values())
    cuda_apis_converted = max(0, cuda_apis_detected - cuda_apis_remaining)
    
    # Store metrics in context
    context.cuda_apis_detected = cuda_apis_detected
    context.cuda_apis_converted = cuda_apis_converted
    context.cuda_apis_remaining = cuda_apis_remaining
    context.initial_cuda_apis_detail = initial_cuda_apis
    context.remaining_cuda_apis_detail = generated_cuda_apis_after
    
    # Track modified files in the workspace
    modified_files = []
    for file_path in generated_dir.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in (".hip", ".cuh", ".cpp", ".hpp", ".h"):
            modified_files.append(str(file_path.relative_to(workspace)))
    context.files_modified = modified_files
    
    logger.info(
        f"[Validation] CUDA API scan completed: detected={cuda_apis_detected}, "
        f"converted={cuda_apis_converted}, remaining={cuda_apis_remaining}, "
        f"validation_replacements={replacements_count}"
    )
    
    # Write metadata/metrics to a validation JSON artifact in the workspace
    artifacts_dir = workspace / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    validation_report_path = artifacts_dir / "migration_validation.json"
    
    report_data = {
        "cuda_apis_detected": cuda_apis_detected,
        "cuda_apis_converted": cuda_apis_converted,
        "cuda_apis_remaining": cuda_apis_remaining,
        "initial_cuda_apis_detail": initial_cuda_apis,
        "remaining_cuda_apis_detail": generated_cuda_apis_after,
        "replacements_made_during_validation": replacements_count
    }
    
    try:
        with open(validation_report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
        logger.info(f"[Validation] validation json report written to {validation_report_path}")
    except Exception as e:
        logger.error(f"Failed to write validation report json: {e}")
