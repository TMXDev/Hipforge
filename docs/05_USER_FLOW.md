# 05_USER_FLOW.md

Version: 1.0

Status: Pending

---

# Purpose

This document defines the complete end-to-end user journey inside HIPForge.

It describes every interaction between the user and the system from the moment a CUDA project is uploaded until the final migration package is downloaded.

This document represents the functional behavior of HIPForge and serves as the reference for both frontend and backend implementation.

---

# Goals

The user flow should:

- Be simple.
- Require minimal user interaction.
- Prioritize deterministic migration.
- Keep the user informed in real time.
- Produce transparent results.
- Recover gracefully from failures.

---

# Scope

This document defines:

- User interactions.
- System responses.
- Migration lifecycle.
- Error handling.
- Completion workflow.

It does NOT define:

- API endpoints.
- Redis schema.
- AI prompts.
- Backend implementation.

---

# User Journey Overview

The migration process consists of six phases.

1. Project Upload
2. Automatic Translation
3. Compilation Validation
4. Intelligent Repair
5. Report Generation
6. Download

The entire workflow is designed to minimize manual intervention.

---

# Phase 1 — Project Upload

User Actions

The user opens HIPForge.

The user chooses one of three input methods:

- Paste raw CUDA source code directly into the editor.
- Upload a single `.cu` source file.
- Upload a complete CUDA project as a `.zip` archive.

The system automatically detects the selected input method and prepares the appropriate Migration Workspace.

This flexibility allows HIPForge to support quick experiments, individual kernels, and full production projects without changing the workflow.

---

System Actions

The backend:

- Creates a unique Migration Workspace.
- Copies uploaded files into the workspace.
- Generates a Migration ID.
- Initializes the Migration Journal.
- Updates the UI.

UI Status

```
Project uploaded successfully.
Preparing migration...
```
## Advanced Migration Options

Before starting the migration, the user may optionally configure advanced settings.

These settings allow developers to tailor the migration process to their project while keeping the default experience simple for beginners.

### Target AMD GPU Architecture

The user can select the target GPU architecture.

Examples:

- MI210
- MI250
- MI300
- MI300X

The selected architecture is provided to the AI agents and compiler configuration to generate hardware-aware migration recommendations.

Default:

Latest Stable Architecture

---

### Retry Budget

The user selects the maximum number of AI repair attempts.

Available Range

- Minimum: 1
- Default: 5
- Maximum (Community Edition): 10

Future commercial editions may allow higher retry budgets.

---

### Migration Mode

Users may choose how conservative the migration should be.

Available Modes

#### Strict

- Prioritizes correctness.
- Avoids risky optimizations.
- Stops when uncertain.
- Recommended for production workloads.

#### Balanced (Default)

- Balances correctness and automation.
- Performs common optimizations when confidence is high.

#### Experimental

- Allows more aggressive AI-assisted modifications.
- May introduce larger code transformations.
- Intended for research and experimentation.

---

### Performance Profiling

If supported by the execution environment, users may enable AMD profiling using:

```
rocprof
```

When enabled, HIPForge performs a profiling pass after successful compilation and includes performance metrics inside the Migration Report.

This option is automatically disabled if profiling tools are unavailable.

---

### Generated Deliverables

Users may choose which artifacts should be included in the final migration package.

Available options include:

- Migration Report
- Compatibility Report
- Git Patch
- Build Scripts
- README
- Migration Journal

All options are enabled by default.
---

# Phase 2 — Automatic Translation

The Workflow Engine starts automatically.

The compiler subsystem executes:

```
hipify-clang
```

The translated HIP source is stored inside the Migration Workspace.

Before compilation begins, HIPForge executes the **Semantic Compatibility Analyzer (SCA)**.

The SCA performs a deterministic scan of the translated HIP source code to detect known CUDA constructs that may compile successfully but behave differently on AMD hardware.

Unlike the AI agents, the SCA never edits code.

It generates a structured `migration_risks.json` report that becomes part of the Workflow Context for all subsequent AI-assisted repair stages.

Examples of detected migration risks include:

- warpSize assumptions
- Cooperative Groups
- Inline PTX
- Dynamic Shared Memory
- CUDA Graphs
- Tensor Core intrinsics
- CUB
- Thrust

UI Status

```
Translating CUDA → HIP...
```

Progress Indicator

Step 1 / 6

---

# Phase 3 — Compilation Validation

HIPForge immediately validates the generated code.

The compiler executes:

```
hipcc
```

Two outcomes are possible.

---

## Scenario A — Compilation Success

If compilation succeeds:

The Workflow Engine skips every AI component.

Actions

- Save generated HIP source.
- Generate report.
- Package artifacts.
- Notify frontend.

UI

```
Migration completed successfully.
```

The migration ends.

---

