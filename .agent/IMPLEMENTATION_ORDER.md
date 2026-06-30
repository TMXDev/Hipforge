# IMPLEMENTATION_ORDER.md

> This document defines the **mandatory build sequence** for HIPForge.
>
> No phase may begin until the previous phase is verified and working.
> Each session corresponds to one entry in `IMPLEMENTATION_PROMPTS.md`.

---

## Phase 1 — Repository Scaffold

**Goal**: Empty but correct project structure exists on disk. No logic yet.

| Session | Task                         | Spec Reference          |
| ------- | ---------------------------- | ----------------------- |
| 1.1     | Create all folders and files | `03_PROJECT_STRUCTURE.md` |

**Gate**: Run `find . -type f` (or `Get-ChildItem -Recurse`) and confirm the layout matches `03_PROJECT_STRUCTURE.md` exactly.

---

## Phase 2 — Infrastructure

**Goal**: `docker-compose up` works. Redis is reachable. Environment is wired.

| Session | Task                              | Spec Reference          |
| ------- | --------------------------------- | ----------------------- |
| 2.1     | Write all Dockerfiles             | `15_DOCKER_SETUP.md`    |
| 2.2     | Write `docker-compose.yml`        | `15_DOCKER_SETUP.md`    |
| 2.3     | Write `.env.example` and config   | `15_DOCKER_SETUP.md`    |

**Gate**: `docker-compose up -d` starts without errors. `docker-compose ps` shows all services healthy. Redis responds to `PING`.

---

## Phase 3 — Backend Skeleton

**Goal**: FastAPI app starts. All route stubs exist. No business logic yet.

| Session | Task                                          | Spec Reference             |
| ------- | --------------------------------------------- | -------------------------- |
| 3.1     | FastAPI app entrypoint + CORS + health check  | `13_BACKEND.md`            |
| 3.2     | All API route stubs (no logic, return 501)    | `16_API_SPECIFICATION.md`  |
| 3.3     | WebSocket endpoint stub                       | `16_API_SPECIFICATION.md`  |

**Gate**: `uvicorn` starts. `/health` returns 200. All routes return 501. No import errors.

---

## Phase 4 — Redis Manager

**Goal**: All Redis operations used by HIPForge are wrapped in a single module.

| Session | Task                                        | Spec Reference               |
| ------- | ------------------------------------------- | ---------------------------- |
| 4.1     | Redis connection pool + all key helpers     | `08_REDIS_ARCHITECTURE.md`   |
| 4.2     | Queue operations (`LPUSH`, `BRPOP`, active) | `08_REDIS_ARCHITECTURE.md`   |
| 4.3     | Pub/Sub publish and subscribe helpers       | `08_REDIS_ARCHITECTURE.md`   |
| 4.4     | Unit tests for Redis Manager                | `20_TESTING.md`              |

**Gate**: All tests pass. Every key and channel defined in `08_REDIS_ARCHITECTURE.md` is covered by a helper function. No raw string keys exist outside this module.

---

## Phase 5 — Workspace Manager

**Goal**: Job directories are created, structured, and cleaned up correctly.

| Session | Task                                             | Spec Reference                 |
| ------- | ------------------------------------------------ | ------------------------------ |
| 5.1     | Workspace creation, layout, and teardown logic   | `06_WORKSPACE_ARCHITECTURE.md` |
| 5.2     | File write, read, and path resolution helpers    | `06_WORKSPACE_ARCHITECTURE.md` |
| 5.3     | Unit tests for Workspace Manager                 | `20_TESTING.md`                |

**Gate**: All tests pass. A workspace is created with the correct subdirectory structure. Source files are written and readable.

---

## Phase 6 — Workflow Engine

**Goal**: The state machine runs all 10 states in sequence with correct transitions.

| Session | Task                                              | Spec Reference          |
| ------- | ------------------------------------------------- | ----------------------- |
| 6.1     | State machine base class and state registry       | `07_WORKFLOW_ENGINE.md` |
| 6.2     | All 10 state handlers (stubs — no execution yet) | `26_JOB_LIFECYCLE.md`   |
| 6.3     | Transition logic, retry logic, failure handling   | `07_WORKFLOW_ENGINE.md` |
| 6.4     | Redis event emission per state transition         | `08_REDIS_ARCHITECTURE.md` |
| 6.5     | Unit tests for state transitions                  | `20_TESTING.md`         |

