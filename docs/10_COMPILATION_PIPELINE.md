# 10_COMPILATION_PIPELINE.md

Version: 1.0

Status: Pending

---

# Purpose

This document defines the complete CUDA-to-HIP compilation pipeline executed by HIPForge.

The compilation pipeline transforms CUDA source code into validated HIP code using deterministic tooling first, followed by AI-assisted repair only when necessary.

The compiler is always considered the final source of truth.

---

# Goals

The compilation pipeline must:

- Minimize AI usage.
- Prefer deterministic tools.
- Validate every generated file.
- Produce reproducible results.
- Preserve debugging information.
- Fail safely.

---

# Scope

This document defines:

- Translation pipeline
- Compilation workflow
- Validation process
- Retry execution
- Pipeline outputs

It does NOT define:

- Redis architecture
- AI prompts
- Frontend behavior

---

# Pipeline Overview

Every migration follows the same pipeline.

```
Choose Input Method
(Paste Code | Upload .cu | Upload .zip)

↓

Create Migration Workspace

↓

Run hipify-clang

↓

Run Semantic Compatibility Analyzer (SCA)

↓

Generate migration_risks.json

↓

Run hipcc

↓

Compilation Success?

├── YES
│
│ ↓
│
│ Optional rocprof Profiling
│
│ ↓
│
│ Generate Engineering Reports
│
│ ↓
│
│ Export Migration Package
│
└── NO
    │
    ▼
Analysis Agent

↓

Patch Agent

↓

Run hipcc Again

↓

Compilation Success?

├── YES

│

↓
│
Optional rocprof Profiling

│

↓

Generate Reports

└── NO

↓

Research Agent

↓

Migration Journal Update

↓

Retry
```

---

# Stage 1 — Workspace Preparation

The Workflow Engine:

- Creates a Migration Workspace.
- Copies uploaded files.
- Validates supported extensions.
- Generates metadata.

Supported files include:

```
.cu
.cuh
.h
.hpp
.cpp
.cmake
CMakeLists.txt
```

---

# Stage 1.5 — Checkpoint Creation

HIPForge creates immutable workspace checkpoints throughout the migration process.

A checkpoint is a complete snapshot of the project at a specific stage of the workflow.

Checkpoints are never modified after creation.

They allow HIPForge to:

- Roll back failed AI modifications.
- Compare different migration attempts.
- Generate before-and-after code comparisons.
- Improve debugging.
- Support future visual timeline features.
- Preserve a complete migration history.

Every migration automatically creates checkpoints at the following stages:

```
checkpoint_000_original/

Original uploaded CUDA project

↓

checkpoint_001_hipify/

After hipify-clang translation

↓

checkpoint_002_patch/

After each successful AI patch

↓

checkpoint_final/

Final exported project
```

If an AI-generated patch causes new compiler failures or significantly degrades the migration, the Workflow Engine can restore the previous checkpoint instead of attempting to repair an already degraded version.

This ensures every AI iteration begins from the last known stable state rather than accumulating incorrect modifications.

# Stage 2 — HIP Translation

HIPForge executes:

```
hipify-clang
```

Inputs:

- CUDA source
- Include paths

Outputs:

- HIP source
- hipify log

If hipify fails:

Stop workflow.

Generate failure report.

---

# Stage 2.5 — Semantic Compatibility Analysis

Before attempting compilation, HIPForge executes the **Semantic Compatibility Analyzer (SCA)**.

The SCA is a deterministic inspection engine that scans translated HIP source code for CUDA constructs known to behave differently on AMD hardware.

Unlike AI agents, the SCA never modifies code.

Instead, it produces a structured compatibility report that becomes part of the Workflow Context.

The analysis_agent currently detects migration risks such as:

- warpSize assumptions
- Cooperative Groups
- Inline PTX
- Dynamic Shared Memory
- CUDA Graphs
- Texture References
- Surface References
- Tensor Core intrinsics
- CUB
- Thrust

Generated artifact:

```
migration_risks.json
```

The Workflow Engine attaches this report to every AI iteration, allowing the agents to make architecture-aware repair decisions instead of relying only on compiler errors.

# Stage 3 — Initial Compilation

HIPForge executes:

```
hipcc
```

Compiler output collected:

- Exit code
- stdout
- stderr
- execution time

Decision:

Exit Code = 0

↓

Pipeline Success

Otherwise

↓

AI Repair Pipeline

