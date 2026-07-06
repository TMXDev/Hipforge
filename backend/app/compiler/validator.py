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


def find_matching_brace(text: str, start_pos: int) -> int:
    """Finds the index of the matching closing brace for the opening brace at start_pos."""
    brace_count = 0
    in_string = False
    in_char = False
    escape = False
    in_comment = False
    in_line_comment = False
    
    for i in range(start_pos, len(text)):
        char = text[i]
        
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
            
        if in_line_comment:
            if char == '\n':
                in_line_comment = False
            continue
        if in_comment:
            if char == '/' and i > 0 and text[i-1] == '*':
                in_comment = False
            continue
            
        if in_string:
            if char == '"':
                in_string = False
            continue
        if in_char:
            if char == "'":
                in_char = False
            continue
            
        if char == '"':
            in_string = True
            continue
        if char == "'":
            in_char = True
            continue
        if char == '/' and i + 1 < len(text) and text[i+1] == '/':
            in_line_comment = True
            continue
        if char == '/' and i + 1 < len(text) and text[i+1] == '*':
            in_comment = True
            continue
            
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                return i
    return -1


def harden_hip_content(content: str, validation_enabled: bool = False) -> tuple[str, dict]:
    """
    Scans for run_xxx launcher functions and inserts pointer, N <= 0 guards,
    hipGetLastError(), and optionally hipDeviceSynchronize().
    """
    stats = {
        "launcher_expects_device_pointers": "N/A",
        "kernel_launch_error_checks": "none",
        "synchronization_status": "none"
    }
    
    # Pattern to find void run_xxx(...) signature and the opening {
    pattern = re.compile(r'(extern\s+"C"\s+)?void\s+(run_\w+)\s*\(([^)]*)\)\s*\{', re.MULTILINE)
    
    matches = list(pattern.finditer(content))
    if not matches:
        return content, stats

    # Sort matches in descending order of start position to replace from back to front
    matches.sort(key=lambda m: m.start(), reverse=True)
    
    new_content = content
    has_launcher = False
    
    for match in matches:
        extern_c = match.group(1)
        func_name = match.group(2)
        params_str = match.group(3)
        start_pos = match.end() - 1  # index of '{'
        
        # Match braces to get body
        end_pos = find_matching_brace(new_content, start_pos)
        if end_pos == -1:
            continue
            
        has_launcher = True
        body = new_content[start_pos + 1 : end_pos]
        
        # Parse pointer parameter names
        pointer_names = []
        for p in params_str.split(','):
            p = p.strip()
            if '*' in p:
                ptr_match = re.search(r'\*\s*(\w+)', p)
                if ptr_match:
                    pointer_names.append(ptr_match.group(1))
                    
        # Parse size parameter name
        size_name = None
        for p in params_str.split(','):
            p = p.strip()
            size_match = re.search(r'\b(int|size_t|unsigned)\b.*\b(N|n|size|count|num_elements|len|length)\b', p)
            if size_match:
                size_name = size_match.group(2)
                break
                
        # Analyze existing guards
        has_existing_guards = ("nullptr" in body or "NULL" in body or "<= 0" in body)
        has_kernel_launch = "<<" in body  # Match <<< or general hipLaunchKernel
        has_error_check = "hipGetLastError" in body or "hipPeekAtLastError" in body
        has_sync = "hipDeviceSynchronize" in body
        
        # Check if there is host allocation/copy logic (e.g. hipMalloc/hipMemcpy)
        has_host_allocation_or_copy = ("hipMalloc" in body or "hipHostMalloc" in body or "hipMemcpy" in body or "malloc" in body)
        
        # Update pointer contract tracking
        if pointer_names:
            stats["launcher_expects_device_pointers"] = "Yes"
            
        # 1. Prefix: Device pointer comment & null/size check guards
        prefix = ""
        if not has_existing_guards:
            comment_lines = []
            if not has_host_allocation_or_copy:
                if pointer_names:
                    ptrs_str = " and ".join(pointer_names)
                    comment_lines.append(f"    // {ptrs_str} are expected to be HIP device pointers.")
                else:
                    comment_lines.append("    // Expected to receive HIP device pointers.")
            
            guard_conds = []
            if size_name:
                guard_conds.append(f"{size_name} <= 0")
            for ptr in pointer_names:
                guard_conds.append(f"{ptr} == nullptr")
                
            if guard_conds:
                if comment_lines:
                    prefix += "\n" + "\n".join(comment_lines) + "\n"
                prefix += f"    if ({' || '.join(guard_conds)}) {{\n        return;\n    }}\n"
                stats["guards_inserted"] = True
                
        # 2. Suffix: hipGetLastError and hipDeviceSynchronize
        suffix = ""
        func_label = func_name.replace("run_", "").upper()
        
        if has_kernel_launch:
            if not has_error_check:
                suffix += f"\n    hipError_t launch_error = hipGetLastError();\n"
                suffix += f"    if (launch_error != hipSuccess) {{\n"
                suffix += f'        printf("{func_label} kernel launch failed: %s\\n", hipGetErrorString(launch_error));\n'
                suffix += f"        return;\n"
                suffix += f"    }}\n"
                stats["kernel_launch_error_checks"] = "inserted"
            else:
                stats["kernel_launch_error_checks"] = "found"
                
            if not has_sync:
                if validation_enabled:
                    suffix += f"\n    hipError_t sync_error = hipDeviceSynchronize();\n"
                    suffix += f"    if (sync_error != hipSuccess) {{\n"
                    suffix += f'        printf("{func_label} kernel execution failed: %s\\n", hipGetErrorString(sync_error));\n'
                    suffix += f"    }}\n"
                    stats["synchronization_status"] = "inserted"
                else:
                    stats["synchronization_status"] = "skipped"
            else:
                stats["synchronization_status"] = "found"
                
        # Modify the function body
        new_body = body
        if prefix:
            new_body = prefix + "\n" + new_body.lstrip()
        if suffix:
            new_body = new_body.rstrip() + "\n" + suffix + "\n"
            
        # Replace the body in content
        new_content = new_content[:start_pos + 1] + new_body + new_content[end_pos:]
        
    # Ensure includes are present if we made changes or have launcher
    if has_launcher:
        if not re.search(r'#include\s+<hip/hip_runtime\.h>', new_content):
            new_content = "#include <hip/hip_runtime.h>\n" + new_content
        if (stats["kernel_launch_error_checks"] == "inserted" or stats["synchronization_status"] == "inserted") and not re.search(r'#include\s+<(cstdio|stdio\.h)>', new_content):
            new_content = "#include <cstdio>\n" + new_content
            
    return new_content, stats


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
            
    # 3b. Perform launcher safety checks post-processing
    launcher_stats = {
        "launcher_expects_device_pointers": "N/A",
        "kernel_launch_error_checks": "none",
        "synchronization_status": "none"
    }
    
    for file_path in generated_dir.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in (".hip", ".cpp"):
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                new_content, stats = harden_hip_content(content, validation_enabled=context.runtime_validation_enabled)
                if new_content != content:
                    file_path.write_text(new_content, encoding="utf-8")
                    logger.info(f"[Validation] Hardened HIP launcher functions in {file_path}")
                # Aggregate stats
                if stats["launcher_expects_device_pointers"] == "Yes":
                    launcher_stats["launcher_expects_device_pointers"] = "Yes"
                if stats["kernel_launch_error_checks"] == "inserted" or (stats["kernel_launch_error_checks"] == "found" and launcher_stats["kernel_launch_error_checks"] != "inserted"):
                    launcher_stats["kernel_launch_error_checks"] = stats["kernel_launch_error_checks"]
                if stats["synchronization_status"] == "inserted" or (stats["synchronization_status"] in ("found", "skipped") and launcher_stats["synchronization_status"] != "inserted"):
                    launcher_stats["synchronization_status"] = stats["synchronization_status"]
            except Exception as e:
                logger.error(f"Failed to post-process launcher functions in {file_path}: {e}")
                
    # Update context with launcher safety metrics
    context.launcher_expects_device_pointers = "Yes" if launcher_stats["launcher_expects_device_pointers"] == "Yes" else "N/A"
    context.kernel_launch_error_checks = launcher_stats["kernel_launch_error_checks"]
    context.synchronization_status = launcher_stats["synchronization_status"]

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
        "replacements_made_during_validation": replacements_count,
        "launcher_expects_device_pointers": context.launcher_expects_device_pointers,
        "kernel_launch_error_checks": context.kernel_launch_error_checks,
        "synchronization_status": context.synchronization_status,
    }
    
    try:
        with open(validation_report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
        logger.info(f"[Validation] validation json report written to {validation_report_path}")
    except Exception as e:
        logger.error(f"Failed to write validation report json: {e}")