**Gate**: All tests pass. A mock job can traverse all 10 states. Events are emitted to Redis on each transition. Failure paths transition to `FAILED`.

---

## Phase 7 — Migration Worker

**Goal**: The worker process runs, dequeues one job, executes the Workflow Engine, and loops.

| Session | Task                                          | Spec Reference          |
| ------- | --------------------------------------------- | ----------------------- |
| 7.1     | Worker entrypoint and `BRPOP` consumer loop   | `24_SCALABILITY.md`     |
| 7.2     | Single-job lock, active queue, cleanup logic  | `24_SCALABILITY.md`     |
| 7.3     | Integration test: submit job → worker executes | `20_TESTING.md`        |

**Gate**: Integration test passes. Submit a job via Redis `LPUSH`, confirm the worker dequeues it, runs all state stubs, and emits events. Worker stays alive waiting for the next job.

---

## Phase 8 — Compilation Pipeline

**Goal**: `hipify-clang` and `hipcc` run as subprocesses. Output is captured and parsed.

| Session | Task                                        | Spec Reference               |
| ------- | ------------------------------------------- | ---------------------------- |
| 8.1     | `hipify-clang` subprocess wrapper           | `10_COMPILATION_PIPELINE.md` |
| 8.2     | `hipcc` compilation wrapper + error parser  | `10_COMPILATION_PIPELINE.md` |
| 8.3     | Semantic Compatibility Analyzer (SCA)       | `10_COMPILATION_PIPELINE.md` |
| 8.4     | Wire `HIPIFY`, `COMPILING` states into pipeline | `07_WORKFLOW_ENGINE.md`  |
| 8.5     | Unit tests for each wrapper                 | `20_TESTING.md`              |

**Gate**: All tests pass. `hipify-clang` translates a real CUDA test file. `hipcc` compiles the translated output. Errors are parsed into structured objects.

---

## Phase 9 — AI Agents

**Goal**: Analysis Agent, Patch Agent, and Research Agent operate correctly against the Fireworks AI API.

| Session | Task                                        | Spec Reference           |
| ------- | ------------------------------------------- | ------------------------ |
| 9.1     | Fireworks AI client + authentication        | `09_AI_AGENTS.md`        |
| 9.2     | Analysis Agent + prompt template            | `09_AI_AGENTS.md`        |
| 9.3     | Patch Agent + prompt template               | `09_AI_AGENTS.md`        |
| 9.4     | Research Agent + prompt template            | `11_RESEARCH_AGENT.md`   |
| 9.5     | Agent retry logic and fallback handling     | `09_AI_AGENTS.md`        |
| 9.6     | Wire `ANALYZING`, `PATCHING`, `RESEARCHING` states | `07_WORKFLOW_ENGINE.md` |
| 9.7     | Integration test: error → agent loop → patch | `20_TESTING.md`         |

**Gate**: Integration test passes. A compiler error enters the loop, the Analysis Agent diagnoses it, the Patch Agent produces a patch, and the Workflow Engine applies it and recompiles.

---

## Phase 10 — Migration Journal

**Goal**: Every iteration is logged to Redis with the correct schema.

| Session | Task                                          | Spec Reference           |
| ------- | --------------------------------------------- | ------------------------ |
| 10.1    | Journal write per iteration (Redis + file)    | `12_MIGRATION_JOURNAL.md` |
| 10.2    | Journal read + API endpoint                   | `16_API_SPECIFICATION.md` |
| 10.3    | Unit tests                                    | `20_TESTING.md`           |

**Gate**: A journal entry is written after every state transition. The API endpoint returns the full journal for a migration ID.

---

## Phase 11 — Report Generator

**Goal**: Four report formats are generated at `GENERATING_REPORT` state.

