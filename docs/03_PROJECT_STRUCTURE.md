# 03_PROJECT_STRUCTURE.md

Version: 1.0

Status: Pending

---

# Purpose

This document defines the official repository structure of HIPForge.

It establishes where every component of the system belongs, how modules are organized, naming conventions, and engineering standards.

Every contributor and AI coding agent must follow this structure.

No new top-level directories should be created without updating this document.

---

# Goals

The project structure should:

- Keep the repository organized.
- Encourage modular development.
- Make debugging easier.
- Prevent duplicated code.
- Support future scaling.
- Be intuitive for both humans and AI coding agents.

---

# Scope

This document defines:

- Repository layout
- Folder responsibilities
- Naming conventions
- Code organization
- Engineering standards

It does NOT define:

- APIs
- Docker configuration
- Redis schema
- AI prompts
- Business logic

---

# Repository Structure

```
HIPForge/

├── backend/
│
├── frontend/
│
├── docker/
│
├── workspace/
│
├── tests/
│
├── docs/
│
├── prompts/
│
├── scripts/
│
├── .env.example
│
├── .gitignore
│
├── docker-compose.yml
│
├── README.md
│
└── LICENSE
```

---

# Backend Structure

```
backend/

├── app/
│   ├── api/
│   ├── workflow_engine/
│   ├── workers/
│   ├── compiler/
│   ├── agents/
│   ├── redis/
│   ├── workspace/
│   ├── artifacts/
│   ├── websocket/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   ├── utils/
│   ├── config/
│   └── main.py
│
├── requirements.txt
└── Dockerfile
```

---

## app/

Application initialization.

Responsibilities:

- FastAPI startup
- dependency injection
- lifecycle events

---

## api/

Contains every REST endpoint.

Example:

```
api/

migration.py

status.py

download.py

health.py
```

Business logic is NOT allowed here.

Endpoints should only validate requests and call services.

---

## workflow_engine/

Contains the custom workflow engine state machine logic.

Example

```
state_machine.py

transitions.py

context.py
```

Only state machine and state definition logic belongs here.

---

## workers/

Contains background execution worker scripts.

Example

```
migration_worker.py
```

Only background runner and job subscription loops belong here.

---

## compiler/

Contains deterministic compiler tools.

Example

```
hipify_runner.py

hipcc_runner.py

error_parser.py
```

This folder owns all compiler interaction.

---

## agents/

Contains AI agents.

Example

```
analysis_agent.py

patch_agent.py

research_agent.py

base_agent.py
```

Each file represents one specialized AI agent.

---

## redis/

Contains Redis integration.

Example

```
client.py

keys.py
```

Only Redis-related logic belongs here.

---

## workspace/

Handles local project files.

Example

```
manager.py

cleanup.py

storage.py
```

---

## artifacts/

Contains every artifact generated during the migration process.

Example

analysis/

compiler_logs/

patches/

search_results/

exports/

The artifact directory preserves the complete migration history for debugging and report generation.
```

---

## websocket/

Handles live frontend communication.

Example

```
manager.py

stream.py
```

---

## models/

Internal Python models.

---

## schemas/

Pydantic request and response schemas.

---

## services/

Reusable business logic.

Services connect multiple components together.

---

## utils/

Pure helper utilities.

Utility files must never contain business logic.

---

## config/

Application configuration.

Environment variables.

Feature flags.

Constants.

---

# Frontend Structure

```
frontend/

├── app/
├── components/
├── hooks/
├── services/
├── lib/
├── types/
├── styles/
├── public/
├── package.json
├── Dockerfile
└── next.config.ts
```

---

## app/

Next.js routing.

Pages.

Layouts.

Navigation.

---

## components/

Reusable UI components.

Example

```
UploadCard

Timeline

CompilerLog

CodeViewer

ProgressBar

StatusBadge

Navbar

Footer
```

---

## hooks/

React hooks.

---

## services/

Frontend API client.

WebSocket client.

---

## lib/

Utility functions.

Formatting.

Validation.

---

## types/

Shared TypeScript interfaces.

---

## styles/

Global styling.

---

## public/

Images.

Icons.

Logos.

Fonts.

---

# Workspace Structure

```
workspace/

migration-id/

├── input/
│
├── generated/
│
├── logs/
│
├── patches/
│
├── artifacts/
│
├── reports/
│
└── final/

download package
```

Each migration receives its own isolated workspace.

---

# Docker Folder

Contains:

```
docker/

backend/

frontend/

redis/
```

Container-specific configuration only.

---

# Tests

```
tests/

backend/

frontend/

integration/

fixtures/
```

Tests mirror the project structure.

---

# Documentation

```
docs/

00...

01...

02...
```

Architecture documents only.

No prompts.

---

# Prompts

```
prompts/

backend/

frontend/

docker/

redis/

agents/

testing/
```

Contains implementation prompts for Antigravity AI.

---

# Scripts

Contains helper scripts.

Example

```
start.sh

reset.sh

seed.sh

clean.sh
```

Scripts must never contain business logic.

---

# Naming Conventions

Folders

lowercase

snake_case

Python Files

snake_case.py

Classes

PascalCase

Functions

snake_case()

Constants

UPPER_CASE

React Components

PascalCase.tsx

Hooks

useSomething.ts

---

# Engineering Standards

Every module must have one responsibility.

No circular imports.

No duplicated logic.

No business logic inside API endpoints.

No direct Redis access from the frontend.

No hardcoded paths.

Every public function must include documentation.

Type hints are required.

---

# File Size Guidelines

Target maximum file size:

300–400 lines

Target maximum function size:

40 lines

If a file grows beyond this, consider refactoring.

---

# Dependency Rules

Frontend cannot directly communicate with Redis.

Frontend communicates only with FastAPI.

AI agents never communicate directly.

All shared information passes through Redis.

The Workflow Engine coordinates execution.

The Compiler validates every code modification.

---

# Responsibilities

This document defines the physical organization of the HIPForge repository.

---

# Non-Responsibilities

This document does not define runtime behavior or implementation details.

---

# Dependencies

- 00_SYSTEM_SPECIFICATION.md
- 01_PRODUCT_VISION.md
- 02_SYSTEM_ARCHITECTURE.md

---

# Used By

- Every implementation document
- Every implementation prompt

---

# Acceptance Criteria

✓ Repository layout finalized.

✓ Backend structure finalized.

✓ Frontend structure finalized.

✓ Naming conventions defined.

✓ Engineering standards documented.

✓ Folder responsibilities assigned.

---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.