# 🚀 HIPForge: AI-Powered CUDA to ROCm Migration Platform

HIPForge is a self-healing, AI-orchestrated migration assistant built to automate the translation, compilation, and error-repair of NVIDIA CUDA GPU code to AMD HIP/ROCm code.

With a FastAPI backend, a Next.js frontend, a Redis queue/PubSub system, and specialized Fireworks AI agents, HIPForge automates the "last 30%" of migration debugging that standard compile-time translation tools (`hipify-clang`) leave behind.

---

## 🏗️ System Architecture

The following diagram illustrates the flow of jobs and communication channels within HIPForge:

```mermaid
graph TD
    User([User / Browser])
    subgraph Frontend [Next.js Web App]
        UI[Upload UI]
        WS[WebSocket Live Tracker]
    end
    subgraph Backend [FastAPI Backend]
        API[REST & WS Endpoints]
        WS_Relay[WS Event Relay]
    end
    subgraph Queue [Redis Queue & PubSub]
        PendingQueue[Pending Queue: hipforge:queue:pending]
        EventsChannel[Events Channel: migration:events:*]
    end
    subgraph Worker [Migration Worker]
        Engine[Workflow Engine]
        HIPIFY[1. hipify-clang subprocess]
        SCA[2. Semantic Compatibility Analyzer]
        COMPILING[3. hipcc compilation]
        AI_Loop[4. AI Self-Healing Loop]
    end
    subgraph AI [Fireworks AI API]
        AnalysisAgent[Analysis Agent]
        PatchAgent[Patch Agent]
        ResearchAgent[Research Agent]
    end

    User -->|1. Uploads .cu file| UI
    UI -->|2. POST /api/v1/migrate/upload| API
    API -->|3. Enqueues job & returns 202 Accepted| PendingQueue
    PendingQueue -->|4. BRPOP dequeues job| Engine
    Engine -->|5. Translate| HIPIFY
    Engine -->|6. Scan API compatibility| SCA
    Engine -->|7. Compile checks| COMPILING
    COMPILING -->|8. On failure: analyze, patch, & retry| AI_Loop
    AI_Loop <-->|9. Diagnoses, repairs, researches| AI
    Engine -->|10. Publish progress events| EventsChannel
    EventsChannel -->|11. PubSub listener| WS_Relay
    WS_Relay -->|12. Live Timeline & logs updates| WS
    WS -->|13. Renders live progress| User
```

---

## 🛠️ The 10 Job States

Every migration travels through exactly these states in order, broadcasting progress in real time:

$$\text{QUEUED} \rightarrow \text{PREPARING} \rightarrow \text{HIPIFY} \rightarrow \text{SCA} \rightarrow \text{COMPILING} \rightarrow \text{ANALYZING} \rightarrow \text{PATCHING} \rightarrow \text{RESEARCHING} \rightarrow \text{COMPILING (retry)} \rightarrow \text{GENERATING\_REPORT} \rightarrow \text{COMPLETED / FAILED}$$

*   **QUEUED**: Job is created and waiting in the Redis list.
*   **PREPARING**: Directory structure is generated under `workspace/YYYY/MM/migration_id/`.
*   **HIPIFY**: Running `hipify-clang` to deterministically translate CUDA calls to HIP.
*   **SCA**: Semantic Compatibility Analyzer scans for deep architectural differences.
*   **COMPILING**: `hipcc` compiles the source file. If successful, skips to report generation.
*   **ANALYZING**: Fireworks AI **Analysis Agent** diagnoses compiler error diagnostics.
*   **PATCHING**: Fireworks AI **Patch Agent** writes and applies source code repairs.
*   **RESEARCHING**: Fireworks AI **Research Agent** looks up ROCm documentation if budget is exhausted.
*   **GENERATING_REPORT**: Package creator produces Markdown/JSON reports, Git diffs, and output ZIP.
*   **COMPLETED / FAILED**: Terminal states. All outputs are cleaned up except reports & ZIP archives.

---

## ⚙️ Configuration & Environment

The application configuration is managed via a `.env` file at the project root.

