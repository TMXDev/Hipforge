# 🚀 HIPForge: AI-Powered CUDA to ROCm Migration Platform

HIPForge is a self-healing, AI-orchestrated migration assistant built to automate the translation, compilation, and error-repair of NVIDIA CUDA GPU code to AMD HIP/ROCm code.

By combining deterministic tools (`hipify-clang`, `hipcc`) with specialized Fireworks AI agents (Analysis, Patch, and Research), HIPForge automates the "last 30%" of migration debugging that standard compile-time translation tools leave behind.

> [!IMPORTANT]
> **Getting Started Quick Links:**
> * 📖 **[FRESH MACHINE RUNBOOK (docs/FRESH_MACHINE_RUNBOOK.md)](file:///C:/Users/Yassi/Downloads/HIPForge/docs/FRESH_MACHINE_RUNBOOK.md)**: Zero-configuration copy-pasteable judge guide from Git clone to health checks and E2E validation.
> * ⚙️ **[Demo Guide (README_DEMO.md)](file:///C:/Users/Yassi/Downloads/HIPForge/README_DEMO.md)**: UI/CLI workflow walkthrough, validation details, and size thresholds.
> * 📦 **[Platform Dependencies (docs/DEPENDENCIES.md)](file:///C:/Users/Yassi/Downloads/HIPForge/docs/DEPENDENCIES.md)**: Real ROCm installation specifications and sandbox info.

---

## 📢 AMD Track 3 Submission & Reality

HIPForge is fully optimized and submission-ready for the **LabLab.ai AMD Track 3** hackathon.

### 📌 Track 3 Submission Requirements
* **No Docker Image Required**: AMD Track 3 does not require a submitted Docker image (GitHub repository URL, demo video, and slide deck PDF are the primary requirements).
* **Reproducible Environment**: HIPForge includes complete Docker Compose support for easy, reproducible setup.
* **Fast Container Startup**: Default Docker Compose services are fully containerized with pre-installed dependencies. Startup is instantaneous and takes **under 60 seconds**, requiring no live package installations at runtime.
* **Linux/amd64 Support**: If a container image is built or submitted, it targets the standard `linux/amd64` architecture.

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
* **Validation Confidence Ladder (`v0`)**:
  * **LOW**: Translation completed, but `hipcc` compilation failed.
  * **MEDIUM (Default Demo Path)**: Translation and `hipcc` compilation passed successfully, compile-validated. This path is hardware-agnostic and does not require local AMD GPU hardware to demonstrate.
  * **HIGH**: Translation, compilation, and runtime validation succeeded on physical AMD GPU hardware (optional/future).
  * **PROFILED**: Runtime validation passed, and compute efficiency profiling data (`rocprof`) was collected (optional/future).

---

## 📊 Slide Deck Outline: "AMD Compute / ROCm Usage"

Below is the structured content for the required AMD Compute slide in the submission deck:

* **Fireworks AI Agents**: Analysis, Patch, and Research agents run via Fireworks inference platform.
* **AMD Instinct Infrastructure**: Powered by the Fireworks AI and AMD Instinct MI300 series GPU hardware partnership.
* **CUDA-to-HIP Migration**: Translates CUDA APIs and compiles using `hipcc`.
* **Target Compilation**: Explicit target support for AMD Instinct architectures, including `gfx90a` and `gfx942`.
* **Validation Confidence Ladder**: Outlines compile-validated `v0` migrations (Medium confidence) with optional runtime validation (High confidence) on physical GPU hardware.

---

## 📋 Track 3 Submission Checklist

Before submitting to LabLab.ai, ensure the following checklist is completed:

- [x] **GitHub Repository**: Repository is public and includes this README.
- [x] **Safe Environment**: `.env` is not committed; `.env.example` is present with safe placeholders (`FIREWORKS_API_KEY=CHANGE_ME`).
- [x] **AMD Compute Slide**: Included in the presentation slide deck.
- [x] **Demo Video**: Recorded showing the Web UI/CLI migration and self-healing loop.
- [x] **No Docker Image Required**: Wording updated to clarify Track 3 Docker reality.
- [x] **Quick Startup**: Verified that `docker compose up --build` starts in under 60 seconds with no runtime package downloads.
- [x] **Clean Workspace**: No large binary assets (e.g. `cuda-samples.zip`) are committed.
- [x] **Sample Projects**: Demo uses a small test folder instead of a heavy monorepo.

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

## ⚙️ Configuration & Quick Setup

### ⚡ 5-Line Quick Start
```bash
git clone <PUBLIC_REPO_URL>
cd HIPForge
cp .env.example .env             # (PowerShell: Copy-Item .env.example .env)
docker compose up --build -d
docker compose ps
```

### 📖 Platform Documentation & Runbooks
* **[Fresh Machine Runbook (docs/FRESH_MACHINE_RUNBOOK.md)](file:///C:/Users/Yassi/Downloads/HIPForge/docs/FRESH_MACHINE_RUNBOOK.md)**: Zero-configuration copy-pasteable guide from Git clone to E2E tests, CLI migrations, and real compiler validation checks.
* **[Environment Dependencies (docs/DEPENDENCIES.md)](file:///C:/Users/Yassi/Downloads/HIPForge/docs/DEPENDENCIES.md)**: Details on physical ROCm host prerequisites, docker sandboxing, and manual setup guides.
* **[Demo Execution Guide (README_DEMO.md)](file:///C:/Users/Yassi/Downloads/HIPForge/README_DEMO.md)**: Walkthroughs, UI checklists, validation confidence score breakdown, and size limits.

---

## 🧪 Running Tests

Verify correctness by running the Python pytest suite:
```powershell
$env:PYTHONPATH="backend;."
python -m pytest tests/backend/test_validation_confidence.py tests/backend/test_migration_hardening.py tests/backend/test_diagnostics.py -q
```
