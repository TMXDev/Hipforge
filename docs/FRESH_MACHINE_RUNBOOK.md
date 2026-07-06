# FRESH MACHINE RUNBOOK

This guide provides step-by-step instructions to clone, build, deploy, and verify the HIPForge platform from scratch.

---

## 1. Prerequisites

Before starting, ensure your host system has the following tools installed and running:
* **Docker Desktop** (Windows 10/11 or macOS) or **Docker Engine** (Linux).
* **Docker Compose v2** (integrated inside Docker Desktop; on Linux, install `docker-compose-plugin`).
* **Git** (to clone the codebase).
* **Optional**: Python 3.10+ and Node.js 18+ (only required if running services bare-metal on the host rather than Docker).

> [!IMPORTANT]
> **Docker Daemon Requirement:**
> This setup assumes the Docker daemon is already installed and active. Restricted cloud shells or environments that do not support Docker or containerized nesting are not supported.
>
> **Git CA Certificate Errors:**
> If you encounter Git SSL certificate errors while cloning (e.g. `SSL certificate problem: self signed certificate`), this is a host-level environment configuration issue. You can bypass it for cloning via:
> `git config --global http.sslVerify false`

---

## 2. Clone the Repository

Clone the project repository. Note that Linux filesystems are case-sensitive; use the actual folder name `Hipforge` during operations.

```bash
git clone https://github.com/TMXDev/Hipforge.git
cd Hipforge
```

---

## 3. Environment Configuration

Create the local configuration file:

### On Linux or macOS (Bash):
```bash
cp .env.example .env
```

### On Windows (PowerShell):
```powershell
Copy-Item .env.example .env
```

Open `.env` in a text editor and customize the parameters:

- **Mock Mode (Recommended for offline demos)**:
  ```env
  USE_MOCK_COMPILER=true
  USE_MOCK_AI=true
  FIREWORKS_API_KEY=CHANGE_ME
  RUNTIME_VALIDATION_ENABLED=false
  ```
- **Real Mode (For compilation validation and live LLM repairs)**:
  ```env
  USE_MOCK_COMPILER=false
  USE_MOCK_AI=false
  FIREWORKS_API_KEY=your_actual_fireworks_api_key
  RUNTIME_VALIDATION_ENABLED=false
  ```

---

## 4. Docker Startup

Start the complete application stack. This pulls base images (`rocm/dev-ubuntu-22.04`, `node:20-alpine`, `redis:7-alpine`), builds containers, and boots all services:

```bash
docker compose up --build -d
```

Verify that all 4 containers are running and healthy:

```bash
docker compose ps
```

### Deployed Services:
* `hipforge-redis` (internal queue / state caching)
* `hipforge-backend` (REST API & WS endpoints on port `8000`)
* `hipforge-migration-worker` (background workflow execution daemon)
* `hipforge-frontend` (Next.js dashboard UI on port `3000`)

---

## 5. Health Checks

Verify backend reachability:

### Via curl (Bash):
```bash
curl http://localhost:8000/api/v1/health/check
```

### Via PowerShell:
```powershell
Invoke-WebRequest http://localhost:8000/api/v1/health/check
```

*Expected JSON Output*: `{"status":"ok","redis":"connected","version":"0.1.0"}`

---

## 6. Run a First Migration

### A. Web UI Flow
1. Open your web browser to [http://localhost:3000](http://localhost:3000).
2. Go to the **Upload** page.
3. Paste a CUDA `.cu` code snippet or upload a `.cu` file.
4. Select the target architecture (e.g., `gfx942`).
5. Click **Start Migration**.
6. The browser redirects to `/migration/<job-id>`. Watch the timeline track progress in real-time.
7. Click **Download Results** to retrieve the structured zip archive containing generated HIP code and validation reports.

### B. CLI Flow
Submit migrations directly from the terminal without leaving the compose stack:

```bash
# Verify environment diagnostics
docker compose exec backend python cli/hipforge.py doctor

# Submit a validation job
docker compose exec backend python cli/hipforge.py migrate workspace/input/kernel.cu --output workspace/demo_out --arch gfx942 --attempts 0
```

---

## 7. Sandbox Compilation Validation (Real Compiler Mode)

To validate compilation against real ROCm compiler tools (`USE_MOCK_COMPILER=false`), ensure the sandbox image is compiled locally:

```bash
docker build -t hipforge-sandbox:latest -f Dockerfile.sandbox .
```

Verify the Sandbox compilers:
```bash
docker run --rm hipforge-sandbox:latest hipify-clang --version
docker run --rm hipforge-sandbox:latest hipcc --version
```

---

## 8. Run Tests

### Unit Tests (Offline / Mock Mode)
Run unit tests on the host (requires Python 3.10+):
```bash
# Windows PowerShell
$env:PYTHONPATH="backend;."
python -m pytest tests/ -q

# Linux/macOS
PYTHONPATH="backend:." python -m pytest tests/ -q
```

### E2E Tests (Requires running Docker stack)
Verify container API routing:
```bash
# Windows PowerShell
$env:PYTHONPATH="backend;."
python -m pytest -m e2e_real -s -vv

# Linux/macOS
PYTHONPATH="backend:." python -m pytest -m e2e_real -s -vv
```

---

## 9. Troubleshooting

* **Backend Unreachable**: View container console output:
  `docker compose logs backend`
* **Queue Tasks Not Processing**: Inspect background worker traces:
  `docker compose logs migration-worker`
* **Project Upload Rejected**: If the dashboard rejects uploads with `PROJECT_TOO_LARGE`, check the limits in `.env` (max 20 `.cu` files, max 50 MB extraction). Extract large project directories and upload a single sub-folder at a time.
* **AI Repair Skipped**: If `USE_MOCK_AI=false` and no Fireworks key is provided, the worker skips self-healing on compilation errors and goes straight to report generation. Ensure a valid Fireworks API key is set in `.env`.

---

## 10. Shutdown

Stop all containers and preserve volumes:
```bash
docker compose down
```

Wipe all database volumes and workspace directories to start fresh:
```bash
docker compose down --volumes
```
