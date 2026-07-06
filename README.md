# 🚀 HIPForge: AI-Orchestrated CUDA to AMD HIP Migration

HIPForge is a self-healing, AI-orchestrated migration platform designed to automate the translation, compilation, and error-repair of NVIDIA CUDA GPU code to AMD HIP/ROCm code.

By combining deterministic tools (`hipify-clang`, `hipcc`) with specialized Fireworks AI agents (Analysis, Patch, and Research), HIPForge automates the "last 30%" of migration debugging that standard compile-time translation tools leave behind.

> [!IMPORTANT]
> **Getting Started Quick Links:**
> * 📖 **[FRESH MACHINE RUNBOOK (docs/FRESH_MACHINE_RUNBOOK.md)](file:///C:/Users/Yassi/Downloads/HIPForge/docs/FRESH_MACHINE_RUNBOOK.md)**: Zero-configuration copy-pasteable judge guide from Git clone to health checks and E2E validation.
> * ⚙️ **[Demo Guide (README_DEMO.md)](file:///C:/Users/Yassi/Downloads/HIPForge/README_DEMO.md)**: UI/CLI workflow walkthrough, validation details, and size thresholds.
> * 📦 **[Platform Dependencies (docs/DEPENDENCIES.md)](file:///C:/Users/Yassi/Downloads/HIPForge/docs/DEPENDENCIES.md)**: Real ROCm installation specifications and sandbox info.

---

## ⚡ 5-Line Quick Start

Deploy the complete container stack (Redis, Backend API, worker, and Web UI) in under 60 seconds:

```bash
git clone https://github.com/TMXDev/Hipforge.git
cd HIPForge
cp .env.example .env             # (PowerShell: Copy-Item .env.example .env)
docker compose up --build -d
docker compose ps
```
* **Web UI**: Access at [http://localhost:3000](http://localhost:3000)
* **Backend Docs (Swagger)**: Access at [http://localhost:8000/docs](http://localhost:8000/docs)
* **Health Check**: `curl http://localhost:8000/api/v1/health/check`

---

## 🏗️ System Architecture

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
        PendingQueue[Pending Queue]
        EventsChannel[Events Channel]
    end
    subgraph Worker [Migration Worker]
        Engine[Workflow Engine]
        HIPIFY[1. hipify-clang]
        SCA[2. Semantic Analyzer]
        COMPILING[3. hipcc compilation]
        AI_Loop[4. AI Self-Healing Loop]
    end
    subgraph AI [Fireworks AI API (on AMD Instinct)]
        AnalysisAgent[Analysis Agent]
        PatchAgent[Patch Agent]
        ResearchAgent[Research Agent]
    end

    User -->|Uploads .cu file| UI
    UI -->|POST /api/v1/migrate/upload| API
    API -->|Enqueues job| PendingQueue
    PendingQueue -->|BRPOP dequeues| Engine
    Engine -->|Translate| HIPIFY
    Engine -->|Scan compatibility| SCA
    Engine -->|Compile checks| COMPILING
    COMPILING -->|On failure: self-heal| AI_Loop
    AI_Loop <-->|Diagnose & repair| AI
    Engine -->|Publish progress| EventsChannel
    EventsChannel -->|WS event listener| WS_Relay
    WS_Relay -->|Live timeline updates| WS
    WS -->|Render progress| User
```

---

## ⚡ AMD Compute & ROCm Proof

HIPForge demonstrates native AMD compute integration through a dual-path pipeline:

### 1. Fireworks AI on AMD Instinct Infrastructure
* **Agentic Workflows**: All analysis, repair, and research agent queries run via the **Fireworks AI Inference Platform**.
* **AMD Partnership**: Fireworks AI runs its model endpoints on high-performance **AMD Instinct™ GPU infrastructure** (such as MI300X accelerators), providing direct, AMD-accelerated LLM inference.

### 2. ROCm / HIP Target Compilation
* **Target Architectures**: HIPForge automates targeting AMD CDNA/RDNA architectures. Supported and tested target offload architectures include `gfx90a` (MI210/MI250), `gfx941`, and `gfx942` (MI300 series).
* **Compiler Logs & Commands**: Compilation reports record the exact compiler commands executed in the sandboxed build, showing target parameters such as:
  ```bash
  hipcc --offload-arch=gfx942 -c main.hip -o main.o
  ```

---

## 📋 Track 3 Submission Checklist

- [x] **GitHub Repository**: Repository is public ([https://github.com/TMXDev/Hipforge.git](https://github.com/TMXDev/Hipforge.git)).
- [x] **Safe Environment**: `.env` is not committed; `.env.example` is present with safe placeholders.
- [x] **AMD Compute Slide**: Included in the presentation slide deck.
- [x] **Demo Video**: Recorded showing the Web UI/CLI migration and self-healing loop.
- [x] **Quick Startup**: Verified that `docker compose up --build` starts in under 60 seconds.
- [x] **Sample Projects**: Demo uses a small test folder instead of a heavy monorepo.

---

## 🧪 Running Tests Locally

Verify correctness by running the Python pytest suite:
```powershell
$env:PYTHONPATH="backend;."
python -m pytest tests/backend/test_validation_confidence.py tests/backend/test_migration_hardening.py tests/backend/test_diagnostics.py -q
```
