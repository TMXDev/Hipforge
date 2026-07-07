# HIPForge NotebookLM Reference Context

This document is a self-contained, comprehensive technical reference for the HIPForge project. It details the system architecture, state machine, compilation pipeline, AI self-healing agents, validation models, and setup/troubleshooting steps.

---

## 1. Project Summary & Hackathon Context

### Project Summary
HIPForge is a self-healing, AI-orchestrated migration platform designed to automate the translation, compilation validation, and error repair of Nvidia CUDA GPU code into AMD HIP/ROCm code.

### The Problem
Converting CUDA code to AMD HIP is often performed by standard tools like `hipify-clang`. While these tools automate initial syntactic translations, they frequently leave behind compile-time errors due to differences in APIs, compiler strictness, custom project build system layouts, or semantic incompatibilities. Debugging these issues (the "last 30%" of migration) has historically required manual developer intervention.

### The Solution (HIPForge)
HIPForge automates this debugging cycle. It runs deterministic translators (`hipify-clang`) and compile checks (`hipcc`), captures compile errors, and routes them through specialized LLM agents (Analysis, Patch, and Research) to automatically patch files, compile again, and iterate until the project builds successfully.

---

## 2. System Architecture & Flows

### Thin Client Architecture
HIPForge splits client operations from heavy compilation tasks:
- **Next.js Web UI**: Client dashboard for file uploads, live WebSocket event tracking, code diff viewing, and downloading packaged report archives.
- **Python CLI (`cli/hipforge.py`)**: Thin command-line program supporting interactive wizard mode (`/migrate`) and commands like `migrate`, `doctor` (diagnostic verification), and `self-test` (end-to-end installation test).
- **FastAPI Backend**: Receives migration files, creates local workspace structures, and enqueues jobs into Redis.
- **Redis Queue**: Serves as the asynchronous task broker and Pub/Sub channel.
- **Migration Worker**: Runs the Python Workflow Engine as a daemon process, popping tasks and executing the state machine.
- **Docker Sandbox**: Runs compilers (`hipify-clang`, `hipcc`) inside an isolated, containerized ROCm environment to prevent local host pollution.

