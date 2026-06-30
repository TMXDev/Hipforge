# 06_WORKSPACE_ARCHITECTURE.md

Version: 1.0

Status: Pending

---

# Purpose

This document defines how HIPForge stores, organizes, and manages every migration session on disk.

The Migration Workspace is the single location where all files related to one migration are stored.

Each migration receives its own isolated workspace to ensure reliability, traceability, and future scalability.

---

# Goals

The Migration Workspace must:

- Isolate every migration.
- Preserve every important artifact.
- Prevent file conflicts.
- Support debugging.
- Support report generation.
- Be easy to clean up.
- Be predictable for developers and AI agents.

---

# Scope

This document defines:

- Workspace directory layout.
- File organization.
- Artifact lifecycle.
- Cleanup policy.
- Naming conventions.

It does NOT define:

- Redis state.
- Backend endpoints.
- AI prompts.
- Compiler implementation.

---

# Workspace Philosophy

A Migration Workspace is a temporary project environment created for a single migration.

Nothing outside the workspace may be modified.

Every generated file belongs inside the workspace.

---

# Workspace Creation

When a migration begins, the backend automatically creates:

```
workspace/

2026/
└── 07/
    └── migration_YYYYMMDD_HHMMSS_<SHORT_UUID>
```

Example

```
workspace/

2026/
└── 07/
    └── migration_20260701_143522_4fd4d857/
```

The Migration ID is generated automatically.

The Migration ID is also stored in Redis.

---

# Workspace Structure

```
workspace/

2026/
└── 07/
    └── migration_20260701_143522_4fd4d857/

├── input/
│
├── generated/
│
├── patches/
│
├── logs/
│
├── artifacts/
│
├── reports/
│
├── exports/
│
└── metadata.json
```

---

# Directory Responsibilities

## input/

Contains the original user files.

These files are never modified.

Examples

```
kernel.cu

matrix.cu

helper.cuh
```

---

## generated/

Contains the latest generated HIP source code.

Only the newest working version exists here.

Examples

```
kernel.hip

matrix.hip
```

---

## patches/

Contains every AI-generated patch.

Example

```
patch_001.diff

patch_002.diff

patch_003.diff
```

These files make debugging easier.

---

## logs/

Contains compiler output.

Examples

```
hipify.log

compile_attempt_1.log

compile_attempt_2.log

compile_attempt_3.log
```

Logs are never overwritten.

---

## artifacts/

Contains intermediate outputs.

Examples

```
analysis_001.json

research_001.md

compiler_summary.json

workflow_state.json
```

Artifacts document the complete migration process.

---

## reports/

Contains generated reports.

Example

```
migration_report.md

migration_report.pdf
```

PDF generation is optional in Version 1.

---

## exports/

Contains the final downloadable package.

Example

```
HIPForge_Migration.zip
```

---

## metadata.json

Stores migration metadata.

Example

```json
{
  "migration_id": "...",
  "status": "running",
  "created_at": "...",
  "retry_budget": 5,
  "current_attempt": 2,
  "compiler": "hipcc",
  "workflow_state": "analysis"
}
```

This file allows interrupted migrations to be resumed in future versions.

---

# Artifact Lifecycle

Every stage produces artifacts.

Example

Upload

↓

Original CUDA

↓

Hipify

↓

HIP Source

↓

Compile

↓

Compiler Log

↓

Analysis Agent

↓

Analysis Report

↓

Patch Agent

↓

Patch

↓

Compile Again

↓

Research Agent (if needed)

↓

Research Notes

↓

Final Report

Nothing is deleted during execution.

---

# Naming Conventions

Compiler Logs

```
compile_attempt_001.log
```

Patches

```
patch_001.diff
```

Analysis

```
analysis_001.json
```

Research

```
research_001.md
```

Reports

```
migration_report.md
```

Exports

```
HIPForge_Migration.zip
```

All numbering starts at 001.

---

# Cleanup Policy

Successful migrations

Workspace is retained until the user downloads the package.

Failed migrations

Workspace is retained so the user can inspect the logs.

Automatic Cleanup

Version 1:

No automatic deletion.

Future versions may automatically remove old workspaces after a configurable retention period.

---

# File Access Rules

The frontend never accesses the workspace directly.

Only the backend may:

- Read files.
- Write files.
- Delete files.
- Package files.

This prevents accidental modification and improves security.

---

# Workspace Isolation

Every migration is completely independent.

No migration may:

- Read another workspace.
- Modify another workspace.
- Share artifacts.
- Share logs.

This enables future concurrent execution.

---

# Recovery Support

If the backend restarts unexpectedly:

The Workflow Engine can recover the migration using:

- metadata.json
- Redis state
- Existing artifacts

Version 1 recovery is best-effort.

Future versions may support automatic resume.

---

# Export Package

The downloadable archive contains:

```
generated/

patches/

logs/

reports/

README.txt
```

The original uploaded files are not included by default.

This keeps the package lightweight.

---

# Design Principles

The Migration Workspace must be:

- Predictable
- Isolated
- Reproducible
- Debuggable
- Disposable

Every migration should be reproducible using only the contents of its workspace.

---

# Responsibilities

This document defines the on-disk organization of every migration session.

---

# Non-Responsibilities

This document does not define:

- Redis communication.
- AI logic.
- Compilation workflow.
- User interface.

---

# Dependencies

- 02_SYSTEM_ARCHITECTURE.md
- 03_PROJECT_STRUCTURE.md
- 05_USER_FLOW.md

---

# Used By

- 07_WORKFLOW_ENGINE.md
- 08_REDIS_ARCHITECTURE.md
- 10_COMPILATION_PIPELINE.md
- 13_BACKEND.md
- 17_REPORT_GENERATOR.md

---

# Acceptance Criteria

✓ Every migration has its own workspace.

✓ Workspace layout is fixed.

✓ File naming is standardized.

✓ Artifacts are preserved.

✓ Logs are never overwritten.

✓ Workspace isolation is guaranteed.

✓ Export package structure is defined.

---

# Startup Notes

Future SaaS Evolution

Future versions may replace the local workspace with object storage (such as Amazon S3 or Azure Blob Storage) while preserving the same logical directory structure.

The Workflow Engine should continue to treat the Migration Workspace as an abstraction rather than relying on local filesystem paths.

---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.