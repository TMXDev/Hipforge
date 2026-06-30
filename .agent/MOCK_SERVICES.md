# .agent/MOCK_SERVICES.md

> **Pre-hackathon development guide.**
>
> The Fireworks AI API and ROCm compiler tools are unavailable during pre-hackathon development.
> This document defines exactly how to mock them so the system runs end-to-end without real APIs,
> and how to swap to real services in under 5 minutes when the hackathon begins.

---

## The Core Principle

Every external service must be injectable via environment variable.

```
USE_MOCK_AI=true        # Fireworks AI → MockFireworksClient
USE_MOCK_COMPILER=true  # hipify + hipcc → Mock runners
```

When real services are available:
```
USE_MOCK_AI=false
USE_MOCK_COMPILER=false
```

**No code changes required to swap. Only .env changes.**

---

## 1. Fireworks AI Mock

### When to use
Pre-hackathon phase. `USE_MOCK_AI=true` in `.env`.

### File to create
`backend/app/agents/mock_client.py`

### Behavior
The mock client must:
- Accept the same interface as the real client: `chat_completion(model, messages, max_tokens)`
- Return deterministic, realistic-looking responses for each agent type
- Log every call so you can see what would have been sent to the real API
- Introduce a small artificial delay (0.5–1 second) to simulate real latency

### Mock response strategy

```python
# analysis_agent mock response
MOCK_ANALYSIS_RESPONSE = {
    "analysis": "The error occurs because cudaMemcpyAsync is not fully equivalent to hipMemcpyAsync in this context.",
    "root_cause": "The stream parameter type differs between CUDA and HIP in versions prior to ROCm 5.3.",
    "suggested_fix": "Replace hipMemcpyAsync with hipMemcpyWithStream and pass the stream explicitly."
}

# patch_agent mock response — return a plausible corrected source file
MOCK_PATCH_RESPONSE = "/* HIPForge mock patch applied */\n" + "<original source with one obvious error removed>"

# research_agent mock response
MOCK_RESEARCH_RESPONSE = "According to the ROCm documentation, hipMemcpy stream synchronization requires explicit stream handles..."
```

### Factory pattern (required)

```python
# backend/app/agents/client_factory.py

import os

def get_ai_client():
    if os.getenv("USE_MOCK_AI", "true").lower() == "true":
        from backend.app.agents.mock_client import MockFireworksClient
        return MockFireworksClient()
    else:
        from backend.app.agents.fireworks_client import FireworksClient
        return FireworksClient(api_key=os.getenv("FIREWORKS_API_KEY"))
```

All agents must use `get_ai_client()` — never instantiate a client directly.

---

## 2. hipify-clang Mock

### When to use
Pre-hackathon phase. `USE_MOCK_COMPILER=true` in `.env`. Or when ROCm is not installed.

### File to create
`backend/app/compiler/mock_hipify_runner.py`

### Behavior
The mock must:
- Accept the same interface: `run_hipify(source_path, output_path)`
- Return the same schema: `{"success": bool, "output_path": str, "stdout": str, "stderr": str}`
- Write a plausible HIP file to `output_path` (copy the input, replace `cuda` with `hip` in strings)
- Always return `success=True` unless a special trigger comment is in the source file

### Failure trigger (for testing the repair loop)

Include a special comment in your CUDA test fixture to trigger mock compilation failure:

```cuda
// HIPFORGE_MOCK_COMPILE_ERROR
```

When the mock runner sees this comment, it returns `success=False` with a realistic error message, which triggers the AI repair loop during testing.

### Factory pattern (required)

```python
# backend/app/compiler/compiler_factory.py

import os

def get_hipify_runner():
    if os.getenv("USE_MOCK_COMPILER", "true").lower() == "true":
        from backend.app.compiler.mock_hipify_runner import MockHipifyRunner
        return MockHipifyRunner()
    else:
        from backend.app.compiler.hipify_runner import HipifyRunner
        return HipifyRunner()

def get_hipcc_runner():
    if os.getenv("USE_MOCK_COMPILER", "true").lower() == "true":
        from backend.app.compiler.mock_hipcc_runner import MockHipccRunner
        return MockHipccRunner()
    else:
        from backend.app.compiler.hipcc_runner import HipccRunner
        return HipccRunner()
```

