# .agent/IMPLEMENTATION_PROMPTS.md

> **Your vibe coding playbook.** Copy and paste each prompt exactly as written.
>
> Rules:
> - Complete the **Gate** at the end of each session before moving to the next.
> - Never skip a Gate. Never run two sessions at once.
> - Every prompt starts with a planning step. Do not skip it.
> - After each Gate passes: update `.agent/SESSION_STATE.json`, then commit.

---

# MANDATORY SESSION START BLOCK

> **Paste this at the very beginning of every new chat session**, before the specific prompt below.

```
Before doing anything else:

1. Read .agent/SESSION_STATE.json
2. Read .agent/AGENT_RULES.md
3. Read .agent/PROJECT_CONTEXT.md

Report back:
- Current session from .agent/SESSION_STATE.json
- Current mode (pre-hackathon or hackathon)
- Any blocked items
- What was completed in the last session

Then proceed with the session prompt I give you next.
```

---

# MANDATORY SESSION END BLOCK

> **Every session ends by updating .agent/SESSION_STATE.json.** This is not optional.

The AI must update the following fields in `.agent/SESSION_STATE.json` after every successful gate:

```json
{
  "last_updated": "<ISO timestamp>",
  "last_session": "<just completed session ID>",
  "phase": {
    "current_session": "<next session ID>",
    "status": "in_progress"
  },
  "sessions": {
    "<just completed session ID>": {
      "status": "completed",
      "gate_passed": true,
      "notes": "<any important decisions or findings>"
    }
  },
  "next_action": "<one sentence: what Session X.Y will do>"
}
```

Then produce this git commit message (the human will run it):

```
git add .
git commit -m "feat(session-X.Y): <what was built>

Gate: passed
Mode: pre-hackathon"
```

---

# PRE-HACKATHON MODE NOTICE

> The hackathon has not started. External APIs and cloud services are NOT available yet.

When implementing AI agents or compiler wrappers, read `.agent/MOCK_SERVICES.md` first.

| Service | Status | Environment Variable |
|---------|--------|---------------------|
| Fireworks AI | MOCKED | `USE_MOCK_AI=true` |
| hipify-clang | MOCKED | `USE_MOCK_COMPILER=true` |
| hipcc | MOCKED | `USE_MOCK_COMPILER=true` |
| Redis | REAL (Docker) | Always real |

All mocks must be swappable to real services by changing `.env` only — no code changes.

---

# HOW EVERY PROMPT WORKS

Each prompt below follows this structure:

1. **Read** — specific spec files for this session only
2. **Plan** — AI explains its approach before coding
3. **Implement** — code is written
4. **Allowed Files** — exact files the AI may touch
5. **Definition of Done** — checklist that must be fully satisfied
6. **STOP + UPDATE .agent/SESSION_STATE.json** — hard stop after state update

---

# PHASE 1 — Repository Scaffold

---

## Session 1.1 — Create Project Structure

```
Read .agent/PROJECT_CONTEXT.md and docs/03_PROJECT_STRUCTURE.md completely.

Before writing anything:
1. List all folders you will create.
2. List all empty files you will create.
3. Confirm your plan matches docs/03_PROJECT_STRUCTURE.md exactly.
Then execute.

Your task:
Create the entire HIPForge repository folder and file layout on disk exactly as described in docs/03_PROJECT_STRUCTURE.md. All files must be empty — no content, no imports, no logic.

Allowed Files:
Create only the folders and empty files listed in docs/03_PROJECT_STRUCTURE.md.
Do not create any file not listed there.
Do not modify any existing file.

Definition of Done:
[ ] Every folder from docs/03_PROJECT_STRUCTURE.md exists on disk.
[ ] Every file from docs/03_PROJECT_STRUCTURE.md exists on disk (empty).
[ ] No extra files or folders were created.
[ ] No file contains any content.

STOP.
Do not write any code.
Wait for the next implementation prompt.
```

**Gate**: Run `Get-ChildItem -Recurse | Select-Object FullName` and compare against `docs/03_PROJECT_STRUCTURE.md`. ✓ / ✗

---

# PHASE 2 — Infrastructure

---

## Session 2.1 — Backend Dockerfile

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/15_DOCKER_SETUP.md.

Before writing anything:
1. Identify the base image to use.
2. Identify the Python version and dependency install method.
3. Identify the correct entrypoint and exposed port.
Then implement.

Your task:
Write the Dockerfile for the FastAPI backend service.

Allowed Files:
- backend/Dockerfile
- backend/requirements.txt (create with placeholder dependencies if it does not exist)

Do not write any other file.

Definition of Done:
[ ] backend/Dockerfile exists and is complete.
[ ] Base image matches docs/15_DOCKER_SETUP.md.
[ ] requirements.txt is installed correctly.
[ ] Entrypoint, working directory, and port match the spec.
[ ] docker build -f backend/Dockerfile . completes with no errors.

STOP.
Do not write docker-compose.yml yet.
Wait for the next implementation prompt.
```

**Gate**: `docker build -f backend/Dockerfile .` completes with no errors. ✓ / ✗

---

## Session 2.2 — Frontend Dockerfile + docker-compose.yml

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/15_DOCKER_SETUP.md.

Before writing anything:
1. Identify the Node.js version and base image for the frontend.
2. List all four services docker-compose must define: backend, frontend, redis, migration-worker.
3. List all volume mounts and port mappings from the spec.
Then implement.

Your task:
Write the frontend Dockerfile and the complete docker-compose.yml.

Allowed Files:
- frontend/Dockerfile
- docker-compose.yml

Do not touch backend/Dockerfile.

Definition of Done:
[ ] frontend/Dockerfile exists and builds successfully.
[ ] docker-compose.yml defines: backend, frontend, redis, migration-worker.
[ ] Volume mounts match docs/15_DOCKER_SETUP.md.
[ ] Port mappings match docs/15_DOCKER_SETUP.md.
[ ] migration-worker service supports scale-out (no hardcoded replica count).
[ ] docker-compose up -d starts all services without errors.
[ ] docker-compose ps shows all services healthy.
[ ] redis-cli PING returns PONG.

STOP.
Do not implement any application code.
Wait for the next implementation prompt.
```

