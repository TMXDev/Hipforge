# FRESH MACHINE RUNBOOK

This guide provides step-by-step instructions for a judge or fresh-clone developer to build, deploy, and verify the HIPForge platform from scratch.

---

## 1. Prerequisites

Before starting, ensure your machine has the following tools installed:

### Host Operating System Requirements
* **Windows 10/11** with **Docker Desktop** installed and running (WSL 2 backend recommended).
* **Linux** (Ubuntu 20.04+ or similar) with **Docker Engine** and **Docker Compose** installed.
* **Git** (to clone the repository).
* **Optional**: Python 3.10+ (only if running the migration CLI or test suites locally on the host).
* **Optional**: Node.js 18+ and npm (only if running the frontend locally on the host).

### Infrastructure Keys & Compute
* **Fireworks AI API Key** (optional, only required for AI self-healing repair). If not provided, you can run in mock AI mode.
* **AMD GPU Hardware**: Optional. Physical AMD GPU hardware is **not required** to run compile-validation or workflow demos.
* **ROCm/HIP Compiler Validation Requirements**: Requires `hipify-clang` and `hipcc`. In dockerized setups, these are pre-installed in the provided docker sandbox.

---

## 2. Clone the Repository

Clone the project repository and navigate to the project root:

```bash
git clone <PUBLIC_REPO_URL>
cd HIPForge
```
*(Replace `<PUBLIC_REPO_URL>` with the final repository URL).*

---

## 3. Environment Setup

Create your environment configuration file:

### On Bash (Linux/macOS/Git Bash):
```bash
cp .env.example .env
```

### On PowerShell (Windows):
```powershell
Copy-Item .env.example .env
```

Open `.env` in a text editor and configure the keys:

* `FIREWORKS_API_KEY`: Set your Fireworks AI key (replace `CHANGE_ME`).
* `USE_MOCK_AI`: Set to `true` to demo without query costs or Fireworks API keys. Set to `false` for live agent diagnostics.
* `USE_MOCK_COMPILER`: Set to `true` to run workflow-only demos on machines lacking ROCm packages. Set to `false` for real compiler validation.
* `RUNTIME_VALIDATION_ENABLED`: Leave `false` (default) as v0 focuses on compilation validation.
* `REDIS_URL`: Defaults to `redis://redis:6379` inside container networks.
* `NEXT_PUBLIC_BACKEND_URL`: Defaults to `http://localhost:8000`.
* **Upload and Engine Limits**:
  * `MAX_CUDA_FILES_FOR_AUTO_MIGRATION`: Max CUDA files permitted (default: `20`).
  * `MAX_TOTAL_FILES_FOR_AUTO_MIGRATION`: Max total files permitted (default: `1000`).
  * `MAX_EXTRACTED_BYTES_FOR_AUTO_MIGRATION`: Max ZIP extraction limit (default: `52428800` bytes / 50MB).
  * `TIMEOUT_COMPILE`: Compile execution timeout in seconds (default: `60`).

> [!IMPORTANT]
> **Real Compiler Mode Requirements:**
> Setting `USE_MOCK_COMPILER=false` requires `hipify-clang` and `hipcc` to be installed and accessible. In Docker Compose setups, the `migration-worker` container uses the sandboxed Docker image `hipforge-sandbox:latest` which is pre-built with ROCm tools. If this sandbox image is missing, compilation validation will fail.

---

## 4. Docker Startup: Main Judge Path

Deploy the complete container stack. This builds and spins up all backend, worker, frontend, and Redis services in **under 60 seconds** (no packages are downloaded at runtime):

```bash
docker compose up --build -d
```

Verify that all 4 containers are running and healthy:

```bash
docker compose ps
```

### Expected Containers:
* `hipforge-redis`: Port `6379` (internal).
* `hipforge-backend`: Port `8000`.
* `hipforge-migration-worker`: Internal daemon.
* `hipforge-frontend`: Port `3000`.

---

## 5. Health Checks

Confirm that the application services are fully reachable:

### Via curl (Bash):
```bash
curl http://localhost:8000/api/v1/health/check
```

### Via PowerShell:
```powershell
Invoke-WebRequest http://localhost:8000/api/v1/health/check
```

*Expected JSON Response*: `{"status":"ok","redis":"connected","version":"0.1.0"}`