| Session | Task                               | Spec Reference           |
| ------- | ---------------------------------- | ------------------------ |
| 11.1    | Markdown report generator          | `17_REPORT_GENERATOR.md` |
| 11.2    | JSON report generator              | `17_REPORT_GENERATOR.md` |
| 11.3    | Git patch file generator           | `17_REPORT_GENERATOR.md` |
| 11.4    | ZIP package builder                | `17_REPORT_GENERATOR.md` |
| 11.5    | Wire into `GENERATING_REPORT` state | `07_WORKFLOW_ENGINE.md` |
| 11.6    | Download API endpoint              | `16_API_SPECIFICATION.md` |

**Gate**: A completed migration produces all four report artifacts. The download endpoint returns a valid ZIP.

---

## Phase 12 — Backend API (Full)

**Goal**: All API endpoints are fully implemented with real logic, not stubs.

| Session | Task                                     | Spec Reference           |
| ------- | ---------------------------------------- | ------------------------ |
| 12.1    | `POST /migrate` — job submission + enqueue | `16_API_SPECIFICATION.md` |
| 12.2    | `GET /migrate/{id}` — status polling     | `16_API_SPECIFICATION.md` |
| 12.3    | `GET /migrate/{id}/journal`              | `16_API_SPECIFICATION.md` |
| 12.4    | `GET /migrate/{id}/report`               | `16_API_SPECIFICATION.md` |
| 12.5    | `GET /migrate/{id}/download`             | `16_API_SPECIFICATION.md` |
| 12.6    | WebSocket event relay (Redis → frontend) | `16_API_SPECIFICATION.md` |
| 12.7    | Integration tests — full API surface     | `20_TESTING.md`          |

**Gate**: All integration tests pass. A job submitted via the API flows through the worker and produces a real report.

---

## Phase 13 — Frontend

**Goal**: The Next.js UI is fully functional against the real backend.

| Session | Task                                         | Spec Reference   |
| ------- | -------------------------------------------- | ---------------- |
| 13.1    | Upload page + job submission flow            | `14_FRONTEND.md` |
| 13.2    | Live progress timeline (WebSocket consumer)  | `14_FRONTEND.md` |
| 13.3    | Real-time log stream panel                   | `14_FRONTEND.md` |
| 13.4    | Migration Journal viewer                     | `14_FRONTEND.md` |
| 13.5    | Report viewer                                | `14_FRONTEND.md` |
| 13.6    | Download package button                      | `14_FRONTEND.md` |

**Gate**: Upload a CUDA file via the browser. Watch all 10 states animate live. Download the output ZIP.

---

## Phase 14 — Testing, Security & Polish

**Goal**: All subsystems are tested, security hardened, and the demo flow runs end to end without errors.

| Session | Task                                     | Spec Reference      |
| ------- | ---------------------------------------- | ------------------- |
| 14.1    | Full E2E test — CUDA file → ZIP download | `20_TESTING.md`     |
| 14.2    | Security hardening                       | `19_SECURITY.md`    |
| 14.3    | Observability / logging                  | `18_OBSERVABILITY.md` |
| 14.4    | Demo dry-run against `31_DEMO_SCRIPT.md` | `31_DEMO_SCRIPT.md` |

**Gate**: E2E test passes. Demo dry-run completes within 6 minutes. The preparation checklist in `31_DEMO_SCRIPT.md` is fully satisfied.

---

## Phase Summary

| Phase | Description              | Sessions |
| ----- | ------------------------ | -------- |
| 1     | Repository Scaffold      | 1        |
| 2     | Infrastructure           | 3        |
| 3     | Backend Skeleton         | 3        |
| 4     | Redis Manager            | 4        |
| 5     | Workspace Manager        | 3        |
| 6     | Workflow Engine          | 5        |
| 7     | Migration Worker         | 3        |
| 8     | Compilation Pipeline     | 5        |
| 9     | AI Agents                | 7        |
| 10    | Migration Journal        | 3        |
| 11    | Report Generator         | 6        |
| 12    | Backend API (Full)       | 7        |
| 13    | Frontend                 | 6        |
| 14    | Testing, Security, Polish | 4       |
| **Total** |                     | **60**   |

> **60 focused sessions.** Each one has a clear start, a deliverable, and a gate you verify before moving on.