**Gate**: `docker-compose up -d` all healthy. `docker-compose exec redis redis-cli PING` → `PONG`. ✓ / ✗

---

## Session 2.3 — Environment Configuration

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/15_DOCKER_SETUP.md, and docs/04_TECHNOLOGY_DECISIONS.md.

Before writing anything:
1. List every environment variable referenced across docs/15_DOCKER_SETUP.md and docs/04_TECHNOLOGY_DECISIONS.md.
2. Group them by service: backend, worker, frontend, Redis, GPU.
Then implement.

Your task:
Write .env.example with every environment variable required by HIPForge.

Allowed Files:
- .env.example

Do not modify any other file.

Definition of Done:
[ ] .env.example exists.
[ ] Every variable referenced in docs/15_DOCKER_SETUP.md is present.
[ ] FIREWORKS_API_KEY is present.
[ ] Redis connection variables are present.
[ ] HIP_VISIBLE_DEVICES is present for GPU pinning.
[ ] Every variable has a comment above it explaining its purpose.
[ ] No secret values are hardcoded — only placeholder examples.

STOP.
Do not write any Python or TypeScript code.
Wait for the next implementation prompt.
```

**Gate**: `.env.example` is complete. Every variable is commented. No secrets are hardcoded. ✓ / ✗

---

# PHASE 3 — Backend Skeleton

---

## Session 3.1 — FastAPI App Entrypoint

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/13_BACKEND.md.

Before writing anything:
1. Identify the app title, description, and version from docs/13_BACKEND.md.
2. Identify the CORS configuration required.
3. List the router modules you will import (they may be empty for now).
Then implement.

Your task:
Write the FastAPI application entrypoint.

Allowed Files:
- backend/app/main.py
- backend/app/config/settings.py (environment variable loading only)
- backend/app/api/health.py (the /health route only)

Do not implement any other route or logic.

Definition of Done:
[ ] backend/app/main.py exists with the FastAPI app initialized.
[ ] App title, description, and version match docs/13_BACKEND.md.
[ ] CORS middleware is configured for the frontend origin.
[ ] GET /health returns {"status": "ok"} with HTTP 200.
[ ] uvicorn backend.app.main:app starts without errors.
[ ] No import errors in the console.

STOP.
Do not implement any other route.
Wait for the next implementation prompt.
```

**Gate**: `uvicorn backend.app.main:app --reload` starts. `GET /health` → `{"status": "ok"}` HTTP 200. ✓ / ✗

---

## Session 3.2 — All API Route Stubs

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/16_API_SPECIFICATION.md.

Before writing anything:
1. List every endpoint defined in docs/16_API_SPECIFICATION.md with its method and path.
2. Confirm you have accounted for all of them.
Then implement.

Your task:
Create all API route stubs. Every stub must return HTTP 501 Not Implemented.

Allowed Files:
- backend/app/api/migration.py
- backend/app/api/status.py
- backend/app/api/download.py
- backend/app/api/router.py (to register all routes)
- backend/app/main.py (include the router — import only, no logic change)

Do not implement any business logic. Do not write any service or model files yet.

Definition of Done:
[ ] Every endpoint from docs/16_API_SPECIFICATION.md exists as a stub.
[ ] Every stub returns HTTP 501 with body {"detail": "not implemented"}.
[ ] URL paths, HTTP methods, and parameter names exactly match docs/16_API_SPECIFICATION.md.
[ ] No 404 responses for any documented endpoint.
[ ] Backend starts cleanly with no errors.

STOP.
Do not implement any endpoint logic.
Wait for the next implementation prompt.
```

**Gate**: Every route in `docs/16_API_SPECIFICATION.md` returns 501. Zero 404s for documented routes. ✓ / ✗

---

## Session 3.3 — WebSocket Stub

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/16_API_SPECIFICATION.md.

Before writing anything:
1. Identify the exact WebSocket path from docs/16_API_SPECIFICATION.md.
2. Identify what the initial connection message should contain.
Then implement.

Your task:
Create the WebSocket endpoint stub.

Allowed Files:
- backend/app/websocket/manager.py
- backend/app/websocket/stream.py
- backend/app/api/migration.py (add the WebSocket route — append only)

Do not implement any Pub/Sub relay logic yet.

Definition of Done:
[ ] WebSocket endpoint exists at the path defined in docs/16_API_SPECIFICATION.md.
[ ] Connecting receives: {"type": "connected", "migration_id": "<id>"}.
[ ] Connection closes gracefully when the client disconnects.
[ ] Backend starts cleanly with no errors.

STOP.
Do not implement the Pub/Sub relay.
Wait for the next implementation prompt.
```

**Gate**: A WebSocket client connects and receives `{"type": "connected"}`. ✓ / ✗

---

# PHASE 4 — Redis Manager

---

## Session 4.1 — Redis Connection + Key Builders

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/08_REDIS_ARCHITECTURE.md completely.

Before writing anything:
1. List every Redis key template defined in docs/08_REDIS_ARCHITECTURE.md.
2. List every Pub/Sub channel template.
3. Confirm you will create a builder function for every single one.
Then implement.

Your task:
Implement the Redis connection pool and key builder module.

Allowed Files:
- backend/app/redis/client.py (connection pool)
- backend/app/redis/keys.py (key builder functions)

No other file may contain raw Redis key strings. All keys must come from keys.py.

Definition of Done:
[ ] backend/app/redis/client.py initializes a connection pool from REDIS_URL env variable.
[ ] backend/app/redis/keys.py has one function per key template in docs/08_REDIS_ARCHITECTURE.md.
[ ] Every function takes migration_id as a parameter and returns the full key string.
[ ] Key strings exactly match the patterns in docs/08_REDIS_ARCHITECTURE.md.
[ ] No raw key strings exist outside keys.py.
[ ] Import from this module works without errors.

