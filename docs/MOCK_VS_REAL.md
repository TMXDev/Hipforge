# Mock vs Real Modes

This document details the configuration and behaviors of the mock and real modes in HIPForge. It is designed to prevent incorrect claims and clarify how compile validation, AI self-healing, and infrastructure requirements differ between development/test environments and real AMD hardware environments.

---

## Configuration Toggles

HIPForge relies on environment variables (defined in `.env`) to switch between mock and real behaviors:

1. **`USE_MOCK_COMPILER`**:
   - `true` (Default): Simulates the behavior of `hipify-clang` and `hipcc` compiler tools. Ideal for testing backend workflow orchestration and frontend timelines offline.
   - `false`: Executes the actual `hipify-clang` and `hipcc` compilers within an isolated sandbox Docker container.

2. **`USE_MOCK_AI`**:
   - `true` (Default): Returns canned AI responses for compilation error diagnosis and patch suggestions. No API key or internet access required.
   - `false`: Interacts with real Fireworks AI agents to dynamically generate code explanations and patches. Requires a valid `FIREWORKS_API_KEY`.

3. **`RUNTIME_VALIDATION_ENABLED`**:
   - `false` (Default / Recommended for v0): Marks runtime validation status as `NOT_CONFIGURED` or `SKIPPED`. No binary execution on physical hardware is attempted.
   - `true` (Optional): v0 runtime validation hook. When enabled, if compilation fails, the status is marked `SKIPPED`. If compilation succeeds, it serves as a placeholder where status remains `SKIPPED` with a note that no binary was executed. **HIPForge v0 does not execute untrusted binaries on physical GPUs by default.**

---

## Component Differences Table

| Component / Subsystem | Mock Behavior | Real Behavior | Used in Tests? | Acceptable as AMD Compute Proof? |
| :--- | :--- | :--- | :--- | :--- |
| **Compiler Validation (`USE_MOCK_COMPILER`)** | Simulates exit code 0 or canned error diagnostics based on input text. | Invokes sandboxed `hipify-clang` and `hipcc` compilation. | **Yes** (mock in unit/integration tests; real in E2E tests). | **No.** Simulated compiler runs do not prove AMD ROCm/HIP toolchain compilation. |
| **AI Orchestration (`USE_MOCK_AI`)** | Returns static pre-configured repair plans and root causes. | Submits prompt slices to Fireworks AI (running on AMD Instinct GPUs). | **Yes** (mock in unit tests). | **Yes (Real AI mode only).** Each live agent query runs inference on AMD Instinct MI300X systems. |
| **Redis Database** | Test suites use `MockRedis` or `fakeredis` in memory. | Runs official Redis container (`redis:7-alpine`) on host/compose network. | **Yes** (mock in tests). | **No.** Local Redis caching is not proof of AMD GPU execution. |
| **Runtime GPU Execution** | Simulated execution output or skipped validation status. | Opt-in placeholder hooks; runtime status is marked `SKIPPED` or `NOT_CONFIGURED` in v0. | **No.** | **No.** HIPForge does not claim runtime-verified execution in v0. |

---

## Important Rules & Guarantees

> [!WARNING]
> **Mock compiler mode is not compilation validation.**
> Setting `USE_MOCK_COMPILER=true` allows the state machine to run without local ROCm compilers, but it **must never** be presented as proof of compilation validation or migration success.

> [!IMPORTANT]
> **Compile-only validation is not runtime validation.**
> Successfully compiling a translated HIP file with `hipcc` confirms that the code is syntactically valid and references supported HIP APIs. It **does not** prove that the code is free of runtime errors (e.g. out-of-bounds access, division by zero) or that it executes correctly on AMD GPU hardware.
>
> In the final reports, `runtime_validation_status` should remain `NOT_CONFIGURED` (or `SKIPPED` if enabled but bypassed) to reflect the fact that no binary was executed in v0.