---

# Stage 4 — AI Repair Pipeline

Analysis Agent

↓

Repair Plan

↓

Patch Agent

↓

Modified HIP Code

↓

Compilation

The compiler always validates generated code.

---

# Stage 5 — Research Recovery

Executed only when:

- Patch attempt failed.

The Research Agent searches:

- ROCm documentation
- HIP documentation
- AMD examples
- GitHub issues

Research results are added to the Migration Journal.

---

# Research Trigger Strategy

The Research Agent is an expensive operation and should only execute when deterministic repair is unlikely to succeed.

The Workflow Engine determines whether research is required using the following rules.

## Immediate Research

Run the Research Agent immediately if the compiler error indicates:

- Unsupported CUDA API
- Missing ROCm equivalent
- Architecture-specific behavior
- Unsupported compiler intrinsic
- Missing HIP runtime functionality

## Delayed Research

For common compiler issues such as:

- Syntax errors
- Missing includes
- Type mismatches
- Namespace issues
- Template errors

The Workflow Engine should allow one complete Analysis → Patch → Compile cycle before invoking the Research Agent.

## Duplicate Failure Detection

Before launching the Research Agent, the Workflow Engine compares the latest compiler error against previous Migration Journal entries.

If the error is substantially identical to a previous failed attempt, research is immediately triggered to avoid repeating ineffective repair strategies.

This reduces unnecessary AI usage while improving recovery quality.

# Retry Loop

Each retry performs:

```
Analysis

↓

Patch

↓

Compile

↓

Research (if required)
```

The retry counter increases after each Patch attempt.

The Workflow Engine stops when:

- Compilation succeeds.
- Retry budget is exhausted.

---

# Validation Rules

Every compilation must verify:

- Successful translation.
- Compiler exit code.
- Generated binary (if applicable).
- Fatal warnings.
- Missing includes.
- Unsupported APIs.

---

# Compiler Output

Compiler logs are saved as:

```
logs/

compile_attempt_001.log

compile_attempt_002.log

...
```

Logs are never overwritten.

---

# Generated Artifacts

The pipeline produces:

```
converted_project/

checkpoints/

analysis/

patches/

research/

logs/

reports/

migration_risks.json

migration_journal.json

compatibility_report.md

git_patch.diff

README.md
```

These artifacts become part of the final export.

---

# Failure Conditions

Pipeline termination occurs if:

- Upload invalid.
- hipify crashes.
- Compiler crashes.
- Retry budget exceeded.
- Workspace unavailable.
- Internal system error.

Every failure generates:

- Log
- Report entry
- Journal entry
- Frontend notification

---

# Performance Goals

The pipeline should:

- Avoid unnecessary AI calls.
- Avoid recompiling unchanged code.
- Preserve successful patches.
- Create immutable workspace checkpoints.
- Support rollback to the last stable checkpoint.
- Minimize token usage.
- Maximize deterministic execution before AI.

---

# Design Principles

The pipeline must be:

- Deterministic
- Observable
- Recoverable
- Versioned
- Modular
- Reproducible

---

# Responsibilities

The pipeline is responsible for:

- Translation
- Compilation
- Validation
- Repair execution
- Artifact generation

---

# Non-Responsibilities

The pipeline does NOT:

- Manage Redis.
- Generate reports.
- Render UI.
- Decide retry limits.

---

# Dependencies

05_USER_FLOW.md

06_WORKSPACE_ARCHITECTURE.md

07_WORKFLOW_ENGINE.md

09_AI_AGENTS.md

---

# Used By

13_BACKEND.md

17_REPORT_GENERATOR.md

20_TESTING.md

---

# Acceptance Criteria

✓ hipify executes first.

✓ Compiler validates every modification.

✓ AI activates only after compiler failure.

✓ Retry loop is deterministic.

✓ Logs are preserved.

✓ Artifacts are generated.

✓ Final report can be produced.

---

# Startup Notes

# Future Enhancements

The pipeline has been designed to support future capabilities without changing its architecture.

Planned enhancements include:

- Parallel compilation of independent source files.
- Incremental compilation to avoid rebuilding unchanged code.
- Automatic performance profiling using `rocprof`.
- Architecture-specific optimization passes.
- Semantic Compatibility Analyzer rule updates.
- Additional AI providers.
- Distributed worker execution.

All future improvements must preserve the deterministic-first philosophy of HIPForge.
---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.