STOP.
Do not implement queue or Pub/Sub operations yet.
Wait for the next implementation prompt.
```

**Gate**: `from backend.app.redis.keys import *` works. Every key in `docs/08_REDIS_ARCHITECTURE.md` has a builder. ✓ / ✗

---

## Session 4.2 — Queue Operations

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/08_REDIS_ARCHITECTURE.md.

Before writing anything:
1. Identify the four queue operations needed: enqueue, dequeue, mark_active, mark_done.
2. Identify which Redis commands each uses.
Then implement.

Your task:
Implement queue operations in the Redis Manager.

Allowed Files:
- backend/app/redis/manager.py

Use only key builder functions from backend/app/redis/keys.py. No raw key strings.

Definition of Done:
[ ] enqueue_job(migration_id, payload) pushes to the pending queue correctly.
[ ] dequeue_job(timeout) blocks and returns (migration_id, payload) or None on timeout.
[ ] mark_active(migration_id) records the job in the active queue.
[ ] mark_done(migration_id) removes the job from the active queue.
[ ] All four operations use key builders from keys.py exclusively.

STOP.
Do not implement Pub/Sub yet.
Wait for the next implementation prompt.
```

**Gate**: Manual test — enqueue a job, dequeue it, payload round-trips correctly. ✓ / ✗

---

## Session 4.3 — Pub/Sub Helpers

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/08_REDIS_ARCHITECTURE.md, and docs/26_JOB_LIFECYCLE.md.

Before writing anything:
1. Identify the Pub/Sub channel naming pattern from docs/08_REDIS_ARCHITECTURE.md.
2. Identify the event payload fields from docs/26_JOB_LIFECYCLE.md.
Then implement.

Your task:
Implement Pub/Sub publish and subscribe helpers.

Allowed Files:
- backend/app/redis/publisher.py
- backend/app/redis/subscriber.py

Definition of Done:
[ ] publish_event(migration_id, stage, status, message) publishes to the correct channel.
[ ] subscribe_to_migration(migration_id) returns an active subscriber for that channel.
[ ] Event payload includes: stage, status, message, timestamp (ISO 8601).
[ ] Channel name is built using keys.py — no raw channel strings.

STOP.
Do not write tests yet.
Wait for the next implementation prompt.
```

**Gate**: Publish an event, subscriber on another connection receives it with correct payload. ✓ / ✗

---

## Session 4.4 — Redis Manager Tests

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/08_REDIS_ARCHITECTURE.md, and docs/20_TESTING.md.

Before writing anything:
1. List the test cases you will write (one sentence each).
Then implement.

Your task:
Write unit tests for the complete Redis Manager.

Allowed Files:
- tests/backend/test_redis_manager.py
- tests/backend/conftest.py (pytest fixtures only)

Use a real Redis test instance. Do not mock Redis.

Definition of Done:
[ ] Tests cover: every key builder function.
[ ] Tests cover: enqueue + dequeue round-trip.
[ ] Tests cover: mark_active and mark_done.
[ ] Tests cover: publish + subscribe event delivery.
[ ] pytest runs and ALL tests pass.

STOP.
Do not implement the Workspace Manager yet.
Wait for the next implementation prompt.
```

**Gate**: `pytest tests/backend/test_redis_manager.py -v` — all pass. ✓ / ✗

---

# PHASE 5 — Workspace Manager

---

## Session 5.1 — Workspace Creation and Layout

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/06_WORKSPACE_ARCHITECTURE.md.

Before writing anything:
1. List every subdirectory that must be created inside a migration workspace.
2. Identify the environment variable for the workspace root path.
Then implement.

Your task:
Implement the Workspace Manager — workspace creation and teardown.

Allowed Files:
- backend/app/workspace/manager.py

Definition of Done:
[ ] create_workspace(migration_id) creates the exact directory tree from docs/06_WORKSPACE_ARCHITECTURE.md.
[ ] Workspace root path comes from an environment variable, not hardcoded.
[ ] teardown_workspace(migration_id) removes the workspace directory completely.
[ ] No errors if teardown is called on a non-existent workspace.

STOP.
Do not implement file helpers yet.
Wait for the next implementation prompt.
```

**Gate**: `create_workspace("test-id")` — directory tree matches `docs/06_WORKSPACE_ARCHITECTURE.md`. ✓ / ✗

---

## Session 5.2 — File Helpers + Tests

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/06_WORKSPACE_ARCHITECTURE.md, and docs/20_TESTING.md.

Before writing anything:
1. List the three helper functions you will implement.
2. List the test cases you will write.
Then implement.

Your task:
Implement file read/write helpers and write all Workspace Manager tests.

Allowed Files:
- backend/app/workspace/manager.py (add helpers to existing file)
- backend/app/workspace/storage.py (if the spec separates storage logic)
- tests/backend/test_workspace_manager.py

Definition of Done:
[ ] write_source_file(migration_id, filename, content) writes to the correct workspace subdirectory.
[ ] read_file(migration_id, relative_path) reads and returns file content.
[ ] resolve_path(migration_id, relative_path) returns the correct absolute path.
[ ] pytest covers: create, write, read, resolve, teardown.
[ ] All tests pass.

STOP.
Wait for the next implementation prompt.
```

**Gate**: `pytest tests/backend/test_workspace_manager.py -v` — all pass. ✓ / ✗

---

# PHASE 6 — Workflow Engine

---

## Session 6.1 — State Machine Base Class

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/07_WORKFLOW_ENGINE.md, and docs/26_JOB_LIFECYCLE.md.

Before writing anything:
1. List all 10 state names in order.
2. Describe how the run() loop will traverse them.
3. Describe how job context will be structured and passed.
Then implement.

Your task:
Implement the WorkflowEngine base class and state registry. State handlers are stubs — they immediately return success.

Allowed Files:
- backend/app/workflow_engine/state_machine.py
- backend/app/workflow_engine/context.py
- backend/app/workflow_engine/states.py (stub handlers only)

Definition of Done:
[ ] WorkflowEngine accepts job context: migration_id, workspace_path, redis_manager.
[ ] State registry maps all 10 state names to handler methods.
[ ] run() traverses all 10 states sequentially via stubs without errors.
[ ] No state handler contains real logic yet.
[ ] Import works without errors.

