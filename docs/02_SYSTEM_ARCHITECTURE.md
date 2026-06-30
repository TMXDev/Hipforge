# 02_SYSTEM_ARCHITECTURE.md

Version: 1.0

Status: Pending

---

# Purpose

This document defines the complete technical architecture of HIPForge.

It describes every major subsystem, how components communicate, where data is stored, and how the complete migration pipeline operates.

This document serves as the architectural blueprint for implementation.

---

# Goals

The architecture must:

- Be modular.
- Be containerized.
- Be easy to debug.
- Minimize AI costs.
- Keep deterministic tools first.
- Support future extensions.
- Keep every component independent.

---

# Scope

This document covers:

- High-level architecture
- Major components
- Communication flow
- Runtime workflow
- Data movement
- System boundaries

This document does NOT cover:

- API endpoints
- Redis schema
- Security implementation
- Docker configuration
- Prompt engineering

Those are documented separately.

---

# High-Level Architecture

The HIPForge platform consists of nine major subsystems.

1. Frontend
2. Backend
3. Workflow Engine
4. Redis
5. AI Agent Layer
6. Workspace
7. Compiler Pipeline
8. Semantic Compatibility Analyzer (SCA)
9. Report Generator
---

# Overall System Diagram

                         User
                           │
                           ▼
                ┌──────────────────┐
                │ Next.js Frontend │
                └────────┬─────────┘
                         │
              HTTP + WebSocket
                         │
                         ▼
               ┌─────────────────┐
               │ FastAPI Backend │
               └────────┬────────┘
                        │ LPUSH
                        ▼
             ┌─────────────────────┐
             │ Redis Job Queue     │
             │ (hipforge:queue:...)│
             └──────────┬──────────┘
                        │ BRPOP
                        ▼
             ┌─────────────────────┐
             │   Migration Worker   │
             │ (Workflow Engine)   │
             └──────────┬──────────┘
                        │
      ┌─────────────────┼────────────────┐
      ▼                 ▼                ▼
 Workspace            Redis        Compiler Tools
 (Storage)       (Shared Memory)  (hipify / hipcc)
      │                 │                │
      │                 │                │
      ▼                 ▼                ▼
                 AI Agent Layer
         Analysis → Patch → Research
                        │
                        ▼
                Report Generator
                        │
                        ▼
               Download Package

---

# Component Overview

## Frontend

Technology:

- Next.js
- TypeScript
- TailwindCSS

Responsibilities:

- File upload
- Live migration progress
- Timeline visualization
- Log viewer
- Code comparison
- Migration report
- Download interface

The frontend contains no migration logic.

---

## Backend

Technology:

FastAPI

Responsibilities:

- Receive uploads
- Manage workspace
- Execute compiler
- Launch workflow_engine
- Communicate with Redis
- Call Fireworks AI
- Stream updates
- Generate reports

The backend is the central coordinator.

---

## Workflow Engine

Technology

Custom Python State Machine

Purpose

The Workflow Engine coordinates the entire migration process.

It is implemented as a lightweight deterministic state machine run within a standalone **Migration Worker** process. Every state represents one stage of the migration pipeline.

Example states include:

- Initialize
- Hipify
- Compile
- Analyze
- Patch
- Search
- Report
- Complete

Each state performs one responsibility before deciding which state should execute next.

The Workflow Engine never performs AI reasoning itself.

Responsibilities

- Execute workflow states sequentially within the Migration Worker.
- Coordinate deterministic tooling.
- Trigger AI agents only when required.
- Track retry limits.
- Detect terminal failures.
- Publish progress updates to Redis Pub/Sub.
- Resume interrupted migrations.

Redis remains the single source of shared migration state.

Design Principles

- Deterministic
- Stateless
- Easy to debug
- Framework independent
- Fully testable

Reason for Custom Implementation

HIPForge follows a deterministic workflow.

A custom implementation provides:

- Complete control
- No framework lock-in
- Easier debugging
- Lower maintenance
- Better explainability during demonstrations

## Redis

Purpose:

Shared memory and task broker.

Stores:

- Job execution queue
- Migration status
- Compiler logs
- Agent outputs
- Retry counter
- Migration Journal
- Workspace metadata

Redis is not responsible for active workflow_engine. It serves as the queue broker and the shared memory store.

---

## Workspace

Purpose:

Persistent project storage.

Contains:

- Uploaded CUDA files
- Generated HIP files
- Temporary patches
- Reports
- Compiler logs

The workspace is the canonical location for source files.

---

## Semantic Compatibility Analyzer (SCA)

Purpose

The Semantic Compatibility Analyzer (SCA) is a deterministic inspection engine that analyzes translated HIP code before AI-assisted repair begins.

Unlike AI agents, the SCA never modifies code. Its purpose is to identify CUDA constructs that are known to compile successfully but may behave differently on AMD hardware.

Examples of detected migration risks include:

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

The analysis_agent generates a structured file:

```
migration_risks.json
```

This file becomes part of the Workflow Context and is available to every AI agent during the migration process.

The SCA reduces unnecessary AI reasoning by identifying known migration risks before any repair attempts begin.

