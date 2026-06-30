# AGENT_RULES.md

> **Read this file at the start of every coding session before writing any code.**
> Then read SESSION_STATE.json to understand exactly where you are.

---

## Purpose

This document defines the permanent rules for every AI coding session on HIPForge.

**These rules take priority over any implementation request.**

The architecture is designed. Your job is to build it — not redesign it.

---

## Rule 0 — Session State (Read First, Write Last)

**At the start of every session:**
1. Read `SESSION_STATE.json`.
2. Confirm the current session matches what you were asked to implement.
3. Check `mode` — if `"pre-hackathon"`, follow Rule 13 (mock services).
4. Check `blocked_items` — if anything is blocked that affects this session, report it before coding.

**At the end of every session (before stopping):**
Update `SESSION_STATE.json` with:
- `last_updated`: current ISO timestamp
- `last_session`: the session ID you just completed (e.g. `"3.1"`)
- `phase.current_session`: the **next** session ID
- `phase.status`: `"in_progress"` if more sessions remain in this phase, `"complete"` if all gates in this phase passed
- Under `sessions["X.Y"]`: set `"status": "completed"` and `"gate_passed": true` if the gate passed
- `next_action`: one sentence describing what the next session will do
- Any notes about decisions made or issues found in `sessions["X.Y"]["notes"]`

Do NOT update `SESSION_STATE.json` if the gate did not pass. Only update on success.

---

## Rule 1 — Architecture Is Frozen

The HIPForge architecture is locked. See `ARCHITECTURE_LOCK.md`.

- Do NOT redesign any subsystem.
- Do NOT suggest alternative patterns or frameworks.
- Do NOT refactor decisions that are already documented.

If you believe a design decision is wrong, **STOP** and explain why. Wait for instruction.

---

## Rule 2 — Read the Spec First

Before writing a single line of code for any component, read its specification document.

The specification is the source of truth. Code must match it exactly.

| Working on              | Read first                                                |
| ----------------------- | --------------------------------------------------------- |
| Workflow Engine         | `07_WORKFLOW_ENGINE.md`, `26_JOB_LIFECYCLE.md`            |
| Migration Worker        | `24_SCALABILITY.md`, `08_REDIS_ARCHITECTURE.md`           |
| Redis Manager           | `08_REDIS_ARCHITECTURE.md`                                |
| Backend API             | `13_BACKEND.md`, `16_API_SPECIFICATION.md`                |
| Workspace Manager       | `06_WORKSPACE_ARCHITECTURE.md`                            |
| Compilation Pipeline    | `10_COMPILATION_PIPELINE.md`                              |
| AI Agents               | `09_AI_AGENTS.md`, `11_RESEARCH_AGENT.md`                 |
| Migration Journal       | `12_MIGRATION_JOURNAL.md`                                 |
| Report Generator        | `17_REPORT_GENERATOR.md`                                  |
| Frontend                | `14_FRONTEND.md`, `16_API_SPECIFICATION.md`, `26_JOB_LIFECYCLE.md` |
| Docker / Infrastructure | `15_DOCKER_SETUP.md`, `03_PROJECT_STRUCTURE.md`           |

---

## Rule 3 — Never Invent APIs

Only implement API endpoints that are explicitly defined in `16_API_SPECIFICATION.md`.

If a required endpoint is missing from the spec:

> **STOP. Report the missing specification. Do not invent one.**

---

## Rule 4 — Never Invent Redis Keys

Only use Redis keys and channel names that are defined in `08_REDIS_ARCHITECTURE.md`.

No exceptions.

---

## Rule 5 — Never Change the Project Structure

The folder and file layout is defined in `03_PROJECT_STRUCTURE.md`.

- Do NOT rename files.
- Do NOT rename folders.
- Do NOT add new top-level directories without instruction.

---

## Rule 6 — Approved Technology Only

**Allowed:**
- Python / FastAPI
- TypeScript / Next.js
- Redis (native — `redis-py`, `ioredis`)
- Docker / Docker Compose
- Fireworks AI SDK
- `hipify-clang` / `hipcc` (subprocess calls)
- `pytest` for testing

**Forbidden without explicit approval:**
- LangGraph, LangChain, CrewAI
- Celery, RabbitMQ, Kafka, BullMQ
- Supabase, Firebase, MongoDB, PostgreSQL
- Any ORM (SQLAlchemy, Prisma, Drizzle)
- Zustand, Redux, Jotai (unless in spec)
- Any CSS framework not in the spec

---

## Rule 7 — Conflicts Must Be Reported

If two specification documents contradict each other:

> **STOP. Clearly state the conflict. Wait for resolution.**

Do not silently pick one interpretation.

---

## Rule 8 — No Placeholders

- Never write `TODO`, `FIXME`, `pass`, or `# implement later`.
- Never mock production code unless the specification explicitly permits a stub.
- Never use `...` as a function body in production code.

---

## Rule 9 — Verify Before Stopping

After every implementation task:

1. Run the relevant tests (`pytest`, `npm test`, etc.)
2. Fix any lint errors
3. Confirm the implemented behavior matches the specification
4. Report what was built, what was tested, and what passed

Only stop after verification is complete.

---

## Rule 10 — Implement One Thing

Implement exactly the subsystem or component requested. When it is done:

> **Stop. Do not continue to the next subsystem.**

Wait for the next prompt.

---

## Rule 11 — No Version 2 Features

The following are deferred to Version 2 and must NOT be built during this phase:

- Migration Replay
- Team workspaces
- Usage dashboards
- Subscription management
- Authentication / user accounts

If an implementation path naturally leads toward one of these, stop and report it.

---

## Rule 12 — Documentation Is Read-Only

You may read specification documents but not modify them during implementation.

If a specification needs to be updated based on an implementation finding:

> **STOP. Describe the required change. Wait for approval before modifying any `.md` file.**

---

## Rule 13 — Pre-Hackathon Mock Mode

Check `SESSION_STATE.json` → `mode` field before implementing any external service.

**If mode is `"pre-hackathon"`:**

- Read `MOCK_SERVICES.md` completely before implementing any AI agent or compiler wrapper.
- Build the **mock client first**, then the real client stub alongside it.
- Every external service must be injected via factory function (defined in `MOCK_SERVICES.md`).
- Use `USE_MOCK_AI` and `USE_MOCK_COMPILER` environment variables — never hardcode mock behavior.
- Never call the real Fireworks AI API. Never call `hipify-clang` or `hipcc` directly — use the factory.
- The mock and real implementations must share the exact same function signatures and return schemas.

**If mode is `"hackathon"`:**

- Real APIs are available. Use real clients.
- Follow the Hackathon Swap Checklist in `MOCK_SERVICES.md` before touching any service.

---

## Rule 14 — Commit Message Format

After every session gate passes, write a git commit message in this format:

```
feat(session-X.Y): <what was implemented>

Gate: passed
Mode: pre-hackathon | hackathon
```

Example:
```
feat(session-4.1): implement Redis connection pool and key builders

Gate: passed
Mode: pre-hackathon
```

This format makes it easy to trace which session produced which commit.