STOP.
Do not implement retry logic yet.
Wait for the next implementation prompt.
```

**Gate**: `WorkflowEngine` with mock context, `run()` → all 10 states traverse without errors. ✓ / ✗

---

## Session 6.2 — Retry Logic and Failure Handling

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/07_WORKFLOW_ENGINE.md, and docs/26_JOB_LIFECYCLE.md.

Before writing anything:
1. Identify which states support retries and their retry limits.
2. Describe the FAILED transition logic.
3. Describe what must happen in Redis on FAILED and COMPLETED.
Then implement.

Your task:
Implement retry logic and failure handling in the WorkflowEngine.

Allowed Files:
- backend/app/workflow_engine/state_machine.py
- backend/app/workflow_engine/transitions.py

Definition of Done:
[ ] States with retry support retry up to the configured maximum before FAILED.
[ ] FAILED state sets the Redis status key and emits a failure event.
[ ] COMPLETED state sets the Redis status key and emits a completion event.
[ ] pytest test: a state fails beyond retry limit → engine ends in FAILED.
[ ] Test passes.

STOP.
Do not wire Redis events yet.
Wait for the next implementation prompt.
```

**Gate**: Test passes — failing state exhausts retries, engine ends in `FAILED`. ✓ / ✗

---

## Session 6.3 — Redis Event Emission

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/07_WORKFLOW_ENGINE.md, docs/08_REDIS_ARCHITECTURE.md, and docs/26_JOB_LIFECYCLE.md.

Before writing anything:
1. Identify exactly when events must be emitted: before entering, after completing, on failure.
2. Confirm the event payload fields from docs/26_JOB_LIFECYCLE.md.
Then implement.

Your task:
Wire Redis Pub/Sub event emission into the WorkflowEngine.

Allowed Files:
- backend/app/workflow_engine/state_machine.py (event calls only — no restructuring)

Use only publish_event() from backend/app/redis/publisher.py. Do not call Redis directly.

Definition of Done:
[ ] status="started" event published before entering each state.
[ ] status="completed" event published after each state succeeds.
[ ] status="failed" event published with error message on failure.
[ ] Events include all fields: stage, status, message, timestamp.
[ ] pytest test: engine run → events appear on Redis Pub/Sub channel.
[ ] Test passes.

STOP.
Wait for the next implementation prompt.
```

**Gate**: Events appear on the Redis channel for every state transition during a test run. ✓ / ✗

---

## Session 6.4 — Workflow Engine Tests

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/07_WORKFLOW_ENGINE.md, and docs/20_TESTING.md.

Before writing anything:
1. List every test case you will write.
Then implement.

Your task:
Write the full test suite for the Workflow Engine.

Allowed Files:
- tests/backend/test_workflow_engine.py
- tests/backend/conftest.py (add fixtures if needed — do not modify existing ones)

Definition of Done:
[ ] Test: successful traversal of all 10 states.
[ ] Test: retry — state fails N-1 times then succeeds.
[ ] Test: failure — state fails beyond retry limit → FAILED.
[ ] Test: events emitted at every transition.
[ ] pytest -v runs and ALL tests pass.

STOP.
Wait for the next implementation prompt.
```

**Gate**: `pytest tests/backend/test_workflow_engine.py -v` — all pass. ✓ / ✗

---

# PHASE 7 — Migration Worker

---

## Session 7.1 — Worker Entrypoint and Consumer Loop

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/24_SCALABILITY.md, and docs/08_REDIS_ARCHITECTURE.md.

Before writing anything:
1. Describe the single-job execution guarantee.
2. Describe the full loop: BRPOP → mark_active → run engine → mark_done.
3. Describe what happens if the engine raises an unhandled exception.
Then implement.

Your task:
Implement the Migration Worker entrypoint.

Allowed Files:
- backend/app/workers/migration_worker.py

Definition of Done:
[ ] Worker calls BRPOP on the pending queue with a configurable timeout.
[ ] When a job is received: mark_active → run WorkflowEngine → mark_done.
[ ] Strictly single-threaded: never starts a second job until the first is done.
[ ] try/finally ensures mark_done always runs, even on engine crash.
[ ] Worker loops indefinitely until killed by signal.
[ ] Starting the worker produces no errors.

STOP.
Do not write the integration test yet.
Wait for the next implementation prompt.
```

**Gate**: Start worker → LPUSH test job → worker dequeues, runs all state stubs, completes. ✓ / ✗

---

## Session 7.2 — Worker Integration Test

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/24_SCALABILITY.md, and docs/20_TESTING.md.

Before writing anything:
1. Describe how you will start the worker in the test.
2. Describe the assertions you will make.
Then implement.

Your task:
Write an integration test for the Migration Worker.

Allowed Files:
- tests/integration/test_migration_worker.py

Definition of Done:
[ ] Test starts the worker in a subprocess or background thread.
[ ] Test submits a job via Redis LPUSH.
[ ] Asserts job reaches COMPLETED (checks Redis status key).
[ ] Asserts all 10 state transition events were published.
[ ] Asserts worker is still alive after the job finishes.
[ ] pytest passes.

STOP.
Wait for the next implementation prompt.
```

**Gate**: `pytest tests/integration/test_migration_worker.py -v` passes. ✓ / ✗

---

# PHASE 8 — Compilation Pipeline

---

## Session 8.1 — hipify-clang Wrapper

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/10_COMPILATION_PIPELINE.md.

Before writing anything:
1. Identify the subprocess command from the spec.
2. Identify the return schema.
Then implement.

Your task:
Implement the hipify-clang subprocess wrapper and unit tests.

Allowed Files:
- backend/app/compiler/hipify_runner.py
- tests/backend/test_hipify_runner.py
- tests/backend/fixtures/ (place .cu test fixture files here)

Definition of Done:
[ ] run_hipify(source_path, output_path) runs hipify-clang as a subprocess.
[ ] Returns: {"success": bool, "output_path": str, "stdout": str, "stderr": str}.
[ ] On non-zero exit: success=False, error in stderr field.
[ ] Unit test uses a real .cu fixture file.
[ ] HIP output file is written. Test passes.

