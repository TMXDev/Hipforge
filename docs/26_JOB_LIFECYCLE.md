# 26_JOB_LIFECYCLE.md

Version: 1.0

Status: Pending

---

# Purpose

This document defines the formal job lifecycle and state machine states of a HIPForge migration task. It specifies the exact state transitions executed by the `migration_worker.py` process, defining entry/exit criteria and the event payload structures published to Redis for live progress visualization on the Next.js Frontend.

---

# State Model Overview

The migration process is modeled as a linear pipeline that can transition into iterative repair loops upon compilation failure.

```
 [ QUEUED ] ──► [ PREPARING ] ──► [ HIPIFY ] ──► [ SCA ] ──► [ COMPILING ]
                                                                 │
                                ┌────────────────────────────────┴───┐
                                ▼ (Compilation Fails)                ▼ (Succeeds)
                         [ ANALYZING ]                        [ GENERATING_REPORT ]
                                │                                    │
                                ▼                                    ▼
                          [ PATCHING ]                         [ COMPLETED ] or
                                │                                  [ FAILED ]
                                ▼
                       (Budget Remaining?)
                       ├── YES ──► [ COMPILING ]
                       └── NO  ──► [ RESEARCHING ] ──► [ COMPILING ] (Final Try)
```

---

# Detailed State Definitions

### 1. `QUEUED`
* **Description**: The job is accepted by FastAPI, a unique `migration_id` is assigned, metadata is written to Redis, and the job is pushed to the Redis list `hipforge:queue:pending`.
* **Entry Criteria**: User uploads code or pastes source via frontend.
* **Exit Criteria**: A `migration_worker.py` process pops the job from the queue.

### 2. `PREPARING`
* **Description**: The worker creates the isolated workspace directories (`input/`, `generated/`, `patches/`, `logs/`, `artifacts/`, `reports/`) and writes the uploaded source archive or files.
* **Entry Criteria**: Job popped from Redis list.
* **Exit Criteria**: Workspace directories created, input files written, and `metadata.json` initialized.

### 3. `HIPIFY`
* **Description**: Runs deterministic source-to-source CUDA-to-HIP translation via `hipify-clang` on all files.
* **Entry Criteria**: Workspace preparation completes.
* **Exit Criteria**: Translates files into the `generated/` directory.

### 4. `SCA`
* **Description**: Runs the Semantic Compatibility Analyzer (SCA) to scan translated HIP source code for hidden architectural differences (e.g. `warpSize` warp assumptions, texture references).
* **Entry Criteria**: `hipify-clang` execution terminates.
* **Exit Criteria**: Writes `migration_risks.json` to the workspace.

### 5. `COMPILING`
* **Description**: Runs the HIP compiler (`hipcc`) to validate syntax and compile translated files.
* **Entry Criteria**: SCA finishes or a new patch is applied.
* **Exit Criteria**: Compilation succeeds (transitions to `GENERATING_REPORT`) or fails (transitions to `ANALYZING`).

### 6. `ANALYZING`
* **Description**: Triggered upon compilation failure. The Analysis Agent reads compiler error diagnostics, source code context, and the Migration Journal to pinpoint the root cause and write a structured repair strategy.
* **Entry Criteria**: `hipcc` exits with a non-zero code.
* **Exit Criteria**: Analysis Agent returns a structured repair plan JSON.

### 7. `PATCHING`
* **Description**: The Patch Agent takes the repair plan and source files, generates a localized patch, and writes it to the source code.
* **Entry Criteria**: Repair plan JSON is written to Redis.
* **Exit Criteria**: Source files are modified, and the patch is logged in the workspace `patches/` directory.

### 8. `RESEARCHING`
* **Description**: Triggered if the patch attempts fail to resolve compilation errors and the retry budget is depleted. The Research Agent queries documentation and knowledge bases via web tools to retrieve correct AMD equivalent APIs.
* **Entry Criteria**: Iteration count reaches retry limit.
* **Exit Criteria**: New migration mappings or code patterns are loaded into the agent context for a final repair attempt.

### 9. `GENERATING_REPORT`
* **Description**: Compiles all patch diffs, compiler log statistics, migration journal entries, and compatibility risk summaries, writing them into standard reports (`migration_report.md`, `compatibility_report.md`).
* **Entry Criteria**: Compilation success or exhaustion of retry/research budgets.
* **Exit Criteria**: Reports are generated in the `reports/` directory, and workspace files are zipped into `HIPForge_Migration.zip`.

### 10. `COMPLETED` / `FAILED`
* **Description**: The terminal states of the job lifecycle. The workspace is archived, client is notified, and Redis keys are scheduled for deletion.
* **Entry Criteria**: Zipped export package is written to the `exports/` folder.
* **Exit Criteria**: None (terminal).

---

# Transition Rules & State Key

The job state is persisted in Redis under the key `migration:{id}:status` (defined in `08_REDIS_ARCHITECTURE.md`).

| Source State | Trigger / Event | Target State | Condition |
| :--- | :--- | :--- | :--- |
| `QUEUED` | Job Dequeued | `PREPARING` | Worker pops job from queue |
| `PREPARING` | Directory creation OK | `HIPIFY` | Workspace is ready |
| `HIPIFY` | Translation complete | `SCA` | Code is hipified |
| `SCA` | Risk analysis written | `COMPILING` | `migration_risks.json` saved |
| `COMPILING` | Compilation Success | `GENERATING_REPORT` | `hipcc` exit code == 0 |
| `COMPILING` | Compilation Failure | `ANALYZING` | `hipcc` exit code != 0 |
| `ANALYZING` | Repair plan generated | `PATCHING` | Plan JSON written |
| `PATCHING` | Code modified | `COMPILING` | Patch successfully written; increment attempt count |
| `COMPILING` | Compile Fails & Limit Reached | `RESEARCHING` | `current_attempt` >= `retry_budget` |
| `RESEARCHING` | Reference code retrieved | `COMPILING` | Last-resort patch applied |
| `COMPILING` | Final Last-resort fails | `GENERATING_REPORT` | Budget fully depleted |
| `GENERATING_REPORT` | Zipping completes | `COMPLETED` | Compile was successful |
| `GENERATING_REPORT` | Zipping completes | `FAILED` | Compile remained unresolved |

---

# Event Payload Structure

On every state transition, the worker must publish a JSON status event to the Redis Pub/Sub channel `migration:{id}:events`:

```json
{
  "migration_id": "migration_20260630_171000_abcd",
  "timestamp": "2026-06-30T17:15:00Z",
  "state": "COMPILING",
  "details": "Running hipcc compilation (Attempt 2 of 5)...",
  "progress_percentage": 50
}
```

This payload is consumed by FastAPI and streamed directly to the frontend timeline component.

---

# Dependencies

- `02_SYSTEM_ARCHITECTURE.md`
- `07_WORKFLOW_ENGINE.md`
- `08_REDIS_ARCHITECTURE.md`
- `24_SCALABILITY.md`

---

# Used By

- `14_FRONTEND.md` (Timeline UI)
- `13_BACKEND.md` (WebSockets endpoint)
- `07_WORKFLOW_ENGINE.md` (State transitions)

---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.