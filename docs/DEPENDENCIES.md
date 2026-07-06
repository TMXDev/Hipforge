# HIPForge Dependency Specification

This document details the dependencies, environment configurations, and setup procedures required to run, compile, and validate HIPForge.

---

## 1. Quick Dependency Table

| Dependency | Scope | Required For | Provided By |
| :--- | :--- | :--- | :--- |
| **Docker Desktop / Engine** | System | Container orchestration and isolated compilation sandbox. | User (Host System) |
| **Docker Compose v2** | System | Building and launching multi-container stacks. | User (Host System) |
| **Git** | Development | Cloning repositories. | User (Host System) |
| **Fireworks AI API Key** | Integration | Dynamic AI self-healing agent queries (Real AI mode only). | User (Credentials) |
| **Python 3.10+** | Host (Optional) | Running CLI scripts or backend tests locally on the host machine. | User (Host System) / Docker internally |
| **Node.js 18+ & npm** | Host (Optional) | Running frontend UI development server locally on the host. | User (Host System) / Docker internally |
| **ROCm Toolchain** | Sandbox | Translating and compiling code (`hipcc`, `hipify-clang`). | Sandbox image (`Dockerfile.sandbox`) |
| **CUDA Toolkit** | Sandbox | AST parser compatibility (`cuda_runtime.h`). | Sandbox image (`Dockerfile.sandbox`) |
| **Redis 7** | Infrastructure | Shared state caching and queue broker. | Redis container (`redis:7-alpine`) |

> [!NOTE]
> **No Host installation required**: You do **NOT** need to manually install Python, Node.js, Redis, ROCm, or CUDA tools on your host machine to run HIPForge. The standard `docker compose up` stack packages all backend, worker, frontend, compiler, and Redis environments internally.

---

## 2. Compiler Sandbox Configuration

To perform compile-validation without faking outputs (`USE_MOCK_COMPILER=false`), you must build the sandbox Docker image on the host:

```bash
docker build -t hipforge-sandbox:latest -f Dockerfile.sandbox .
```

Verify that the tools are available within the image:

```bash
docker run --rm hipforge-sandbox:latest hipify-clang --version
docker run --rm hipforge-sandbox:latest hipcc --version
```

If these tools execute successfully, the migration worker will be able to perform compile validation.

---

## 3. Environment Variables reference

Define these variables in your local `.env` file:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `REDIS_URL` | `redis://redis:6379` | Redis connection endpoint inside compose network. |
| `USE_MOCK_COMPILER` | `true` | Set to `false` to invoke sandbox compile-validation. |
| `USE_MOCK_AI` | `true` | Set to `false` to use live Fireworks AI agents. |
| `FIREWORKS_API_KEY` | `CHANGE_ME` | API Key used when `USE_MOCK_AI=false`. |
| `RUNTIME_VALIDATION_ENABLED` | `false` | Disabled by default in v0. Set to `false`. |
| `TIMEOUT_COMPILE` | `60` | Compile execution timeout in seconds. |
| `MAX_CUDA_FILES_FOR_AUTO_MIGRATION` | `20` | Preflight upload limit for CUDA source files. |
| `MAX_TOTAL_FILES_FOR_AUTO_MIGRATION`| `1000` | Preflight upload limit for total workspace files. |