STOP.
Do not implement hipcc yet.
Wait for the next implementation prompt.
```

**Gate**: `pytest tests/backend/test_hipify_runner.py -v` passes. Translated HIP file exists on disk. ✓ / ✗

---

## Session 8.2 — hipcc Wrapper + Error Parser

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/10_COMPILATION_PIPELINE.md.

Before writing anything:
1. Identify the CompilerError schema from docs/10_COMPILATION_PIPELINE.md.
2. Identify the subprocess command for hipcc.
3. Describe your error parsing approach.
Then implement.

Your task:
Implement the hipcc compiler wrapper and error parser.

Allowed Files:
- backend/app/compiler/hipcc_runner.py
- backend/app/compiler/error_parser.py
- backend/app/models/compiler_error.py
- tests/backend/test_hipcc_runner.py

Definition of Done:
[ ] run_hipcc(source_path, output_path) runs hipcc as a subprocess.
[ ] Returns: {"success": bool, "binary_path": str, "errors": list[CompilerError], "stdout": str}.
[ ] CompilerError has exactly: file, line, column, message, code.
[ ] Error parser extracts all structured errors from hipcc stderr.
[ ] Unit test uses a .hip fixture file with known errors.
[ ] Tests pass. Structured error list matches known errors.

STOP.
Do not implement SCA yet.
Wait for the next implementation prompt.
```

**Gate**: `pytest tests/backend/test_hipcc_runner.py -v` passes. Known errors produce structured objects. ✓ / ✗

---

## Session 8.3 — Semantic Compatibility Analyzer

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/10_COMPILATION_PIPELINE.md.

Before writing anything:
1. Identify the CompatibilityIssue schema from docs/10_COMPILATION_PIPELINE.md.
2. List the patterns the SCA must detect.
Then implement.

Your task:
Implement the Semantic Compatibility Analyzer.

Allowed Files:
- backend/app/compiler/sca.py
- backend/app/models/compatibility_issue.py
- tests/backend/test_sca.py

Definition of Done:
[ ] analyze(source_path) scans HIP source for patterns in docs/10_COMPILATION_PIPELINE.md.
[ ] Returns: {"issues": list[CompatibilityIssue], "score": float}.
[ ] CompatibilityIssue schema exactly matches docs/10_COMPILATION_PIPELINE.md.
[ ] Unit test uses a fixture with at least 2 known issues.
[ ] Tests pass. Known issues correctly identified.

STOP.
Do not wire into Workflow Engine yet.
Wait for the next implementation prompt.
```

**Gate**: `pytest tests/backend/test_sca.py -v` passes. Known patterns detected correctly. ✓ / ✗

---

## Session 8.4 — Wire Pipeline into Workflow States

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/07_WORKFLOW_ENGINE.md, docs/10_COMPILATION_PIPELINE.md, and docs/26_JOB_LIFECYCLE.md.

Before writing anything:
1. Identify which state handlers will be replaced: HIPIFY, SCA, COMPILING.
2. Describe how results are stored in the job context.
Then implement.

Your task:
Replace HIPIFY, SCA, and COMPILING state stubs with real implementations.

Allowed Files:
- backend/app/workflow_engine/states.py (HIPIFY, SCA, COMPILING handlers only)
- backend/app/workflow_engine/context.py (add fields for compiler output if needed)

Do not modify state_machine.py, transitions.py, or any other state handler.

Definition of Done:
[ ] HIPIFY state calls run_hipify(), stores output_path in context, fails on error.
[ ] SCA state calls analyze(), stores issues in context, emits issue count in event.
[ ] COMPILING state calls run_hipcc(), stores errors in context.
[ ] End-to-end test: real CUDA file passes through HIPIFY → SCA → COMPILING.
[ ] Test passes.

STOP.
Do not implement AI agents yet.
Wait for the next implementation prompt.
```

**Gate**: Test CUDA file traverses HIPIFY → SCA → COMPILING successfully. ✓ / ✗

---

# PHASE 9 — AI Agents

---

## Session 9.1 — Fireworks AI Client

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/09_AI_AGENTS.md, and docs/04_TECHNOLOGY_DECISIONS.md.

Before writing anything:
1. Identify the Fireworks AI authentication method.
2. Identify the retry/backoff behavior from docs/09_AI_AGENTS.md.
Then implement.

Your task:
Implement the Fireworks AI client wrapper.

Allowed Files:
- backend/app/agents/base_agent.py

Definition of Done:
[ ] Client authenticates using FIREWORKS_API_KEY from environment.
[ ] chat_completion(model, messages, max_tokens) method works end to end.
[ ] Rate limit errors trigger exponential backoff per docs/09_AI_AGENTS.md.
[ ] Test makes a real API call and returns a valid completion.
[ ] Test passes.

STOP.
Do not implement any agent yet.
Wait for the next implementation prompt.
```

**Gate**: Real Fireworks API call succeeds and returns a completion response. ✓ / ✗

---

## Session 9.2 — Analysis Agent

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/09_AI_AGENTS.md.

Before writing anything:
1. Identify the Analysis Agent's input contract.
2. Identify the output schema.
3. Write out the prompt template from the spec before coding.
Then implement.

Your task:
Implement the Analysis Agent and wire it into the ANALYZING Workflow Engine state.

Allowed Files:
- backend/app/agents/analysis_agent.py
- backend/app/workflow_engine/states.py (ANALYZING handler only)

Definition of Done:
[ ] analyze(compiler_errors, source_code) uses exact prompt template from docs/09_AI_AGENTS.md.
[ ] Returns: {"analysis": str, "root_cause": str, "suggested_fix": str}.
[ ] ANALYZING state calls agent and stores result in context.
[ ] Test with a real compiler error returns a structured diagnosis.
[ ] Test passes.

STOP.
Do not implement Patch Agent yet.
Wait for the next implementation prompt.
```

**Gate**: Analysis Agent returns structured diagnosis for a real compiler error. ✓ / ✗

---

## Session 9.3 — Patch Agent

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/09_AI_AGENTS.md.

Before writing anything:
1. Confirm the output is a full corrected file, not a diff.
2. Identify the input contract.
Then implement.

Your task:
Implement the Patch Agent and wire it into the PATCHING Workflow Engine state.

