# 13_BACKEND.md

Version: 1.0

Status: Pending

---

# Purpose

This document defines the backend architecture of HIPForge.

The backend is responsible for exposing REST APIs, managing workspace environments, running WebSockets for event communication, pushing migration jobs to the Redis task queue, and serving final report packages.

The backend API layer is implemented using FastAPI.

---

# Goals

The backend must be:

- Modular
- Testable
- Maintainable
- Asynchronous
- Framework-independent
- Easy to extend

---

# Guiding Principles

The backend should follow a layered architecture.

Each layer has one responsibility.

Business logic must never be mixed with HTTP routes.

Routes should be as thin as possible.

---

# High-Level Architecture

```
Client

↓

API Routes

↓

Application Services

↓

Workflow Engine

↓

Infrastructure

↓

Redis
Workspace
Fireworks
Compiler
Filesystem
```

Every request flows downward.

Dependencies should never point upward.

---

# Folder Structure

```
backend/

app/

├── api/
│
├── core/
│
├── models/
│
├── schemas/
│
├── services/
│
├── workflow_engine/
│
├── workers/
│
├── agents/
│
├── compiler/
│
├── workspace/
│
├── reports/
│
├── infrastructure/
│
├── utils/
│
├── config.py
│
└── main.py
```

---

# Folder Responsibilities

## api/

Contains FastAPI endpoints only.

No business logic.

Example

```
upload.py

migration.py

status.py

websocket.py
```

---

## core/

Shared backend utilities.

Examples

- Dependency Injection
- Startup logic
- Logging
- Exception handling

---

## models/

Internal Python models.

Example

```
Migration

WorkflowContext

CompilerResult
```

---

## schemas/

Pydantic request/response schemas.

Every API request is validated here.

---

## services/

Business logic.

Examples

MigrationService

CompilerService

WorkspaceService

ReportService

---

## workflow_engine/

Contains the custom Workflow Engine state machine. Decoupled from FastAPI to run in any Python process.

---

## workers/

Contains background workers (`migration_worker.py`) that consume task lists from Redis.

---

## agents/

Contains wrappers around AI providers.

Examples

AnalysisAgent

PatchAgent

ResearchAgent

Every agent exposes one public method.

```
execute(...)
```

---

## compiler/

Everything related to:

hipify

hipcc

compiler logs

---

## workspace/

Responsible for:

- creating workspaces
- file management
- exports
- cleanup

---

## reports/

Generates:

Markdown reports

JSON reports

future PDF reports

---

## infrastructure/

External integrations.

Examples

Redis

Fireworks

Environment variables

Storage

---

## utils/

Pure helper functions.

Never contain business logic.

---

# API Layer

Routes should only:

- validate input
- call services
- return responses

Routes should NEVER:

- call Redis directly
- call Fireworks
- compile code
- manipulate files

---

# Service Layer

Services coordinate business logic.

Example

```
MigrationService

↓

Create Workspace

↓

Start Workflow

↓

Return Migration ID
```

Services may communicate with multiple modules.

---

# Workflow Engine

The Workflow Engine remains the heart of HIPForge.

Only the Workflow Engine can:

- advance workflow state
- consume retry budget
- invoke AI agents
- invoke compiler

---

# AI Agent Layer

Agents are isolated.

Every agent exposes

```
execute(context)
```

Example

```
analysis_agent.execute(context)

patch_agent.execute(context)

research_agent.execute(context)
```

The Workflow Engine decides when they run.

---

# Dependency Injection

Every shared dependency should be injected.

Examples

Redis Client

Fireworks Client

Configuration

Logger

This makes testing significantly easier.

---

# Configuration

All configuration is loaded from environment variables.

Examples

```
REDIS_URL

FIREWORKS_API_KEY

WORKSPACE_PATH

DEFAULT_RETRY_BUDGET

MAX_UPLOAD_SIZE

LOG_LEVEL
```

No secrets should exist inside the source code.

---

# Background Execution

All migrations are treated as asynchronous jobs. 

1. **API Job Submission**: The client submits a migration job via POST request. FastAPI creates the directory workspace, pushes the job packet to `hipforge:queue:pending` in Redis, and immediately returns a `202 Accepted` response with the `migration_id`.
2. **Worker Dequeue**: A standalone Migration Worker process (`migration_worker.py`) listens to Redis, pops the task, and executes the state machine (`workflow_engine/`) to run compiler tools and agents.
3. **Event Relay**: The worker broadcasts progress messages over Redis Pub/Sub (`migration:{id}:events`). FastAPI WebSocket endpoints subscribe to this channel and stream these updates to the Frontend in real-time.

---

# Error Handling

Every layer handles only its own errors.

Examples

API

↓

400 Request

Workflow

↓

Migration Failed

Compiler

↓

Compilation Error

Infrastructure

↓

Redis Unavailable

No raw stack traces should be exposed to users.

---

# Logging

Every major operation generates structured logs.

Examples

Migration Started

Workspace Created

Compiler Started

Compiler Failed

Patch Generated

Research Started

Migration Completed

Logs should include:

- migration_id
- timestamp
- component
- severity

---

# Security

The backend must:

- Validate uploads.
- Limit upload size.
- Sanitize filenames.
- Prevent path traversal.
- Restrict workspace access.
- Validate JSON responses from AI.
- Never expose API keys.

---

# Design Principles

The backend should always be:

- Predictable
- Observable
- Testable
- Modular
- Recoverable

---

# Responsibilities

The backend is responsible for:

- REST API endpoints.
- WebSocket streaming and event relay.
- Workspace directory initialization and packaging.
- Decoupled business services (workspace management, report retrieval).
- Job enqueueing to Redis.

---

# Non-Responsibilities

The backend does NOT:

- Render UI.
- Run compilation or translation in-process (handled by Migration Workers).
- Manage permanent database storage.
- Orchestrate active workflow states (handled by the Workflow Engine running inside the Migration Worker).

---

# Dependencies

- `06_WORKSPACE_ARCHITECTURE.md`
- `07_WORKFLOW_ENGINE.md`
- `08_REDIS_ARCHITECTURE.md`
- `09_AI_AGENTS.md`
- `10_COMPILATION_PIPELINE.md`
- `12_MIGRATION_JOURNAL.md`
- `24_SCALABILITY.md`
- `26_JOB_LIFECYCLE.md`

---

# Used By

- `14_FRONTEND.md`
- `15_DOCKER_SETUP.md`
- `16_API_SPECIFICATION.md`
- `20_TESTING.md`

---

# Acceptance Criteria

✓ Layered architecture defined.

✓ Folder responsibilities defined.

✓ Services isolated.

✓ Workflow isolated.

✓ Dependency Injection used.

✓ Environment configuration defined.

✓ Security requirements documented.

✓ Background execution supported.

---

# Startup Notes

Future versions may introduce:

- Worker queues
- Distributed execution
- Multiple AI providers
- User authentication
- SaaS billing

These additions should integrate through the service layer without requiring architectural changes.

---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.