# HIPForge Demo Readiness Notes

Last verified: 2026-07-05

This document outlines the status and steps to run the HIPForge demo.

> [!IMPORTANT]
> **Honest Demo Status:**
> * **v0 is Compile-Validated by Default:** Today, HIPForge verifies translation correctness by checking if the generated HIP code builds successfully using the target compiler (`hipcc`).
> * **Runtime AMD GPU Validation is Optional/Future:** Running the translated binaries on physical AMD GPU hardware is currently disabled by default and marked for future releases. We do not claim runtime-verified migration.
> * **Recommended Demo Path:** It is highly recommended to run the demo via the **bare-metal** path rather than Docker Compose unless you have verified all network and volume configurations on your local setup.

---

## 1. Environment Verification (`hipforge doctor`)

Before starting, check your environment health using the doctor tool:

```bash
python cli/hipforge.py doctor
```

In mock mode (recommended for pitch demos), this checks dependencies and connectivity. In real mode, it checks for physical AMD GPU dependencies.

### Dependency-Error Path

If critical dependencies (like `hipcc`, CUDA/ROCm runtimes) are missing, `hipforge doctor` will fail and print detailed warnings:

```text
Missing Components
  [X] ROCm SDK (hipcc)
  [X] cuda_runtime.h
  [X] libdevice
```

To run a safe demo without these dependencies, switch to Mock Mode by setting the following in your `.env` file:

```env
USE_MOCK_AI=true
USE_MOCK_COMPILER=true
```

---

## 2. Recommended Demo Path (Bare-Metal)

Since Docker Compose setups can hide network or environment edge cases, bare-metal startup is recommended:

### Step 1: Start Redis
Ensure Redis is running (e.g., via Docker or locally on port 4444):
```bash
docker compose up -d redis
```

### Step 2: Configure Environment
Copy `.env.example` to `.env` and set:
```env
REDIS_URL=redis://localhost:4444
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
USE_MOCK_AI=true
USE_MOCK_COMPILER=true
```

### Step 3: Run Backend Service
From the root workspace, run the following to start the backend:
```bash
$env:PYTHONPATH="backend;."
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Step 4: Run Migration Worker
In another shell, start the background worker:
```bash
$env:PYTHONPATH="backend;."
python -m app.workers.migration_worker
```

### Step 5: Start Frontend
From the `frontend` directory:
```bash
npm run dev
```
Access the application at `http://localhost:3000`.

---

## 3. CLI Happy Path

You can also run migrations directly via the CLI:

```bash
python cli/hipforge.py migrate <path_to_cuda_file_or_directory> --output <output_directory> --arch gfx90a
```

Example command:
```bash
python cli/hipforge.py migrate workspace/input/kernel.cu --output workspace/output --arch gfx90a
```

This command submits the migration job to the backend, streams live logs, and saves the translated files once the compile-validation is complete.

---

## 4. Manual Web UI Checklist

If browser testing cannot be automated, follow this checklist to verify frontend readiness:

1. Open `http://localhost:3000/upload` in your web browser.
2. Select a target AMD GPU architecture (e.g., `gfx90a`).
3. Upload a sample `.cu` (CUDA) file or paste its code in the editor.
4. Click **Start Migration**.
5. You will be redirected to the dashboard page (`/migration/<id>`).
6. Observe the progress timeline, active steps, and compilation logs.
7. Confirm that the status updates to `COMPLETED` and the final translated report page renders.

---

## 5. Validation Confidence

At the end of a migration, HIPForge displays a **Validation Confidence** score (High, Medium, Low) based on:
1. **Compilation Success:** Whether the translated code successfully built with `hipcc`.
2. **Static Analysis (SCA):** Detection of CUDA-specific APIs or patterns that were not fully mapped or could cause runtime performance variance.
3. **AI Confidence:** Log-probabilities of translation confidence returned from the translation LLM.

This score informs the user of how much manual revision may be required before the code is ready for real AMD GPU deployment.