Allowed Files:
- backend/app/agents/patch_agent.py
- backend/app/workflow_engine/states.py (PATCHING handler only)

Definition of Done:
[ ] patch(source_code, analysis, compiler_errors) uses exact prompt template from docs/09_AI_AGENTS.md.
[ ] Returns the full corrected source file as a string.
[ ] PATCHING state calls agent and writes patched source to workspace.
[ ] Test: patched file no longer contains the targeted error.
[ ] Test passes.

STOP.
Do not implement Research Agent yet.
Wait for the next implementation prompt.
```

**Gate**: Patch Agent returns corrected source. Known error is absent in the output. ✓ / ✗

---

## Session 9.4 — Research Agent

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/11_RESEARCH_AGENT.md.

Before writing anything:
1. Identify the Research Agent's query input and context output format.
2. Describe how the result feeds into the next ANALYZING cycle.
Then implement.

Your task:
Implement the Research Agent and wire it into the RESEARCHING Workflow Engine state.

Allowed Files:
- backend/app/agents/research_agent.py
- backend/app/workflow_engine/states.py (RESEARCHING handler only)
- backend/app/workflow_engine/context.py (add research_context field if needed)

Definition of Done:
[ ] research(query) follows behavior defined in docs/11_RESEARCH_AGENT.md.
[ ] Returns relevant HIP/ROCm documentation context as a string.
[ ] RESEARCHING state stores result in context for next ANALYZING cycle.
[ ] Test with a known HIP error query returns relevant context.
[ ] Test passes.

STOP.
Do not implement the repair loop integration test yet.
Wait for the next implementation prompt.
```

**Gate**: Research Agent returns relevant context for a HIP error query. ✓ / ✗

---

## Session 9.5 — Full AI Repair Loop Integration Test

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/07_WORKFLOW_ENGINE.md, docs/09_AI_AGENTS.md, and docs/20_TESTING.md.

Before writing anything:
1. Describe the exact scenario: what CUDA file, what errors, what the loop should do.
Then implement.

Your task:
Write an integration test for the full AI repair loop.

Allowed Files:
- tests/integration/test_ai_repair_loop.py
- tests/integration/fixtures/ (CUDA test file with a known error)

Definition of Done:
[ ] Test starts with CUDA file that produces a known hipcc error after hipify.
[ ] Engine enters: ANALYZING → PATCHING → RESEARCHING → COMPILING.
[ ] Migration Journal records at least one complete repair iteration.
[ ] pytest runs and test passes.

STOP.
Wait for the next implementation prompt.
```

**Gate**: `pytest tests/integration/test_ai_repair_loop.py -v` passes. ✓ / ✗

---

# PHASE 10 — Migration Journal

---

## Session 10.1 — Journal Write, Read, and API Endpoint

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/12_MIGRATION_JOURNAL.md, docs/08_REDIS_ARCHITECTURE.md, and docs/16_API_SPECIFICATION.md.

Before writing anything:
1. Identify the journal entry schema from docs/12_MIGRATION_JOURNAL.md.
2. Identify persistence targets (Redis + filesystem).
3. Identify the API endpoint path.
Then implement.

Your task:
Implement the Migration Journal write/read logic and API endpoint.

Allowed Files:
- backend/app/services/journal_service.py
- backend/app/api/migration.py (add journal endpoint — do not change other routes)
- backend/app/workflow_engine/state_machine.py (call journal service after each state — one line addition only)
- tests/backend/test_journal_service.py

Definition of Done:
[ ] append_journal_entry(migration_id, entry) writes to Redis AND workspace filesystem.
[ ] get_journal(migration_id) returns all entries as a list.
[ ] Journal entry schema exactly matches docs/12_MIGRATION_JOURNAL.md.
[ ] A journal entry is written after every state transition.
[ ] GET /migrate/{id}/journal returns the full journal JSON.
[ ] Returns 404 if migration does not exist.
[ ] pytest tests pass.

STOP.
Wait for the next implementation prompt.
```

**Gate**: Journal entries appear in Redis and on disk after test migration. API returns correct JSON. ✓ / ✗

---

# PHASE 11 — Report Generator

---

## Session 11.1 — All Four Report Formats

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/17_REPORT_GENERATOR.md.

Before writing anything:
1. List the four report artifacts that must be produced.
2. List the fields required in each from docs/17_REPORT_GENERATOR.md.
Then implement.

Your task:
Implement all four report generators and wire them into the GENERATING_REPORT state.

Allowed Files:
- backend/app/services/report_service.py
- backend/app/workflow_engine/states.py (GENERATING_REPORT handler only)
- tests/backend/test_report_service.py

Definition of Done:
[ ] generate_markdown_report(migration_id, context) produces a .md in the workspace.
[ ] generate_json_report(migration_id, context) produces a .json in the workspace.
[ ] generate_git_patch(migration_id) produces a .patch diff of original vs translated.
[ ] build_zip(migration_id) packages all three into a .zip.
[ ] All fields required by docs/17_REPORT_GENERATOR.md are present.
[ ] GENERATING_REPORT state calls all four in order.
[ ] Tests verify all four files exist with required fields.
[ ] pytest passes.

STOP.
Do not implement the download endpoint yet.
Wait for the next implementation prompt.
```

**Gate**: Completed test migration — workspace contains all four report artifacts. ✓ / ✗

---

## Session 11.2 — Download Endpoint

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/16_API_SPECIFICATION.md.

Before writing anything:
1. Identify the endpoint path, method, and response headers.
Then implement.

Your task:
Replace the 501 stub for the download endpoint with a real implementation.

Allowed Files:
- backend/app/api/download.py

Definition of Done:
[ ] GET /migrate/{id}/download streams the ZIP file.
[ ] Content-Type: application/zip.
[ ] Content-Disposition: attachment; filename="hipforge-{id}.zip".
[ ] Returns 404 if migration does not exist or is not COMPLETED.
[ ] curl download produces a valid, openable ZIP.

STOP.
Wait for the next implementation prompt.
```

**Gate**: `curl -O` downloads a valid ZIP. Archive opens and contains all four artifacts. ✓ / ✗

---