### Browser Access:
* **Web UI Dashboard**: Access [http://localhost:3000](http://localhost:3000)
* **Interactive API Documentation (Swagger)**: Access [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 6. Run a First Migration from the Web UI

To test the end-to-end migration pipeline visually:

1. Open your web browser to [http://localhost:3000](http://localhost:3000).
2. Go to the **Upload** page.
3. Paste a small CUDA sample in the text area, or upload a CUDA `.cu` file.
4. Select the target architecture (e.g. `gfx942`).
5. Click **Start Migration**.
6. The app redirects to `/migration/<job-id>`. Watch the live WebSocket timeline trace the stages: `PREFLIGHT`, `HIPIFY`, `COMPILING` (and `ANALYZING`/`PATCHING` if errors occur).
7. Inspect the final output code and download the zipped report package.

---

## 7. Run a First Migration from CLI

You can execute migrations from the command line using one of two methods:

### Option A: Running Inside the Backend Container (Preferred)
No Python environment needs to be configured on your host machine:

```bash
# Verify environment diagnostics
docker compose exec backend python cli/hipforge.py doctor

# Submit a migration job
docker compose exec backend python cli/hipforge.py migrate workspace/input/kernel.cu --output workspace/demo_out --arch gfx942 --attempts 0
```

### Option B: Running on the Host Machine
Only use this if you have Python 3.10+ installed on your host:

```powershell
python -m venv .venv
# PowerShell activation:
.\.venv\Scripts\Activate.ps1
# Bash activation: source .venv/bin/activate

# Install requirements
pip install -r backend/requirements.txt

# Run doctor and migration commands
python cli/hipforge.py doctor
python cli/hipforge.py migrate workspace/input/kernel.cu --output workspace/demo_out --arch gfx942 --attempts 0
```

---

## 8. VectorAdd Sample vs. Nvidia Cuda-samples Monorepo

> [!WARNING]
> **Oversized Repository Guard:**
> Do **NOT** upload the entire Nvidia `cuda-samples` monorepo ZIP. The v0 engine enforces limits to guarantee fast feedback.
> * Archives exceeding `100MB` or extractions exceeding `50MB` will trigger the preflight size guard.
> * Layouts containing more than `20` CUDA files or multiple independent projects will abort immediately with `PROJECT_TOO_LARGE` to prevent long hangs.
>
> **Recommended Sample Path**: Zip and upload a single sample directory, such as `Samples/0_Introduction/vectorAdd` or a single `.cu` file.

---

## 9. Real No-Mock Compiler Validation

To prove compile validation against AMD's toolchain, ensure `USE_MOCK_COMPILER=false` in `.env`.

Verify that the compilers are successfully installed and active:

### Within the Sandboxed Docker Image:
```bash
docker run --rm hipforge-sandbox:latest hipify-clang --version
docker run --rm hipforge-sandbox:latest hipcc --version
```

If these commands return toolchain versions, real compilation validation is ready. If they fail with command-not-found, the environment is in workflow-mock mode.

---

## 10. Build Sandbox Image (If Required)

If `hipforge-sandbox:latest` was not downloaded or needs to be compiled locally:

```bash
docker build -t hipforge-sandbox:latest -f Dockerfile.sandbox .
```

Verify the local build:
```bash
docker run --rm hipforge-sandbox:latest hipcc --version
```

---

## 11. Run Real E2E Tests

If you have local Python dependencies configured, run the E2E verification test suite. Ensure the Docker containers are running first:

```bash
$env:PYTHONPATH="backend;."
python -m pytest -m e2e_real -s -vv
```

*Note: E2E tests check actual backend container connectivity. If the backend is offline, tests will skip.*

---

## 12. Troubleshooting

* **Docker Daemon Not Running**: Start Docker Desktop and verify the status bar turns green.
* **`docker down` Unknown**: Always run the compose subcommand: `docker compose down`.
* **Backend Unreachable on `localhost:8000`**: Inspect backend health and startup logs:
  ```bash
  docker compose logs backend
  ```
* **Worker Offline/Died**: Check background workflow logs:
  ```bash
  docker compose logs migration-worker
  ```
* **Redis Connection Error**: Ensure Redis is running and listening:
  ```bash
  docker compose logs redis
  ```
* **Upload Aborted**: If the preflight returns `PROJECT_TOO_LARGE`, extract the project locally and upload only a single sample directory containing `.cu` files.
* **E2E Tests Skipped**: Verify the backend is up and running (`curl http://localhost:8000/api/v1/health/check`).
* **Fireworks API Key Missing**: The worker will skip AI self-healing and complete report generation immediately after first compilation failure. Set `USE_MOCK_AI=true` to demonstrate self-healing paths without keys.

---

## 13. Shutdown and Clean Restart

To stop all services:
```bash
docker compose down
```

To wipe the workspace and database volumes, and force-rebuild the containers:
```bash
docker compose down --volumes
docker compose up --build -d
```
