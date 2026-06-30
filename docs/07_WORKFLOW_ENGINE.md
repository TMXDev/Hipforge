# 07_WORKFLOW_ENGINE.md

Version: 1.0

Status: Pending

---

# Purpose

This document defines the internal behavior of the HIPForge Workflow Engine.

The Workflow Engine is responsible for coordinating every migration by executing a deterministic sequence of states. It runs asynchronously within the standalone **Migration Worker** process (`backend/app/workers/migration_worker.py`), consuming migration tasks from a Redis queue.

It acts as the central controller of the migration lifecycle.

---

# Goals

The Workflow Engine must:

- Execute states deterministically.
- Never skip validation.
- Keep AI usage minimal.
- Handle failures safely.
- Publish progress updates.
- Support configurable retry budgets.
- Be easy to debug and test.

---

# Scope

This document defines:

- Workflow states
- State transitions
- Retry logic
- Failure handling
- Completion conditions

This document does NOT define:

- Redis schema
- API endpoints
- Prompt engineering
- Compiler implementation

---

# Workflow Context

The Workflow Engine creates a single Workflow Context object at the beginning of every migration.

The Workflow Context contains all runtime information required during workflow execution.

Example contents include:

- Migration ID
- Workspace path
- Current workflow state
- Retry budget
- Current attempt
- Artifact locations
- Compiler status
- Redis connection
- Progress information

The Workflow Context exists only during the migration execution.

Each workflow state receives the same Workflow Context, updates it as necessary, and passes it to the next state.

Redis remains the persistent shared state, while the Workflow Context acts as the temporary in-memory working state.

This design minimizes unnecessary Redis reads and simplifies testing, debugging, and future maintenance.
---

# Workflow States

The engine contains the following states.

```
INITIALIZE

↓

UPLOAD

↓

HIPIFY

↓

COMPILE

↓

SUCCESS?
```

If successful

```
REPORT

↓

EXPORT

↓

COMPLETE
```

If compilation fails

```
ANALYZE

↓

PATCH

↓

COMPILE
```

If compilation fails again

```
RESEARCH

↓

UPDATE JOURNAL

↓

PATCH

↓

COMPILE
```

until:

- Success

or

- Retry Budget Exhausted

---

# State Definitions

## INITIALIZE

Responsibilities

- Create Migration Workspace.
- Generate Migration ID.
- Initialize Redis.
- Initialize Migration Journal.

Next State

UPLOAD

---

## UPLOAD

Responsibilities

- Save uploaded project.
- Validate files.
- Prepare workspace.

Next State

HIPIFY

---

## HIPIFY

Responsibilities

Run

```
hipify-clang
```

Save generated HIP code.

Next State

COMPILE

---

## COMPILE

Responsibilities

Run

```
hipcc
```

Collect:

- exit code
- stdout
- stderr

Decision

If compile succeeds

↓

REPORT

Otherwise

↓

ANALYZE

---

## ANALYZE

Responsibilities

Launch Analysis Agent.

Input

- source code
- compiler logs
- Migration Journal

Output

Repair Plan

Next

PATCH

---

## PATCH

Responsibilities

Launch Patch Agent.

Input

- repair plan
- source code

Output

Modified HIP source

Increment

Attempt Counter

Next

COMPILE

---

## RESEARCH

Responsibilities

Launch Research Agent.

Search:

- ROCm Docs
- HIP Docs
- AMD Examples
- GitHub

Generate

Research Summary

Next

UPDATE JOURNAL

---

## UPDATE_JOURNAL

Responsibilities

Append:

- compiler errors
- analysis
- patch summary
- research findings
- timestamps

Next

PATCH

---

## REPORT

Responsibilities

Generate:

- Migration Report
- Artifact Summary
- Statistics

Next

EXPORT

---

## EXPORT

Responsibilities

Package

```
HIPForge_Migration.zip
```

Next

COMPLETE

---

## COMPLETE

Responsibilities

Notify frontend.

Mark migration complete.

Close Workflow.

---

# Retry Logic

The retry budget is configurable.

Default

```
5
```

Minimum

```
1
```

Maximum

```
10
```

The Workflow Engine increments the attempt counter after every Patch state.

If

```
attempts >= retry_budget
```

↓

Terminate workflow.

↓

Generate failure report.

---

# State Transition Table

| Current | Success | Failure |
|----------|----------|----------|
| Initialize | Upload | Abort |
| Upload | Hipify | Abort |
| Hipify | Compile | Abort |
| Compile | Report | Analyze |
| Analyze | Patch | Abort |
| Patch | Compile | Abort |
| Research | Update Journal | Abort |
| Update Journal | Patch | Abort |
| Report | Export | Abort |
| Export | Complete | Abort |

---

# Failure Handling

Possible failures

- Invalid upload
- hipify crash
- Compiler crash
- AI timeout
- Search failure
- Retry exhaustion

Every failure produces:

- Log
- Journal Entry
- User Notification
- Report Entry

---

# Progress Events

The Workflow Engine emits events.

Examples

```
Migration Initialized

Workspace Created

Running hipify

Compiling

Compilation Failed

Running Analysis Agent

Applying Patch

Searching Documentation

Generating Report

Migration Complete
```

These events are streamed to the frontend.

---

# Design Principles

The Workflow Engine must always be:

Deterministic

Observable

Recoverable

Testable

Framework Independent

---

# Responsibilities

Owns workflow execution.

Owns state transitions.

Owns retry management.

Owns lifecycle coordination.

---

# Non-Responsibilities

Does NOT:

Store business data.

Modify Redis directly.

Generate AI responses.

Compile code.

Render UI.

---

# Dependencies

- `06_WORKSPACE_ARCHITECTURE.md`
- `08_REDIS_ARCHITECTURE.md`
- `09_AI_AGENTS.md`
- `10_COMPILATION_PIPELINE.md`
- `24_SCALABILITY.md`
- `26_JOB_LIFECYCLE.md`

---

# Used By

- `13_BACKEND.md` (via queue injection)
- `15_DOCKER_SETUP.md` (via container service definitions)
- `24_SCALABILITY.md` (defining worker execution)

---

# Acceptance Criteria

✓ Every state is defined.

✓ State transitions are deterministic.

✓ Retry logic is documented.

✓ Failure handling is defined.

✓ Progress events are emitted via Redis Pub/Sub.

✓ Workflow completion is deterministic.

---

# Execution Context

In the scaled worker architecture, the state machine is instantiated per task popped from the queue. Each state handles execution locally and persists shared state in Redis, maintaining horizontal scalability.

---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.