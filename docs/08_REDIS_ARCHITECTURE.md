# 08_REDIS_ARCHITECTURE.md

Version: 1.0

Status: Pending

---

# Purpose

This document defines how Redis is used inside HIPForge.

Redis acts as the shared memory and communication layer between every component of the system.

It stores temporary migration state, enables communication between services, and streams real-time progress updates.

---

# Goals

Redis must:

- Broker asynchronous task queues.
- Store temporary migration state.
- Enable agent communication.
- Publish live frontend updates.
- Track migration progress.
- Preserve temporary runtime data.

Redis is not a permanent database.

---

# Scope

This document defines:

- Redis key structure.
- Pub/Sub channels.
- Runtime state.
- Communication rules.

It does NOT define:

- Backend logic.
- API endpoints.
- AI prompts.
- Workspace files.

---

# Redis Philosophy

Redis is the shared memory of HIPForge.

Every component communicates through Redis.

Components never communicate directly.

Example

Workflow Engine

↓

Redis

↓

Analysis Agent

↓

Redis

↓

Patch Agent

↓

Redis

↓

Frontend

---

# Key Naming Convention

Every migration uses its own namespace.

Example

```
migration:<migration_id>:status
```

This prevents collisions between concurrent migrations.

---

# Redis Keys

## Pending Job Queue

Key:
`hipforge:queue:pending`

Type:
Redis List

Description:
Holds migration job requests pushed by the FastAPI backend using `LPUSH`. The workers consume tasks using blocking pop (`BRPOP`).

Example entry:
```json
{
  "migration_id": "migration_20260630_171000_abcd",
  "workspace_path": "/app/workspace/migration_20260630_171000_abcd"
}
```

---

## Active Job Queue

Key:
`hipforge:queue:active`

Type:
Redis List

Description:
Contains the migration IDs currently being processed by workers. Jobs are added here when popped from pending and removed when terminal states are reached.

---

## Status

Key:
`migration:{id}:status`

Type:
String

Example:
`COMPILING`

Possible values:
- `QUEUED`
- `PREPARING`
- `HIPIFY`
- `SCA`
- `COMPILING`
- `ANALYZING`
- `PATCHING`
- `RESEARCHING`
- `GENERATING_REPORT`
- `COMPLETED`
- `FAILED`

---

## Current Attempt

Key

```
migration:{id}:attempt
```

Type

Integer

Example

```
2
```

---

## Retry Budget

Key

```
migration:{id}:retry_budget
```

Type

Integer

Example

```
5
```

---

## Compiler Logs

Key

```
migration:{id}:compiler_log
```

Type

String

Stores

Latest hipcc output.

---

## Analysis Output

Key

```
migration:{id}:analysis
```

Type

JSON String

Contains

- Root cause
- Repair strategy
- Confidence score

---

## Patch Output

Key

```
migration:{id}:patch
```

Type

JSON String

Contains

- Modified files
- Patch summary
- Timestamp

---

## Research Output

Key

```
migration:{id}:research
```

Type

JSON String

Contains

- Search queries
- Sources
- Findings
- Suggested fixes

---

## Migration Journal

Key

```
migration:{id}:journal
```

Type

Redis List

Each list item represents one migration attempt.

Example entry

```json
{
  "attempt":2,
  "compile":"failed",
  "analysis":"...",
  "patch":"...",
  "research":"..."
}
```

The journal grows throughout the migration session.

---

## Metadata

Key

```
migration:{id}:metadata
```

Type

Redis Hash

Fields

- project_name
- created_at
- current_state
- workspace_path
- compiler
- target_architecture

---

# Pub/Sub Channels

Redis publishes live events.

Channel

```
migration:{id}:events
```

Example messages

```
Workspace Created

Running hipify

Compiling

Compilation Failed

Analysis Started

Patch Generated

Research Started

Migration Completed
```

---

Compiler Logs

Channel

```
migration:{id}:compiler
```

Streams compiler output.

---

Agent Activity

Channel

```
migration:{id}:agents
```

Streams

- Analysis Agent
- Patch Agent
- Research Agent

activity.

---

Frontend Updates

The frontend subscribes to

```
migration:{id}:events
```

and updates the interface in real time.

No polling is required.

---

# Lifetime

Redis data exists only during the migration session.

After the migration completes:

- Report is generated.
- Artifacts are saved.
- Redis keys are deleted.

Persistent information belongs in the workspace, not Redis.

---

# Responsibilities

Redis is responsible for:

- Task queuing and job distribution (broker).
- Temporary shared memory state.
- Live progress broadcast.
- Progress tracking.

---

# Non-Responsibilities

Redis does NOT:

- Store user files.
- Store reports permanently.
- Replace the workspace.
- Coordinate workflow execution (this belongs exclusively to the Workflow Engine running inside the Migration Worker).
- Replace the Workflow Context.

---

# Design Principles

Redis should remain:

- Fast.
- Lightweight.
- Disposable.
- Deterministic.

---

# Dependencies

- `06_WORKSPACE_ARCHITECTURE.md`
- `07_WORKFLOW_ENGINE.md`

---

# Used By

- `07_WORKFLOW_ENGINE.md`
- `13_BACKEND.md`
- `15_DOCKER_SETUP.md`
- `24_SCALABILITY.md`

---

# Acceptance Criteria

✓ Every migration has isolated Redis keys.

✓ Live events are streamed.

✓ Agent communication is indirect.

✓ Temporary state is defined.

✓ Cleanup policy is documented.

---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.