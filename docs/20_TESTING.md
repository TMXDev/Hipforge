# 20_TESTING.md

Version: 1.0

Status: Pending

---

# Purpose

This document defines the testing strategy for HIPForge. A robust testing framework is essential to ensure the correctness, reliability, and performance of the migration process. It covers unit, integration, and end-to-end testing across all components, with a particular focus on the deterministic nature of the workflow and the behavior of AI agents.

---

# Goals

The testing strategy must:

- Ensure the correctness of CUDA-to-HIP translations.
- Validate the integrity of the compilation pipeline.
- Verify the deterministic behavior of the Workflow Engine.
- Assess the effectiveness and reliability of AI agents.
- Prevent regressions with new features or changes.
- Provide confidence in the overall system functionality.
- Support continuous integration and deployment.

---

# Scope

This document covers:

- Unit testing for individual functions and modules.
- Integration testing for component interactions.
- End-to-end testing for the complete migration workflow.
- Testing of AI agent outputs and their impact.
- Performance testing considerations.
- Security testing considerations.

This document does NOT define:

- Specific testing frameworks or libraries (e.g., Pytest, Jest).
- Detailed test case specifications for every function.
- User acceptance testing (UAT) procedures.
- Manual testing procedures.

---

# Testing Philosophy

HIPForge's testing philosophy is built on the principle of **determinism** and **reproducibility**. Given the same input, the system should always produce the same output, especially for the core compilation and deterministic analysis stages. AI agent testing focuses on validating structured outputs and ensuring their actions lead to compiler-validated improvements, rather than evaluating subjective quality.

---

# Scope of Tests

- **Unit Tests**: Coverage of individual helper services (e.g. `workspace/manager.py`, `redis/client.py`, Pydantic models).
- **Integration Tests**: Tests state transitions in `workflow_engine/` and verifies task dequeuing/event broadcasting under `migration_worker.py`.
- **E2E Tests**: Simulates full project uploads, mock compiler error cycles, and checks that a final zip package containing correct reports is generated.

---

# Dependencies

- `02_SYSTEM_ARCHITECTURE.md`
- `07_WORKFLOW_ENGINE.md`
- `13_BACKEND.md`
- `19_SECURITY.md`
- `24_SCALABILITY.md`

---

# Used By

- `27_MAINTENANCE.md`
- `21_DEPLOYMENT.md`

---

# Acceptance Criteria

✓ Core logic (Workflow Engine state runner) has >80% test coverage.
✓ Asynchronous task processing can be simulated using mock Redis queues.
✓ AI agent prompts are testable with isolated mock model responses.
✓ Final output zip contains all required reports.

---

# Implementation Status

Completed

---

# Real Test Levels

- **`pytest`**: Fast unit/integration tests that run locally with mock toolchains and mock databases.
- **`pytest -m e2e_real`**: Real AMD ROCm toolchain smoke tests. These tests skip automatically if ROCm tools (`hipcc`/`hipify-clang`) or `Redis` are not available, ensuring the CI/CD pipeline never false-passes or fails on standard environments.
- **Manual AMD GPU Runtime Test**: Execute the migrated binary directly on an AMD GPU platform to verify actual output equivalence.
- **Manual AMD GPU Profiling Test**: Run `rocprof` validation on the compiled HIP execution binary to verify compute efficiency.