## Compiler Pipeline

Components:

- hipify-clang
- hipcc

Responsibilities:

- Deterministic translation
- Compilation validation
- Error generation

The compiler is the source of truth.

---

## AI Agent Layer

HIPForge uses three specialized AI agents.

### Analysis Agent

Responsibilities

- Analyze compiler errors.
- Identify root causes.
- Produce structured repair plans.

Internal implementation:

analysis_agent.py

---

### Patch Agent

Responsibilities

- Modify only the affected portions of the code.
- Preserve working code.
- Generate targeted patches.

Internal implementation:

patch_agent.py

---

### Research Agent

Responsibilities

- Search official ROCm documentation.
- Search GitHub issues.
- Search migration guides.
- Produce new repair strategies after repeated failures.

Internal implementation:

research_agent.py

---

The AI agents never communicate directly.

All communication occurs through the Workflow Engine using Redis.

## Report Generator

Generates:

- Migration report
- Change summary
- Compiler results
- Confidence score
- Download package

---

Upload CUDA Project / Paste CUDA Code

↓

Workspace Creation

↓

hipify-clang

↓

Semantic Compatibility Analyzer (SCA)

↓

Generate migration_risks.json

↓

hipcc Compilation

↓

Compilation Successful?

├── YES → Generate Reports → Export Package

└── NO

↓

Analysis Agent

↓

Patch Agent

↓

Compilation

↓

Research Agent (if required)

↓

Migration Journal Update

↓

Retry

# Communication Flow

Choose Input Method
(Paste Code | Upload .cu | Upload .zip)

↓

Create Workspace

↓

hipify-clang

↓

Semantic Compatibility Analyzer (SCA)

↓

Generate migration_risks.json

↓

hipcc Compilation

↓

Compilation Successful?

├── YES
│
│   ↓
│
│ Generate Reports
│
│ ↓
│
│ Engineering Dashboard
│
│ ↓
│
│ Export Package
│
└── NO
    │
    ▼
Analysis Agent

↓

Patch Agent

↓

hipcc Compilation

↓

Compilation Successful?

├── YES → Reports

└── NO

↓

Research Agent (if required)

↓

Migration Journal Update

↓

Retry

---

# State Ownership

Frontend

Owns:

UI state only.

Backend

Owns:

Execution lifecycle.

Workspace

Owns:

Files.

Redis

Owns:

Shared migration state.

Compiler

Owns:

Validation.

Agents

Own:

Reasoning only.

---

# Design Principles

The architecture follows these principles.

## Loose Coupling

Every subsystem can evolve independently.

---

## Single Responsibility

Every subsystem owns one responsibility.

---

## Fail Fast

Compile early.

Detect problems immediately.

---

## Deterministic First

Always attempt deterministic migration before AI.

---

## Evidence Driven

Every AI decision must be based on compiler evidence.

---

## Semantic Safety

HIPForge verifies semantic migration risks before AI-assisted repair begins.

Known CUDA constructs that may behave differently on AMD hardware are identified early, reducing the likelihood of producing code that compiles successfully but behaves incorrectly at runtime.

## Explainability

Every AI modification must be documented.

---

# Error Recovery

Errors are handled in layers.

Layer 1

Compiler retry.

Layer 2

Analysis Agent + Patch Agent.

Layer 3

Research Agent.

Layer 4

Maximum retry reached.

↓

Generate failure report.

No infinite loops are allowed.

---

# Scalability

HIPForge utilizes a queue-based asynchronous Migration Worker architecture using Redis. 

- **Concurrency**: Multiple concurrent migrations are supported by scaling worker processes.
- **Worker Isolation**: Web requests are immediately accepted by the FastAPI backend, while actual compilation and agent tasks are offloaded to workers, keeping the UI responsive.
- **GPU Pinning**: Parallel workers can be pinned to specific AMD GPUs using environment variables (`HIP_VISIBLE_DEVICES`).
- **Sandbox Containerization**: Future enterprise deployments will execute compile steps within hardened sandboxes like gVisor or Kata Containers for multi-tenant safety.

---

# Responsibilities

This document defines the overall system architecture.

---

# Non-Responsibilities

This document does not define:

- Redis keys
- REST APIs
- Dockerfiles
- Security rules
- Prompt templates

---

# Dependencies

- `00_SYSTEM_SPECIFICATION.md`
- `01_PRODUCT_VISION.md`

---

# Used By

- `03_PROJECT_STRUCTURE.md`
- `06_WORKSPACE_ARCHITECTURE.md`
- `07_WORKFLOW_ENGINE.md`
- `08_REDIS_ARCHITECTURE.md`
- `13_BACKEND.md`
- `14_FRONTEND.md`
- `09_AI_AGENTS.md`
- `15_DOCKER_SETUP.md`
- `16_API_SPECIFICATION.md`
- `19_SECURITY.md`

---

# Acceptance Criteria

✓ Every subsystem is identified.

✓ Responsibilities are clearly separated.

✓ Runtime workflow is documented.

✓ Component communication is defined.

✓ Future scalability is considered.

---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.