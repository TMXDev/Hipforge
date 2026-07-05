# HIPForge Dependency Specification

This document details the dependencies, environment configurations, and setup procedures required to run, compile, and validate HIPForge.

---

## Quick Dependency Table

| Dependency | Required Version / Source | Required For | Notes |
| :--- | :--- | :--- | :--- |
| **Python** | `>=3.10` | All Modes | Powers the FastAPI backend, CLI doctor tools, and agent execution. |
| **Node.js** | `>=20` | Frontend UI | Builds and runs the Next.js React user interface. |
| **Redis** | `redis:7-alpine` | All Modes | Used for shared state management and real-time WebSocket communication. |
| **Docker & Compose**| Modern Engine / CLI | All Docker Modes | Orchestrates the multi-container stack and isolation sandbox. |
| **gVisor (`runsc`)**| Compatible runtime | Production Sandbox| Provides secure sandbox isolation. (Can fallback to default docker runtime). |
| **ROCm Toolchain** | `rocm/dev-ubuntu-22.04` | Real Compile Mode | Contains AMD HIP SDK tools like `hipcc` and `hipify-clang`. |
| **CUDA Toolkit** | `nvidia-cuda-toolkit` | Real Compile Mode | Essential for `hipify-clang` AST parsing compatibility. |
| **Fireworks AI API** | Developer Key | AI Repair (Real) | DeepSeek Flash model or similar, used to fix compilation errors. |

---

## Compiler and Validation Modes

### 1. Mock Demo Mode (Default / Offline)
* **Description**: Runs entirely on simulated compiler and AI interfaces. Ideal for evaluating the frontend, backend state machine, and basic workflow without local GPU hardware, Docker containers, or live API credentials.
* **Requirements**:
  * Python `>=3.10` and Node.js `>=20` on the host machine.
  * `.env` configured with:
    ```env
    USE_MOCK_COMPILER=true
    USE_MOCK_AI=true
    ```
  * No GPU hardware, Docker daemon, or ROCm SDK is required.

### 2. Compile-Validated Real Mode
* **Description**: Translates CUDA code to HIP and validates structural correctness by running the actual compilers (`hipify-clang` and `hipcc`) inside isolated sandbox Docker containers.
* **Requirements**:
  * Running Docker daemon.
  * Host Docker socket access (`/var/run/docker.sock` mounted).
  * The sandbox Docker image must be built locally:
    ```bash
    docker build -t hipforge-sandbox:latest -f Dockerfile.sandbox .
    ```
  * `.env` configured with:
    ```env
    USE_MOCK_COMPILER=false
    HIPFORGE_SANDBOX_IMAGE=hipforge-sandbox:latest
    ALLOW_RUNSC_FALLBACK=true # Set to false only if gVisor (runsc) is installed
    ```
  * **CUDA Toolkit Requirement**: Because `hipify-clang` relies on CUDA header AST parsing, `nvidia-cuda-toolkit` must be present inside the sandbox image to provide `cuda_runtime.h` and `libdevice.bc` files. (This is pre-configured in `Dockerfile.sandbox`).

### 3. AMD GPU Runtime Validation (Future / Optional)
* **Description**: Validates translated HIP binaries by running them directly on an AMD GPU.
* **Requirements**:
  * Host system containing a supported AMD GPU (e.g. CDNA/RDNA family).
  * ROCm kernel drivers active on the host.
  * Docker containers launched with GPU access flags (e.g. `--device=/dev/kfd --device=/dev/dri` and suitable capabilities).
  * **Status**: **Disabled by default in `v0`.** `v0` supports compile-validated migration out of the box; runtime GPU execution is a future capability.

### 4. Profiling (`rocprof`)
* **Description**: Gathers performance metrics of translated HIP code.
* **Requirements**:
  * Active AMD GPU runtime environment.
  * ROCm profiling tools (`rocprof` / `rocprofv2` or `rocprofiler`) installed inside the sandbox/container.
  * **Status**: **Optional / future feature.**

---

## Environment Variables Configuration

Configure these in a `.env` file at the project root.

| Environment Variable | Default Value | Description |
| :--- | :--- | :--- |
| `REDIS_URL` | `redis://localhost:4444?protocol=2` | Connection URL for Redis. |
| `WORKSPACE_PATH` | `workspace` | Directory for storing input and generated files in the container. |
| `WORKSPACE_SIZE_LIMIT` | `100MB` | Maximum size limit for uploaded source workspaces. |
| `DEFAULT_RETRY_BUDGET` | `5` | Compilation repair attempt budget before marking a migration as failed. |
| `LOG_LEVEL` | `INFO` | Console logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `NEXT_PUBLIC_BACKEND_URL`| `http://localhost:8000` | Frontend backend API endpoint. |
| `FIREWORKS_API_KEY` | `CHANGE_ME` | API Key for accessing Fireworks AI models. |
| `FIREWORKS_MODEL` | `accounts/fireworks/models/deepseek-v4-flash` | Selected AI LLM model. |
| `USE_MOCK_AI` | `false` | Set to `true` to use mock offline AI clients. |
| `USE_MOCK_COMPILER` | `false` | Set to `true` to use mock compiler/sandbox execution. |
| `HIPFORGE_SANDBOX_IMAGE` | `hipforge-sandbox:latest` | Target Docker image name used for sandboxed compilation. |
| `HIP_VISIBLE_DEVICES` | `0` | Exposed AMD GPU device ID. |
| `HOST_WORKSPACE_PATH` | *Current folder path* | Host workspace absolute path mapping for nested container mounting. |
| `DISABLE_COMPILER_CACHE` | `true` | Set to `false` to enable compilation caching. |
| `ALLOW_RUNSC_FALLBACK` | `true` | Allow Docker default runtime if gVisor `runsc` is not present. |
| `REQUIRE_HOST_HIPIFY` | `false` | Require host-level `hipify-clang` instead of sandbox fallback. |

---

## Sandbox and Docker Sanity Commands

Use these commands to verify, debug, and monitor the HIPForge Docker environment:

### 1. Docker Compose Sanity
Verify compose syntax and environment variable interpolation:
```bash
docker compose config
```

### 2. Build and Start Services
Rebuild application images and spin up the backend, frontend, and Redis services:
```bash
docker compose up --build -d
```

### 3. Preflight Diagnostics
Run the preflight health checker tool to inspect Docker, sandbox images, and environment variables:
```bash
python cli/hipforge.py doctor
```
For verbose output showing individual check statuses:
```bash
python cli/hipforge.py doctor --verbose
```

### 4. Run Mock-Mode Tests
Execute the test suite in mock mode (no compiler required):
```bash
$env:PYTHONPATH="backend;."
python -m pytest
```

### 5. Run Real Compiler E2E Tests
Execute E2E validation against the real compiler sandbox (requires active Docker and `hipforge-sandbox:latest` image):
```bash
python -m pytest -m e2e_real -s -vv
```

---

## Known Limitations

1. **Windows Platform Support**: Host-level compilation is not supported on Windows. The compiler tools (`hipcc` and `hipify-clang`) must be executed via sandboxed Docker containers on Windows hosts.
2. **CUDA Headers Dependency**: Even though target binaries run on AMD hardware, the parser tool (`hipify-clang`) requires standard CUDA headers (`cuda_runtime.h`) and `libdevice` files to compile-check and validate source code AST. These are installed in the container environment rather than the host system.
3. **gVisor Availability**: gVisor is not natively supported on Docker Desktop for Windows/macOS. Setting `ALLOW_RUNSC_FALLBACK=true` allows tests to fallback to standard container runtime on these environments.
