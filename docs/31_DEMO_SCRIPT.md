# 31_DEMO_SCRIPT.md

> **Hackathon Demo Guide** — A rehearsed, structured walkthrough of HIPForge that turns a technical tool into a compelling narrative.

---

## Core Narrative (30 seconds)

> "CUDA to ROCm migrations are painful. Developers waste days manually converting API calls, chasing compilation errors, and searching for fixes one by one. HIPForge automates the entire pipeline — upload CUDA, get ROCm — end to end, with live progress and a full audit trail."

---

## Preparation Checklist

Before the demo begins:

- [ ] Docker environment is running (`docker-compose up -d`)
- [ ] Redis is healthy (`docker-compose ps`)
- [ ] Migration Worker is running and waiting on the queue
- [ ] Frontend is accessible in the browser (`http://localhost:3000`)
- [ ] A real-world CUDA file is ready to upload (preferably one with at least 2–3 compiler errors to trigger AI repair)
- [ ] Browser window is zoomed in enough to be visible on a projector
- [ ] Terminal is open and tailing worker logs (for optional live view)

---

## Demo Flow

### Act 1 — The Problem (60 seconds)

**Say:**
> "CUDA runs on NVIDIA GPUs. ROCm runs on AMD GPUs. The APIs are similar but not identical. Every CUDA project has hundreds of calls that need to be translated — `cudaMalloc`, `cudaMemcpy`, `__syncthreads` — and each translation can hide a subtle bug."

**Show:**
- Open a raw CUDA `.cu` source file in the editor.
- Briefly highlight a few CUDA-specific API calls.
- Emphasize that doing this manually on a large project takes days or weeks.

---

### Act 2 — Upload (30 seconds)

**Say:**
> "With HIPForge, you simply upload your CUDA project."

**Show:**
1. Navigate to the Upload page at `http://localhost:3000`.
2. Drag and drop the CUDA file (or folder) into the upload zone.
3. Click **Start Migration**.
4. Show the `202 Accepted` status — the job is queued instantly. The API never blocks.

---

### Act 3 — Live Progress Timeline (90 seconds)

**Say:**
> "The Migration Worker immediately picks up the job and begins executing the pipeline. You can watch every stage in real time."

**Show:**
1. The live progress timeline activating on the frontend:
   - `QUEUED` → `PREPARING` → `HIPIFY` → `SCA` → `COMPILING`
2. Highlight the `HIPIFY` step completing — the deterministic translation finished.
3. Show `SCA` — the Semantic Compatibility Analyzer is checking for subtle API mismatches that hipify-clang misses.
4. Show `COMPILING` — `hipcc` is now compiling the translated code.

**If compilation errors appear:**
> "Here's where it gets interesting. hipcc found errors. That's expected — not every translation is perfect. HIPForge doesn't stop. It hands the errors to the AI repair loop."

---

### Act 4 — AI Repair Loop (60 seconds)

**Say:**
> "The Analysis Agent reads the compiler error, the Research Agent queries the AMD ROCm documentation, and the Patch Agent writes a fix. The system then recompiles. This loop repeats up to the configured retry limit."

**Show:**
1. Timeline moving through: `ANALYZING` → `PATCHING` → `RESEARCHING` → `COMPILING` (second pass).
2. The real-time log stream — show actual compiler errors and AI-generated patches arriving live in the UI.
3. Compilation succeeds. Timeline transitions to `GENERATING_REPORT`.

---

### Act 5 — Migration Journal (30 seconds)

**Say:**
> "Every iteration — every error, every patch, every AI decision — is recorded in the Migration Journal. This is your audit trail."

**Show:**
1. Open the Migration Journal panel.
2. Show the structured log: original error → analysis → patch applied → result.
3. Point out that this is stored persistently — it survives restarts.

---

### Act 6 — Generated Report (30 seconds)

**Say:**
> "When the migration completes, HIPForge generates a full report package."

**Show:**
1. Open the Report Viewer.
2. Show the Markdown summary — what was translated, what was repaired, compatibility score.
3. Briefly show the JSON report for programmatic consumption.
4. Show the Git patch file — a clean, reviewable diff of every change.

---

### Act 7 — Download Package (15 seconds)

**Say:**
> "Everything is packaged and ready to download — the migrated source, the report, and the patch file."

**Show:**
1. Click the **Download Package** button.
2. Show the `.zip` download completing.

---

### Act 8 — Closing (30 seconds)

**Say:**
> "What you just saw was a full CUDA to ROCm migration — translation, compilation, AI-driven repair, and reporting — in under two minutes. HIPForge doesn't just convert code. It explains what it did, why it made each change, and gives developers a complete audit trail they can trust."

**Optional closer if time allows:**
> "The architecture is fully containerized, horizontally scalable, and designed for enterprise workloads. Today it runs on one GPU. It can be scaled to handle multiple migrations in parallel by simply adding more worker containers."

---

## Timing Summary

| Act                   | Duration   |
| --------------------- | ---------- |
| Problem narrative     | 60 seconds |
| File upload           | 30 seconds |
| Live progress timeline | 90 seconds |
| AI repair loop        | 60 seconds |
| Migration Journal     | 30 seconds |
| Report viewer         | 30 seconds |
| Download              | 15 seconds |
| Closing               | 30 seconds |
| **Total**             | **~6 min** |

> [!TIP]
> Aim for 5–6 minutes. Leave 2–3 minutes for judge questions. Never exceed 8 minutes.

---

## Likely Judge Questions & Suggested Answers

| Question | Suggested Answer |
| -------- | ---------------- |
| "What AI model are you using?" | "We use Fireworks AI for inference, which gives us fast, cost-efficient access to open-source models optimized for code tasks." |
| "What if the AI can't fix the error after N retries?" | "The job transitions to FAILED state, the Migration Journal captures every attempted repair, and the developer gets a full diagnostic report explaining exactly where translation broke down." |
| "Can it handle large codebases?" | "Yes — the workspace is file-system based, not in-memory. Workers process one job at a time with dedicated GPU resources, and the system scales horizontally by adding more worker containers." |
| "How is this different from just running hipify manually?" | "hipify-clang handles ~70% of translations deterministically. HIPForge adds the Semantic Compatibility Analyzer for subtle API mismatches, then wraps the remaining errors in an AI repair loop with a full audit trail — something hipify alone cannot do." |
| "Is it production-ready?" | "It's hackathon-ready today. The architecture is designed for Kubernetes and enterprise-scale deployment — that's documented in our scalability spec." |

---

## What NOT to Do

- ❌ Don't demo a file that compiles clean with no errors — it makes the AI loop invisible.
- ❌ Don't skip the Migration Journal — it's one of the most differentiating features.
- ❌ Don't apologize for compilation errors appearing — frame them as "the interesting case."
- ❌ Don't read from slides — the live system is the demo.
- ❌ Don't exceed 8 minutes total.

---

## Version 2 Features (Mention Only — Do Not Demo)

If judges ask about future roadmap:

- **Migration Replay**: Replay any completed migration as if it were happening live — great for debugging and presentations.
- **Team workspaces**: Multi-user migration management.
- **Usage dashboards**: Analytics on migration success rates and AI repair effectiveness.

---

## Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.