# PHASE 12 — Backend API (Full)

---

## Session 12.1 — Job Submission Endpoint (Full)

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/16_API_SPECIFICATION.md, docs/08_REDIS_ARCHITECTURE.md, and docs/06_WORKSPACE_ARCHITECTURE.md.

Before writing anything:
1. List every step POST /migrate must perform in order.
2. Identify the response on success.
Then implement.

Your task:
Replace the POST /migrate stub with the full implementation.

Allowed Files:
- backend/app/api/migration.py (POST /migrate route only)
- backend/app/services/migration_service.py (create this service)
- backend/app/schemas/ (add request/response Pydantic models if missing)

Definition of Done:
[ ] Accepts file upload per docs/16_API_SPECIFICATION.md.
[ ] Generates a UUID migration_id.
[ ] Creates workspace via Workspace Manager.
[ ] Writes uploaded source to workspace.
[ ] Enqueues job in Redis via Redis Manager.
[ ] Initializes Redis status key to QUEUED.
[ ] Returns 202 Accepted with migration_id.
[ ] Integration test: upload CUDA file → 202 returned → job in Redis → worker dequeues it.
[ ] Test passes.

STOP.
Do not implement the status endpoint yet.
Wait for the next implementation prompt.
```

**Gate**: `POST /migrate` with CUDA file → 202 → Redis contains job → worker dequeues it. ✓ / ✗

---

## Session 12.2 — Status Endpoint + WebSocket Relay (Full)

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/16_API_SPECIFICATION.md, and docs/08_REDIS_ARCHITECTURE.md.

Before writing anything:
1. Identify the fields GET /migrate/{id} must return.
2. Describe the WebSocket relay loop.
Then implement.

Your task:
Replace the status stub and implement the full WebSocket relay.

Allowed Files:
- backend/app/api/status.py (GET /migrate/{id} endpoint)
- backend/app/websocket/stream.py (replace stub with Pub/Sub relay)
- backend/app/websocket/manager.py (connection lifecycle management)

Definition of Done:
[ ] GET /migrate/{id} returns: migration_id, status, stage, created_at, updated_at.
[ ] Returns 404 if migration does not exist.
[ ] WebSocket subscribes to Redis Pub/Sub for the migration.
[ ] Every published event forwarded to client as JSON.
[ ] WebSocket closes gracefully on COMPLETED or FAILED.
[ ] Test: submit job, open WebSocket, all 10 state events arrive.
[ ] Test passes.

STOP.
Wait for the next implementation prompt.
```

**Gate**: WebSocket client receives real-time events for all 10 states during a live migration. ✓ / ✗

---

# PHASE 13 — Frontend

---

## Session 13.1 — Upload Page + Job Submission

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/14_FRONTEND.md, and docs/16_API_SPECIFICATION.md.

Before writing anything:
1. Describe the upload page layout and components.
2. Identify the API call and success/error behavior.
Then implement.

Your task:
Implement the upload page and job submission flow.

Allowed Files:
- frontend/app/page.tsx (or upload page route per docs/03_PROJECT_STRUCTURE.md)
- frontend/components/UploadCard/ (upload zone component)
- frontend/services/api.ts (add submit function)
- frontend/types/migration.ts (add MigrationResponse type)

Definition of Done:
[ ] Drag-and-drop zone accepts .cu files and zip archives.
[ ] Start Migration button calls POST /migrate.
[ ] Loading state shown while request is in flight.
[ ] On success: browser navigates to migration dashboard.
[ ] On error: error message shown — no crash.
[ ] npm run build completes with no TypeScript errors.
[ ] Manual test: upload file → browser navigates to dashboard.

STOP.
Do not implement the timeline yet.
Wait for the next implementation prompt.
```

**Gate**: Upload file → Start Migration → browser navigates to dashboard. ✓ / ✗

---

## Session 13.2 — Live Progress Timeline

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/14_FRONTEND.md, docs/26_JOB_LIFECYCLE.md, and docs/16_API_SPECIFICATION.md.

Before writing anything:
1. List all 10 states and their display order.
2. Describe the WebSocket connection lifecycle.
Then implement.

Your task:
Implement the live progress timeline component.

Allowed Files:
- frontend/components/Timeline/ (Timeline component and sub-components)
- frontend/hooks/useWebSocket.ts (WebSocket hook)
- frontend/app/migrate/[id]/page.tsx (dashboard page — add Timeline component only)

Definition of Done:
[ ] All 10 states displayed in a vertical timeline.
[ ] Each state highlights on "started" event.
[ ] Each state shows checkmark on "completed" event.
[ ] Failed states show red error indicator with message.
[ ] WebSocket reconnects automatically on disconnect.
[ ] npm run build completes with no TypeScript errors.
[ ] Manual test: all 10 states animate in sequence during a live migration.

STOP.
Do not implement log stream yet.
Wait for the next implementation prompt.
```

**Gate**: All 10 stages animate live in the browser during a real migration. ✓ / ✗

---

## Session 13.3 — Log Stream, Journal Viewer, Report Viewer, Download

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/14_FRONTEND.md.

Before writing anything:
1. List the four panels and their data sources.
Then implement.

Your task:
Implement the four remaining dashboard panels.

Allowed Files:
- frontend/components/CompilerLog/ (log stream)
- frontend/components/JournalViewer/ (journal viewer)
- frontend/components/ReportViewer/ (report viewer)
- frontend/app/migrate/[id]/page.tsx (add three new components — no layout restructuring)
- frontend/services/api.ts (add journal and report fetch functions)

Definition of Done:
[ ] Log stream displays WebSocket log events in real time.
[ ] Journal viewer fetches GET /migrate/{id}/journal and renders iterations.
[ ] Report viewer fetches and renders the Markdown report.
[ ] Download button triggers GET /migrate/{id}/download, browser downloads ZIP.
[ ] All four panels work on a completed migration.
[ ] npm run build completes with no TypeScript errors.