---

## 3. hipcc Mock

### When to use
Pre-hackathon phase. `USE_MOCK_COMPILER=true` in `.env`.

### File to create
`backend/app/compiler/mock_hipcc_runner.py`

### Behavior
The mock must:
- Accept the same interface: `run_hipcc(source_path, output_path)`
- Return the same schema: `{"success": bool, "binary_path": str, "errors": list[CompilerError], "stdout": str}`
- Default: return `success=True` with empty errors list
- If the source file contains `// HIPFORGE_MOCK_COMPILE_ERROR`: return `success=False` with 1–3 realistic `CompilerError` objects

### Realistic mock errors (use these)

```python
MOCK_COMPILER_ERRORS = [
    {
        "file": "kernel.hip",
        "line": 42,
        "column": 8,
        "message": "error: no matching function for call to 'hipMemcpyAsync'",
        "code": "E0308"
    },
    {
        "file": "kernel.hip",
        "line": 67,
        "column": 12,
        "message": "error: use of undeclared identifier 'hipStreamNonBlocking'",
        "code": "E0020"
    }
]
```

---

## 4. CUDA Test Fixture File

Create this file at `tests/fixtures/sample.cu`:

```cuda
// Sample CUDA file for testing HIPForge
// Remove the line below to test successful compilation path
// HIPFORGE_MOCK_COMPILE_ERROR

#include <cuda_runtime.h>

__global__ void vectorAdd(float* a, float* b, float* c, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        c[i] = a[i] + b[i];
    }
}

int main() {
    int n = 1024;
    float *d_a, *d_b, *d_c;
    
    cudaMalloc(&d_a, n * sizeof(float));
    cudaMalloc(&d_b, n * sizeof(float));
    cudaMalloc(&d_c, n * sizeof(float));
    
    vectorAdd<<<(n+255)/256, 256>>>(d_a, d_b, d_c, n);
    
    cudaMemcpy(d_c, d_c, n * sizeof(float), cudaMemcpyDeviceToHost);
    
    cudaFree(d_a);
    cudaFree(d_b);
    cudaFree(d_c);
    
    return 0;
}
```

**With** `HIPFORGE_MOCK_COMPILE_ERROR`: triggers the AI repair loop (good for testing agents).
**Without** it: clean end-to-end run reaches COMPLETED instantly.

---

## 5. Hackathon Swap Checklist

When the hackathon starts and real services are available, do this in order:

```
[ ] 1. Get Fireworks AI API key
[ ] 2. Add FIREWORKS_API_KEY=<key> to .env
[ ] 3. Set USE_MOCK_AI=false in .env
[ ] 4. Test: run Session 9.1 prompt to verify real Fireworks client works
[ ] 5. If ROCm is available on the server:
       Set USE_MOCK_COMPILER=false in .env
       Run: hipify-clang --version && hipcc --version
       Test: run Session 8.1 gate manually
[ ] 6. Run the full E2E test (Session 14.1) against real services
[ ] 7. Update .agent/SESSION_STATE.json: set mode to "hackathon"
       Set ready_to_swap=true for each service
```

---

## 6. Rules for the AI Agent

When implementing any component that uses an external service:

1. **Always use the factory function** — never instantiate a client class directly.
2. **Mock first, real second** — implement the mock client before or alongside the real one.
3. **Same interface** — the mock must accept exactly the same parameters and return exactly the same schema as the real implementation.
4. **Log all mock calls** — `logger.debug(f"[MOCK] {service} called with: {params}")` so you can audit what the real API would have received.
5. **Never hardcode `USE_MOCK_AI=true`** — always read from environment.