## Scenario B — Compilation Failed

If compilation fails:

Actions

- Save compiler logs.
- Store error details.
- Record Attempt 1.
- Trigger the Analysis Agent.

UI

```
Compilation failed.
Analyzing compiler diagnostics...
```

---

# Phase 4 — Intelligent Repair

This phase is entered only after compilation failure.

The Analysis Agent:

- Reads compiler logs.
- Identifies root causes.
- Produces a repair plan.

The Patch Agent:

- Applies targeted fixes.
- Preserves unaffected code.
- Creates a patch artifact.

The Workflow Engine:

Runs hipcc again.

---

## Repair Successful

If compilation succeeds:

Generate migration report.

Notify frontend.

End workflow.

---

## Repair Failed

The Workflow Engine activates the Research Agent.

---

# Phase 5 — Research Recovery

The Research Agent:

Searches:

- ROCm documentation
- HIP documentation
- AMD examples
- GitHub issues
- Migration guides

The agent generates:

- Research summary
- Suggested strategy
- Supporting references

The Migration Journal records:

- Attempt number
- Compiler errors
- Analysis summary
- Patch summary
- Research findings

The Workflow Engine starts another repair attempt.

---

# Retry Strategy

# Retry Strategy

The Workflow Engine uses a configurable retry budget.

Default:

5 retries

Configuration Rules

Minimum:

1 retry

Default:

5 retries

Maximum (V1):

10 retries

The retry budget is selected by the user through the Advanced Options panel before the migration begins.

Each retry consists of the following stages:

1. Review previous Migration Journal entries.
2. Review detected Semantic Compatibility Risks.
3. Analyze the latest compiler diagnostics.
4. Generate a targeted patch.
5. Recompile using `hipcc`.
6. Perform web research if compilation still fails.
7. Record the complete attempt in the Migration Journal.

Every retry builds upon previous attempts, preventing repeated unsuccessful fixes and continuously improving the available context.

The Workflow Engine terminates the migration when:

- Compilation succeeds, or
- The retry budget is exhausted.

Future commercial versions may expose higher retry budgets depending on subscription plans.

Attempt 1

↓

Compile

↓

Repair

↓

Compile

↓

Research

↓

Attempt 2

↓

...

If maximum retries are reached:

Stop workflow.

Generate failure report.

---

# Phase 6 — Report Generation

The report contains:

- Migration summary
- Files modified
- Compiler diagnostics
- AI reasoning summary
- Research summary
- Migration Journal
- Final status

Artifacts are packaged automatically.

---

# Download

The user receives:

```
migration.zip
```

Contents

```
converted_project/

migration_report.md

migration_journal.json

compatibility_report.md

migration_risks.json

build.sh

CMakeLists.txt

git_patch.diff

README.md

logs/
```

---

# Live Progress Updates

Throughout the migration the user receives live updates.

Examples

```
Preparing workspace...

Running hipify-clang...

Analyzing semantic compatibility...

Compiling with hipcc...

Compilation failed.

Analyzing compiler diagnostics...

Applying targeted patch...

Recompiling...

Searching ROCm documentation...

Updating Migration Journal...

Generating engineering reports...

Migration completed successfully.
```

The interface should never appear frozen.

---

# Failure Handling

Possible failures include:

Unsupported CUDA features

Compiler crashes

AI provider unavailable

Invalid source files

Timeouts

In every case:

The workflow terminates safely.

The user receives a detailed explanation.

No corrupted files are returned.

---

# User Responsibilities

The user only needs to:

- Upload a project.
- Wait for migration.
- Download results.

No compiler knowledge is required.

---

# System Responsibilities

HIPForge is responsible for:

- Translation.
- Validation.
- Repair.
- Research.
- Reporting.
- Progress updates.

---

# Design Principles

The user should always know:

- What is happening.
- Why it is happening.
- What HIPForge is currently doing.
- Whether user input is required.

No hidden processing should occur.

---

# Acceptance Criteria

✓ Upload works.

✓ Migration starts automatically.

✓ Translation is automatic.

✓ Compiler validation occurs before AI.

✓ AI only activates when necessary.

✓ Reports are generated.

✓ Download package is available.

✓ Errors are explained.

---

# Dependencies

- 00_SYSTEM_SPECIFICATION.md
- 01_PRODUCT_VISION.md
- 02_SYSTEM_ARCHITECTURE.md
- 03_PROJECT_STRUCTURE.md
- 04_TECHNOLOGY_DECISIONS.md

---

# Used By

- 06_WORKSPACE_ARCHITECTURE.md
- 07_WORKFLOW_ENGINE.md
- 08_REDIS_ARCHITECTURE.md
- 13_BACKEND.md
- 14_FRONTEND.md
- 17_REPORT_GENERATOR.md

---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.