### Core Variables
*   `REDIS_URL`: The Redis connection string (e.g., `redis://localhost:6379`).
*   `WORKSPACE_PATH`: Storage folder path (default: `workspace`).
*   `WORKSPACE_SIZE_LIMIT`: Max upload file size (default: `100MB`).
*   `DEFAULT_RETRY_BUDGET`: Max repair loops allowed (default: `5`).
*   `LOG_LEVEL`: Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
*   `NEXT_PUBLIC_BACKEND_URL`: public URL of the FastAPI backend.

### Real vs. Mock Mode (Pre-Hackathon Toggles)
*   `USE_MOCK_AI`: Set to `true` to run the AI Agents with a deterministic local simulation, or `false` to connect to the live Fireworks AI API.
*   `USE_MOCK_COMPILER`: Set to `true` to mock compiler subprocesses, or `false` to execute real `hipify-clang` / `hipcc` binaries locally.
*   `FIREWORKS_API_KEY`: Your Fireworks AI developer platform API key (required when `USE_MOCK_AI=false`).

---

## 🐳 Option A: Running with Docker Compose (Recommended)

Docker Compose starts all four core services (Backend, Frontend, Redis, and Worker) automatically.

### 1. Configure the Environment
Ensure your `.env` file contains correct settings. To run a fully real, connected system:
```env
USE_MOCK_AI=false
USE_MOCK_COMPILER=false
FIREWORKS_API_KEY=your_real_fireworks_api_key_here
```
*(If you are running in a host environment without ROCm/HIP SDK installed, keep `USE_MOCK_COMPILER=true`).*

### 2. Launch the Application
Run the following command at the repository root:
```bash
docker-compose up --build
```

Once all containers are running:
*   **Next.js Frontend**: Accessible at [http://localhost:3000](http://localhost:3000).
*   **FastAPI Backend Swagger Docs**: Accessible at [http://localhost:8000/docs](http://localhost:8000/docs).
*   **Redis Broker**: Accessible on port `6379`.

---

## 💻 Option B: Running Locally (Bare Metal)

If you prefer to run the services individually on your host machine for development or debugging, follow these steps:

### Prerequisites
*   Python 3.10+
*   Node.js 18+ (npm or yarn)
*   Redis server running locally on port `6379` (or custom port matching `.env`)

### 1. Setup & Start Redis
If you have Docker but want to run the app code bare-metal, start Redis via Compose:
```bash
docker-compose up -d redis
```

### 2. Start the Backend API Server
Navigate to the root directory, activate your Python virtual environment, and launch FastAPI:
```bash
# Set Python Path
$env:PYTHONPATH="backend"  # PowerShell (Windows)
export PYTHONPATH=backend  # Bash (Linux/macOS)

# Start FastAPI
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Start the Migration Worker
The worker runs as a standalone daemon checking for jobs in Redis. In a new terminal tab:
```bash
# Set Python Path
$env:PYTHONPATH="backend"  # PowerShell (Windows)
export PYTHONPATH=backend  # Bash (Linux/macOS)

# Launch Worker
.venv\Scripts\python -m app.workers.migration_worker
```

### 4. Start the Next.js Frontend
Navigate to the `frontend/` directory, install packages, and start the development server:
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 🧪 Running Tests

A comprehensive unit and integration test suite is located in the `tests/` directory.

> [!IMPORTANT]
> Always restrict `pytest` to the `tests/` directory to prevent it from collecting manual demo scripts like `scripts/test_demo.py` as test suites.

To execute the test suite:
```bash
# Ensure PYTHONPATH points to backend
$env:PYTHONPATH="backend"

# Run tests
.venv\Scripts\pytest tests/ -v
```

---

## ⚡ Mock-to-Real Swap Checklist (Hackathon Transition)

When swapping the system fully from mock stubs to real compilations and Fireworks AI endpoints:

1. Add your `FIREWORKS_API_KEY` to `.env`.
2. Toggle `USE_MOCK_AI=false` in `.env`.
3. If the host machine or container has ROCm installed, set `USE_MOCK_COMPILER=false` in `.env`.
4. Update the mode to `"hackathon"` in `.agent/SESSION_STATE.json` and set `"ready_to_swap": true` for all mocked services.
5. Re-run `pytest tests/ -v` to verify that everything still compiles and executes.