STOP.
Wait for the next implementation prompt.
```

**Gate**: All four panels render correctly on a real completed migration. ZIP downloads. ✓ / ✗

---

# PHASE 14 — Testing, Security & Polish

---

## Session 14.1 — End-to-End Test

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, docs/20_TESTING.md, and docs/31_DEMO_SCRIPT.md.

Before writing anything:
1. Describe the full E2E scenario step by step.
2. List every assertion you will make.
Then implement.

Your task:
Write and run the full end-to-end integration test.

Allowed Files:
- tests/integration/test_e2e.py
- tests/integration/fixtures/ (add CUDA test fixture if not present)

Definition of Done:
[ ] Test submits a CUDA file via POST /migrate.
[ ] Test waits for COMPLETED state via Redis polling.
[ ] Asserts: all 10 states traversed.
[ ] Asserts: Migration Journal has at least one entry per state.
[ ] Asserts: download ZIP contains Markdown report, JSON report, .patch, and translated source.
[ ] pytest -v passes with no failures.

STOP.
Wait for the next implementation prompt.
```

**Gate**: `pytest tests/integration/test_e2e.py -v` — passes completely. ✓ / ✗

---

## Session 14.2 — Security Hardening

```
Read .agent/PROJECT_CONTEXT.md, .agent/AGENT_RULES.md, and docs/19_SECURITY.md.

Before writing anything:
1. List the security requirements from docs/19_SECURITY.md not yet implemented.
Then implement each one.

Your task:
Apply security hardening per docs/19_SECURITY.md.

Allowed Files:
- backend/app/main.py (middleware additions only)
- backend/app/api/ (input validation additions only)
- backend/app/config/settings.py
- docker-compose.yml (environment variable security only)

Definition of Done:
[ ] Every security requirement in docs/19_SECURITY.md is satisfied.
[ ] No new endpoints introduced.
[ ] No existing functionality broken.
[ ] Backend starts cleanly. E2E test still passes.

STOP.
Wait for the next implementation prompt.
```

**Gate**: E2E test still passes after security changes. ✓ / ✗

---

## Session 14.3 — Demo Dry Run

```
Read this file only: docs/31_DEMO_SCRIPT.md

Check every item in the preparation checklist.

For each item, report: PASS or FAIL.

If any item FAILS:
- Describe the gap.
- Do NOT fix it — report it and stop.

Allowed Files:
None. This is a verification session only. Do not write code.

Definition of Done:
[ ] Every preparation checklist item checked.
[ ] A report listing PASS/FAIL for each item is produced.
[ ] If any FAIL: gaps described and no code written.

STOP.
```

**Gate**: All preparation checklist items PASS. Demo runs within 6 minutes with no errors. ✓ / ✗

---

> **You've shipped HIPForge.**
>
> Update `docs/30_IMPLEMENTATION_TRACKER.md` with ✅ for every completed component.
> You're ready to present.

---

# STARTUP PRODUCTIZATION IMPLEMENTATION PROMPTS

Use the following prompts in your upcoming sessions to build out the commercial-grade features described in the roadmap.

## Session 15.1 — gVisor Sandboxing Script

```markdown
You are a senior system architect and security engineer.
Implement a Python helper function `run_sandboxed_compiler(workspace_path: str, command: list, timeout_sec: int = 30) -> dict` that executes compiler tools safely inside an isolated Docker sandbox.

Requirements:
1. Docker Sandbox: Use a lightweight Docker container based on the `rocm/dev-ubuntu-22.04` image.
2. Sandboxed Runtime: The container must be run using gVisor (i.e., specify runtime="runsc" in Docker).
3. Hard Resource Limits: Limit the container to 2GB memory and 2 CPU cores.
4. Security Constraints: Disable network access completely inside the container (--network none), and run as a non-root user.
5. Directory Mounting: Mount the workspace 'input' directory as Read-Only and the 'generated' and 'logs' directories as Read-Write.
6. Execution & Cleanup: Run the command, capture stdout/stderr, enforce the timeout, and guarantee the container is destroyed/cleaned up instantly even if it crashes or times out.
7. Return Format: Return a dict containing {"returncode": int, "stdout": str, "stderr": str, "timeout": bool}.

Write clean, robust, and highly secure Python code using the official `docker` Python SDK. Include thorough logging and error handling.
```

---

## Session 15.2 — AST Pruning & Sliding Context Window

```markdown
You are a compiler engineer and Python developer.
Implement a Python utility `get_optimized_error_context(source_path: str, error_line: int, window_lines: int = 50) -> str` that extracts a highly optimized semantic slice of a source file around a compilation error.

Requirements:
1. AST Extraction: Use the `clang.cindex` Python bindings to parse the source file's Abstract Syntax Tree (AST).
2. Semantic Slicing: Locate the function, class, or structure that contains the `error_line`.
3. Context Compilation: Extract the full code of that function/class block, including:
   - Any global macros (#define) used in the file.
   - Headers/includes at the top of the file.
   - Any global variables referenced inside the function.
4. Fallback: If AST parsing fails or the error line falls outside a resolved block, fall back to extracting a sliding window of `window_lines` lines before and after the `error_line`.
5. Return Format: Return the compiled slice as a string, formatted cleanly to be sent as context to an LLM.

Write clean, optimized, and robust Python code. Add comments explaining the AST node traversal logic.
```

---

## Session 15.3 — LLM Search-and-Replace Patching Applier

```markdown
You are a senior tools developer.
Implement a Python function `apply_llm_search_replace_patch(original_code: str, patch_response: str) -> str` that parses search-and-replace blocks from an LLM and applies them programmatically.

Requirements:
1. Prompt Format: The LLM output is expected to follow this format:
   <<<<<<< SEARCH
   [exact code lines in original file]
   =======
   [replacement code lines]
   >>>>>>> REPLACE
2. Parsing: Locate all search-and-replace blocks inside the `patch_response`.
3. Validation: Verify that the SEARCH block matches a unique substring in the `original_code`. If there are multiple matches or no match, raise a ValueError with diagnostic details.
4. Application: Replace the SEARCH block with the REPLACE block, keeping all whitespace and indentation intact.
5. Return Format: Return the modified complete file contents as a string.

Include extensive unit tests using unittest or pytest to verify exact matching, multiple search-replace blocks, and edge cases with whitespace/indentation.
```
