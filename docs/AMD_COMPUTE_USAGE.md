# AMD Compute Usage

This document describes how HIPForge integrates with and targets AMD compute hardware and software architectures. All claims in this document are aligned with the actual capabilities of the v0 codebase and must be represented truthfully in any demo or submission notes.

---

## 1. Fireworks AI on AMD Instinct GPUs

When live AI mode is active (`USE_MOCK_AI=false`), the AI self-healing agents (Analysis, Patch, and Research) make real-time API calls to the **Fireworks AI Inference Platform**. 

- **Hardware Acceleration**: Fireworks AI runs its models (such as `deepseek-v4-flash`) on **AMD Instinct™ GPU infrastructure** (specifically AMD Instinct™ MI300X accelerators).
- **Proof of Integration**: Every query sent to the agents for diagnosing compilation errors, suggesting code fixes, or researching documentation is processed by an AMD Instinct GPU.

---

## 2. ROCm / HIP Target Compilation

When real compiler validation is active (`USE_MOCK_COMPILER=false`), the migration worker compiles generated code against the AMD ROCm/HIP compiler stack.

- **Target Architectures**: HIPForge targets specific AMD CDNA and RDNA architectures. The target architecture is selectable by the user in both the Web UI and CLI (e.g. `--arch gfx942`). Common target architectures include:
  - `gfx90a` (AMD Instinct™ MI210 / MI250 / MI250X)
  - `gfx941` (AMD Instinct™ MI300A APU)
  - `gfx942` (AMD Instinct™ MI300X Accelerator)
  - `gfx1030` (RDNA™ 2 / Radeon RX 6000 series)
  - `gfx1100` (RDNA™ 3 / Radeon RX 7000 series)
- **Compilation Command Logging**: The report generator logs the exact compilation command executed by the sandboxed `hipcc` compiler. For example:
  ```bash
  hipcc --offload-arch=gfx942 -c main.hip -o main.o
  ```
  These command logs are recorded in `logs/compile_attempt_*.log` and summarized in the migration reports (`reports/migration_report.md` and `reports/migration_report.json`).

---

## 3. Honest Disclaimers & Limits

To maintain submission integrity, please adhere to the following limitations when discussing HIPForge:

* **No Runtime Validation by Default**: In v0, runtime GPU execution of compiled binaries is disabled. `RUNTIME_VALIDATION_ENABLED` is set to `false` by default, and the runtime validation status is logged as `NOT_CONFIGURED` or `SKIPPED`. HIPForge does not verify numerical correctness or runtime memory safety on physical AMD GPU hardware.
* **Compile-Validation Focus**: The system is designed to verify that the translated code builds successfully. Successfully compiling a HIP file is a critical first step but does not guarantee runtime stability.
* **Mock Compiler Mode is Bypassed**: Setting `USE_MOCK_COMPILER=true` bypasses all ROCm toolchains. Simulated compile success does not constitute proof of compiler validation or AMD compute usage.

---

## 4. Forbidden Claims

Do **NOT** make any of the following claims:

- ❌ *"Runs/validates any CUDA project automatically"* (Large or complex codebases will hit project-size preflight guards, and many proprietary libraries are not supported).
- ❌ *"Runtime verified on AMD GPU"* (No binaries are run on AMD GPUs in v0).
- ❌ *"Production-ready"* (HIPForge is a v0 prototype tool).
- ❌ *"Guaranteed migration"* (AI self-healing has a retry budget and may fail to resolve complex compiler issues).
- ❌ *"Mock compiler proves AMD compute"* (Simulation does not invoke any AMD ROCm/HIP tools).
