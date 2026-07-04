import re
from typing import List
from app.models.compiler_error import CompilerError

# Regular expression to extract compiler diagnostics matching Clang/GCC formats:
# Example: kernel.hip:42:8: error: no matching function for call to 'hipMemcpyAsync' [E0308]
DIAGNOSTIC_PATTERN = re.compile(
    r"^(?P<file>(?:[a-zA-Z]:)?[^:\n]+):(?P<line>\d+):(?P<column>\d+):\s+(?:fatal\s+)?error:\s+(?P<message>.*?)(?:\s+\[(?P<code>[^\]\n]+)\])?$"
)

def parse_compiler_errors(stderr: str) -> List[CompilerError]:
    """
    Parses stderr output from a compiler and extracts structured CompilerError models.
    Matches lines formatted like 'file:line:col: error: msg [code]'.
    """
    errors = []
    if not stderr:
        return errors
        
    for line in stderr.splitlines():
        line = line.strip()
        match = DIAGNOSTIC_PATTERN.match(line)
        if match:
            gd = match.groupdict()
            # If no code is explicitly matched in brackets, default to empty string
            code = gd.get("code") or ""
            errors.append(CompilerError(
                file=gd["file"],
                line=int(gd["line"]),
                column=int(gd["column"]),
                message=gd["message"],
                code=code
            ))
            
    return errors


def classify_compiler_error(stderr: str) -> str:
    """
    Classifies any compiler or migration failure into exactly one public category:
    ENVIRONMENT_ERROR, CONFIGURATION_ERROR, DEPENDENCY_ERROR, TOOLCHAIN_ERROR,
    COMPILATION_ERROR, MIGRATION_ERROR, AI_ERROR, NETWORK_ERROR,
    USER_CODE_ERROR, or UNSUPPORTED_FEATURE.
    """
    if not stderr:
        return "USER_CODE_ERROR"
        
    stderr_lower = stderr.lower()
    
    # NETWORK_ERROR
    if (
        "connection timed out" in stderr_lower
        or "connection refused" in stderr_lower
        or "temporary failure in name resolution" in stderr_lower
        or "network is unreachable" in stderr_lower
        or "read timed out" in stderr_lower
        or "timeout" in stderr_lower and ("fireworks" in stderr_lower or "http" in stderr_lower)
    ):
        return "NETWORK_ERROR"

    # AI_ERROR / CONFIGURATION_ERROR
    if "fireworks" in stderr_lower or "api key" in stderr_lower or "model" in stderr_lower:
        if (
            "api key" in stderr_lower
            or "unauthorized" in stderr_lower
            or "http 401" in stderr_lower
            or "forbidden" in stderr_lower
            or "http 403" in stderr_lower
        ):
            return "CONFIGURATION_ERROR"
        return "AI_ERROR"

    # ENVIRONMENT_ERROR
    if (
        "docker sandbox error" in stderr_lower
        or "unknown or invalid runtime" in stderr_lower
        or "runsc" in stderr_lower
        or "sandbox timeout" in stderr_lower
        or ("timeout" in stderr_lower and "sandbox" in stderr_lower)
        or "docker daemon" in stderr_lower
        or "cannot connect to the docker daemon" in stderr_lower
    ):
        return "ENVIRONMENT_ERROR"

    if (
        "permission denied" in stderr_lower
        or "permission" in stderr_lower
        or "no space left on device" in stderr_lower
        or "disk quota exceeded" in stderr_lower
        or "read-only file system" in stderr_lower
    ):
        return "ENVIRONMENT_ERROR"
        
    # TOOLCHAIN_ERROR
    if (
        "hipcc: command not found" in stderr_lower
        or "hipcc: not found" in stderr_lower
        or "hipify-clang: command not found" in stderr_lower
        or "hipify-clang: not found" in stderr_lower
        or "command not found" in stderr_lower
        or "hipcc not found" in stderr_lower
        or "hipify-clang not found" in stderr_lower
        or "cmake: command not found" in stderr_lower
        or "ninja: command not found" in stderr_lower
    ):
        return "TOOLCHAIN_ERROR"

    # DEPENDENCY_ERROR
    if (
        "cannot find -l" in stderr_lower
        or "cannot find library" in stderr_lower
        or "ld: error:" in stderr_lower
        or "cannot find" in stderr_lower and ("library" in stderr_lower or "-l" in stderr_lower)
    ):
        return "DEPENDENCY_ERROR"
    if (
        "hip_runtime.h: no such file" in stderr_lower
        or "hip/hip_runtime.h: no such file" in stderr_lower
        or ("hip_runtime.h" in stderr_lower and "no such file" in stderr_lower)
        or ("hip/hip_runtime.h" in stderr_lower and "no such file" in stderr_lower)
        or ("cuda_runtime.h" in stderr_lower and "no such file" in stderr_lower)
        or "libdevice" in stderr_lower
    ):
        return "DEPENDENCY_ERROR"
    if re.search(r"\brocm\b.*(installation|toolchain|sdk|runtime).*(not found|missing)", stderr_lower):
        return "TOOLCHAIN_ERROR"

    # UNSUPPORTED_FEATURE
    if (
        "unsupported" in stderr_lower
        or "not supported" in stderr_lower
        or "inline ptx" in stderr_lower
        or "wmma" in stderr_lower
        or "tensor core" in stderr_lower
        or "texture reference" in stderr_lower
    ):
        return "UNSUPPORTED_FEATURE"

    # MIGRATION_ERROR
    if (
        "internal system error" in stderr_lower
        or "traceback (most recent call last)" in stderr_lower
        or "python" in stderr_lower
        or "infinite loop prevented" in stderr_lower
        or "patch agent returned unchanged" in stderr_lower
        or "state execution failed" in stderr_lower
    ):
        return "MIGRATION_ERROR"
        
    if "compilation failed" in stderr_lower and "error:" not in stderr_lower:
        return "COMPILATION_ERROR"

    # NEW: unsupported HIP gpu architecture - environment/toolchain error, not user code
    if re.search(r'unsupported hip gpu architecture(?:\s*:|:)\s*(\S+)', stderr_lower) or re.search(r'gfx\d{2,4}[a-z]?\b', stderr_lower):
        return "UNSUPPORTED_FEATURE"
        
    # NEW: unresolved symbol - linker error, needs user intervention for single files
    if "undefined symbol" in stderr_lower or "undefined reference" in stderr_lower:
        return "UNRESOLVED_SYMBOL"

    # Default to user code errors. Only this category triggers AI repair.
    return "USER_CODE_ERROR"