### User Flows
1. **Web Flow**: Upload code or ZIP file via [http://localhost:3000](http://localhost:3000) -> FastAPI enqueues job -> redirected to `/migration/<id>` -> live WebSocket timeline updates -> download packaged ZIP.
2. **CLI Flow**: Execute `python cli/hipforge.py migrate <path> --output <out_path>` -> submits job -> streams logs over WebSocket to terminal -> saves result directory.
3. **API Flow**: Direct endpoints like `POST /api/v1/migrate/upload` (enqueue job) and `GET /api/v1/migrate/{id}/status` (poll status).

---

## 3. Workflow Stages & State Machine

The Workflow Engine manages transitions deterministically through the following states:

- **`QUEUED`**: Task is enqueued in Redis.
- **`PREPARING`**: Task is dequeued. Checks ZIP contents for traversals (Zip-slip) and extracts files.
- **`PREFLIGHT`**: Scans project layout and checks target architecture constraints. If files exceed limits (20 CUDA files, 1000 total files, 50MB extraction, 100MB archive) or if a multiple-entrypoint layout lacks a Makefile, the workflow fails early with `PROJECT_TOO_LARGE` or `MISSING_BUILD_SYSTEM`.
- **`HIPIFY`**: Recursively runs `hipify-clang` on source files. copies non-cuda files. Translates NVCC and CUDA file targets inside Makefiles and CMakeLists. Runs post-translation search-and-replace for known APIs.
- **`SCA`**: Deterministically analyzes code for semantic compatibility risks (e.g., texture memory, cooperative groups, `warpSize`). Writes risks to `migration_risks.json`.
- **`COMPILING`**: Executes `hipcc` or `make` inside the sandbox. Logs output. Runs post-compilation SCA checks to detect high-severity semantic bugs. Classifies errors; infrastructure/dependency compilation errors (missing headers, undefined symbols) set `infrastructure_error = True` and transition directly to reporting, skipping AI repair.
- **`ANALYZING`**: Triggers if compilation fails, retries are under budget, and no infrastructure issues exist. Queries Fireworks AI to classify the root cause and compile a repair plan. Bypasses AI if the error matches a previously cached lesson.
- **`PATCHING`**: Queries Fireworks AI to apply code updates. Post-processes patches with launcher safety guards. Increments `current_attempt` and returns to `COMPILING`.
- **`RESEARCHING`**: Queries ROCm documentation for unresolved issues.
- **`GENERATING_REPORT`**: Packages reports and diffs.
- **`COMPLETED` / `FAILED`**: Terminal states updating Redis job keys.

---

## 4. Code Generation & Hardening Details

### File Provenance Comments
To trace how files were generated and updated, HIPForge prepends provenance comments:
- **Preserved Files**: `// Preserved by HIPForge` (for pre-existing HIP files).
- **Translated Files**: `// Generated by HIPForge` (for translated CUDA files).
- **AI Repaired Files**: `// Generated by HIPForge (AI repaired)` (for AI-modified source files).

### Launcher Hardening Behavior
The validator scans for host launcher functions (e.g. signatures like `void run_xxx(...)`) and applies hardening edits:
- **Null Pointer Checks**: Inserts guards if pointer parameters are null (`ptr == nullptr`).
- **Size Guards**: Inserts size validations if size parameters are invalid (`N <= 0`).
- **Error Checks**: Appends `hipGetLastError()` error checks following kernel launches.
- **Synchronization**: Optionally appends `hipDeviceSynchronize()` for execution safety when `RUNTIME_VALIDATION_ENABLED=true`.

### File Lifecycle Tracking
tracks each file in `context.file_lifecycle` mapping relative source paths to:
- `original_path`, `generated_path`
- `converted` (bool), `modified_by_ai` (bool), `included_in_compile` (bool)
- `compile_status` (`PASSED`, `FAILED`, `SKIPPED`, `NOT_RUN`)
- `original_hash`, `generated_hash`
- `failure_reason`, `skipped_reason`

---

## 5. Status, Logging, and Event Model

### Stage Status Model
Stages return standard, clear statuses:
- **`PASSED`**: The file or compile attempt succeeded.
- **`FAILED`**: The file or compile attempt failed.
- **`SKIPPED`**: The stage was skipped (e.g., copying a HIP file directly without hipify, or bypassing runtime execution).
- **`NOT_RUN`**: The initial status before a stage starts.
- **`NOT_CONFIGURED`**: Default status for optional subsystems that are disabled (like runtime validation).

### WebSocket Event Stream
The migration worker publishes progress events to `hipforge:events:<migration_id>` Redis channel:
- **Events**: Schema `{"type": "event", "stage": stage, "status": status, "message": message}` where status is `started`, `completed`, or `failed`.
- **Live Logs**: Schema `{"type": "log", "message": message, "original_path": ..., "generated_path": ..., "stage": stage, "status": status}`.

---

## 6. Reports & Artifacts

All migration records are stored in a downloadable ZIP archive located at `workspace/<migration_id>/exports/HIPForge_Migration.zip`.

- **`generated/`**: Holds all final translated, patched, and hardened HIP source files.
- **`patches/`**: Keeps intermediate patches for audit trails.
- **`logs/`**: Sequential compile logs named `compile_attempt_*.log`.
- **`reports/migration_report.md`**: Human-readable Markdown summary.
- **`reports/migration_report.json`**: Structured machine-readable JSON summary.
- **`reports/git_patch.diff`**: Unified git-compatible diff comparing input files against generated code.

### Durable Migration History
Previous migrations can be listed and inspected using a file-backed history system stored at:
- **`workspace/history/<job_id>.json`**: A lightweight, durable history summary written when a migration completes or encounters a terminal failure.

This history does not rely on Redis (which is for active/live state) or a database. It is resolved directly from files. Detailed logs remain in the main report directories.


---

## 7. Validation Confidence Ladder

The confidence rating classifies migration success:
- **`LOW`**: hipify ran but compilation failed.
- **`MEDIUM`**: hipify and compilation succeeded; no runtime execution occurred (the default real-mode output).
- **`HIGH`**: Compilation succeeded and binary execution verified on physical AMD hardware (unsupported in v0).
- **`PROFILED`**: `HIGH` + profiling data collected (unsupported in v0).

---

## 8. Mock vs Real Modes

### Mock Mode (`USE_MOCK_COMPILER=true`, `USE_MOCK_AI=true`)
Used for workflow and UI demos. Simulates compilation outputs and AI answers without needing Docker, ROCm compilers, or internet API keys.

### Real Mode (`USE_MOCK_COMPILER=false`, `USE_MOCK_AI=false`)
- **Real Compiling**: Requires running Docker socket. It mounts the host workspace inside the sandbox image `hipforge-sandbox:latest` and invokes `hipify-clang` and `hipcc`.
- **Real AI**: Submits AST slices and errors to Fireworks AI (requires `FIREWORKS_API_KEY`).

---

## 9. AMD Compute Usage & Claims

### Submission-Safe Claims
- **Inference Acceleration**: All live AI queries (agents) run on **Fireworks AI's AMD Instinct™ MI300X GPU infrastructure**.
- **Target Offloading**: Compiled HIP code targets AMD CDNA/RDNA architectures (e.g. `gfx90a`, `gfx942`). Compile logs record the target architecture.

### Forbidden Claims (Do NOT make these)
- ❌ *"Runs/migrates any CUDA project"*
- ❌ *"Runtime verified on AMD GPU"* (No binaries run on GPU in v0; status is `NOT_RUN` or `SKIPPED`).
- ❌ *"Production-ready"*
- ❌ *"Guaranteed migration"*
- ❌ *"Mock compiler proves AMD compute"*

---

## 10. Verification, Setup, and Troubleshooting

### Fresh-Machine Setup
1. **Prerequisites**: Install Docker Desktop / Docker Engine and Git.
2. **Clone**:
   ```bash
   git clone https://github.com/TMXDev/Hipforge.git
   cd Hipforge
   ```
   *(Note: paths are case-sensitive on Linux, use `Hipforge` as cloned).*
3. **Environment**:
   ```bash
   cp .env.example .env
   ```
   Set `USE_MOCK_AI=true` and `USE_MOCK_COMPILER=true` for offline mock demo, or `false` with a Fireworks API key for real mode.
4. **Build Stack**:
   ```bash
   docker compose up --build -d
   ```
5. **Sanity Check**:
   ```bash
   curl http://localhost:8000/api/v1/health/check
   ```
   Expected response: `{"status":"ok","redis":"connected","version":"0.1.0"}`

### Verification Commands
- Check Docker Compose syntax: `docker compose config`
- Verify sandbox compilers:
  ```bash
  docker run --rm hipforge-sandbox:latest hipify-clang --version
  docker run --rm hipforge-sandbox:latest hipcc --version
  ```
- Run tests:
  ```bash
  $env:PYTHONPATH="backend;."
  python -m pytest tests/
  python -m pytest -m e2e_real -s -vv
  ```

### Troubleshooting
- **Git CA cert errors**: Host configuration issues. Check system certificates or run `git config --global http.sslVerify false`.
- **Docker Compose not found**: On modern systems use `docker compose` instead of `docker-compose`.
- **Backend/Worker offline**: Inspect logs via `docker compose logs backend` or `docker compose logs migration-worker`.
- **Upload Aborted**: Extract the project locally and verify the size limits are not exceeded.

---

## 11. Glossary

- **hipify-clang**: AMD's tool to translate CUDA syntax to HIP syntax using Clang AST parsing.
- **hipcc**: AMD's compiler wrapper to compile HIP code using ROCm device offloading.
- **SCA**: Semantic Compatibility Analyzer. Deteministic scanner to check for hidden translation limits.
- **Workflow Context**: Runtime memory containing variables for a single migration task.
- **Migration Journal**: Running ledger tracking compilation errors and agent fixes.
- **Validation Confidence**: Rating score (`LOW`/`MEDIUM`/`HIGH`) representing code translation and compilation validity.
