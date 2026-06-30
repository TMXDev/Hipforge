# .agent/DEBUGGING_PROMPTS.md

> **Your bug-fixing playbook.** When something breaks, find the right section, copy the prompt, paste it in.
>
> The golden rule: **fix the smallest thing that corrects the behavior. Never redesign.**

---

## Universal Debug Header

> Paste this at the top of **every** debugging session before the specific prompt below.

```
Read these files before doing anything:
- .agent/PROJECT_CONTEXT.md
- .agent/AGENT_RULES.md

You are debugging HIPForge.

Your role is ONLY to identify and fix the bug described below.

You are NOT allowed to:
- Redesign any subsystem.
- Refactor code unrelated to the bug.
- Add new features.
- Rename files or folders.
- Introduce new libraries.

Before changing any code:
1. State the exact root cause.
2. List the files that need to change.
3. Explain the smallest possible fix.

Then implement the fix.
Verify it works.
STOP.
```

---

# Build & Import Failures

---

## DB-1 — Python ImportError / ModuleNotFoundError

```
The backend fails to start with an ImportError or ModuleNotFoundError.

Error:
[PASTE THE FULL ERROR HERE]

Before fixing:
1. Identify the exact missing module or circular import.
2. Check whether the import path matches docs/03_PROJECT_STRUCTURE.md.
3. Do not move files — fix the import path.

Allowed files to modify:
- Only the file containing the broken import.
- requirements.txt if a package is genuinely missing.

Fix the import. Restart the server. Confirm it starts cleanly.

STOP.
```

---

## DB-2 — TypeScript / Next.js Build Error

```
The frontend fails to build with a TypeScript or compilation error.

Error:
[PASTE THE FULL ERROR HERE]

Before fixing:
1. Identify the exact type error or missing import.
2. Check whether the type definition exists in frontend/types/.
3. Do not change the component architecture.

Allowed files to modify:
- Only the file containing the error.
- frontend/types/ if a type definition is missing.

Fix the error. Run: npm run build. Confirm it completes with zero errors.

STOP.
```

---

# Docker & Infrastructure Failures

---

## DB-3 — Docker Build Failure

```
A Docker build is failing.

Error:
[PASTE THE FULL DOCKER BUILD OUTPUT HERE]

Read: docs/15_DOCKER_SETUP.md

Before fixing:
1. Identify which Dockerfile instruction is failing.
2. Identify whether the issue is a missing file, wrong base image, or wrong package name.
3. Do not change the service architecture.

Allowed files to modify:
- The specific Dockerfile that is failing.
- requirements.txt or package.json if a dependency is wrong.

Fix the Dockerfile. Run: docker-compose build. Confirm it completes cleanly.

STOP.
```

---

## DB-4 — Docker Compose Service Fails to Start

```
A Docker Compose service is failing to start or is marked as unhealthy.

docker-compose ps output:
[PASTE HERE]

docker-compose logs [service-name] output:
[PASTE HERE]

Read: docs/15_DOCKER_SETUP.md

Before fixing:
1. Identify the failing service and the exact error in its logs.
2. Check port conflicts, volume mount paths, and environment variable names.
3. Do not modify the service architecture.

Allowed files to modify:
- docker-compose.yml
- The relevant Dockerfile
- .env.example

Fix the issue. Run: docker-compose up -d. Confirm all services show healthy.

STOP.
```

---

# Redis Failures

---

## DB-5 — Redis Connection Error

```
The backend or worker cannot connect to Redis.

Error:
[PASTE THE FULL ERROR HERE]

Read: docs/08_REDIS_ARCHITECTURE.md

Before fixing:
1. Check the Redis URL environment variable name against docs/08_REDIS_ARCHITECTURE.md.
2. Check whether the Redis service is running (docker-compose ps).
3. Check the connection pool configuration in backend/app/redis/client.py.

Allowed files to modify:
- backend/app/redis/client.py
- backend/app/config/ (environment variable loading only)

Fix the connection. Verify: docker-compose exec redis redis-cli PING returns PONG.
Verify the backend starts without Redis errors.

STOP.
```

---

## DB-6 — Redis Key Error / Wrong Key Format

```
A Redis operation is failing due to a key not found, wrong key format, or key collision.

Error:
[PASTE THE FULL ERROR AND THE OFFENDING CODE HERE]

Read: docs/08_REDIS_ARCHITECTURE.md

Before fixing:
1. Look up the correct key format in docs/08_REDIS_ARCHITECTURE.md.
2. Identify whether the key builder function in backend/app/redis/keys.py is wrong or bypassed.
3. Never hardcode a key string — always use the key builder functions.

Allowed files to modify:
- backend/app/redis/keys.py (if the builder is wrong)
- The file containing the raw key string (replace it with the builder call)

Fix the key. Write a test that verifies the correct key format. Run pytest.

STOP.
```

---

# FastAPI / Backend Failures

---

## DB-7 — API Endpoint Returns 500

```
An API endpoint is returning a 500 Internal Server Error.

Endpoint: [METHOD] [PATH]
Request body: [PASTE IF RELEVANT]
Error traceback: [PASTE THE FULL TRACEBACK HERE]

Read:
- docs/16_API_SPECIFICATION.md
- docs/13_BACKEND.md

Before fixing:
1. Read the full traceback to find the exact line causing the error.
2. Do not add error-suppression try/except blocks — fix the root cause.
3. Confirm the fix matches the endpoint contract in docs/16_API_SPECIFICATION.md.

Allowed files to modify:
- Only the file(s) referenced in the traceback.

Fix the error. Call the endpoint again and confirm it returns the correct status code.

STOP.
```

---

## DB-8 — API Returns Wrong Response Schema

```
An API endpoint is returning a response that does not match the specification.

Endpoint: [METHOD] [PATH]
Expected response (from docs/16_API_SPECIFICATION.md): [DESCRIBE]
Actual response: [PASTE]

Read: docs/16_API_SPECIFICATION.md

Before fixing:
1. Find the exact schema mismatch.
2. Fix the response serialization — do not change the spec.

Allowed files to modify:
- backend/app/api/ (the specific route file)
- backend/app/schemas/ (if a Pydantic schema is wrong)

Fix the schema. Call the endpoint. Confirm the response matches the spec exactly.

STOP.
```

---

# WebSocket Failures

---

## DB-9 — WebSocket Connection Drops or Never Connects

```
The frontend WebSocket connection to /ws/migrate/{id} is failing or dropping immediately.

Error / symptom:
[DESCRIBE]

Read:
- docs/16_API_SPECIFICATION.md
- docs/08_REDIS_ARCHITECTURE.md

Before fixing:
1. Check whether the backend WebSocket handler is running.
2. Check the CORS and WebSocket origin configuration.
3. Check whether the Redis Pub/Sub subscription is opening correctly.
4. Do not change the WebSocket URL path.

Allowed files to modify:
- backend/app/websocket/
- backend/app/main.py (CORS config only)

Fix the connection. Verify events arrive at the browser client.

STOP.
```

---

## DB-10 — WebSocket Events Not Arriving / Wrong Format

```
The WebSocket connection is established but events are missing or malformed.

Expected event format (from docs/26_JOB_LIFECYCLE.md): [DESCRIBE]
Actual event received: [PASTE]

Read:
- docs/08_REDIS_ARCHITECTURE.md
- docs/26_JOB_LIFECYCLE.md

Before fixing:
1. Check the Redis Pub/Sub publish call in the Workflow Engine or Migration Worker.
2. Check the WebSocket relay handler that reads from Pub/Sub and forwards to the client.
3. Verify the event JSON structure matches docs/26_JOB_LIFECYCLE.md exactly.

Allowed files to modify:
- backend/app/websocket/
- backend/app/workflow_engine/ (event emission only)
- backend/app/workers/migration_worker.py (event emission only)

Fix the event payload. Verify events arrive with the correct schema.

STOP.
```

---

# Workflow Engine Failures

---

## DB-11 — State Machine Stuck / State Not Transitioning

```
The Workflow Engine is stuck in a state and not transitioning.

Stuck state: [STATE NAME]
Migration ID: [ID]
Redis status key value: [PASTE redis-cli GET output]
Worker logs: [PASTE]

Read:
- docs/07_WORKFLOW_ENGINE.md
- docs/26_JOB_LIFECYCLE.md

Before fixing:
1. Check whether the state handler is throwing a silent exception.
2. Check whether the transition logic has a missing condition.
3. Do not change the state order — fix only the broken transition.

Allowed files to modify:
- backend/app/workflow_engine/state_machine.py
- backend/app/workflow_engine/states.py (the specific stuck state handler only)

Fix the transition. Run a test migration and confirm it progresses past the stuck state.

STOP.
```

---

## DB-12 — Job Stuck in FAILED State / Wrong Error Recorded

```
A job is failing unexpectedly or recording the wrong error message.

Migration ID: [ID]
Failing state: [STATE NAME]
Error in Redis: [PASTE]
Worker traceback: [PASTE]

Read:
- docs/07_WORKFLOW_ENGINE.md
- docs/26_JOB_LIFECYCLE.md

Before fixing:
1. Find the exact exception that caused the FAILED transition.
2. Check whether the error is in the state handler logic or the failure handler.
3. Do not suppress the error — fix the root cause.

Allowed files to modify:
- backend/app/workflow_engine/ (failure handler or specific state handler)

Fix the bug. Run a test migration that previously failed and confirm it reaches COMPLETED.

STOP.
```

---

# Compiler Failures

---

## DB-13 — hipify-clang Not Running / Wrong Output

```
The HIPIFY state is failing or hipify-clang is producing unexpected output.

Error:
[PASTE]

Read: docs/10_COMPILATION_PIPELINE.md

Before fixing:
1. Check the subprocess call in backend/app/compiler/hipify_runner.py.
2. Verify the input file path is correctly resolved from the workspace.
3. Do not change the hipify API — fix the subprocess call or path resolution.

Allowed files to modify:
- backend/app/compiler/hipify_runner.py
- backend/app/workspace/manager.py (path resolution only)

Fix the runner. Test with a real CUDA file and confirm the HIP output is written correctly.

STOP.
```

---

## DB-14 — hipcc Compilation Error Parser Failing

```
The error parser is not extracting structured errors from hipcc output.

hipcc stderr output:
[PASTE]

Expected CompilerError objects:
[DESCRIBE]

Actual parsed output:
[PASTE]

Read: docs/10_COMPILATION_PIPELINE.md

Before fixing:
1. Check the regex or parser logic in backend/app/compiler/error_parser.py.
2. Do not change the CompilerError schema — fix the parsing logic.

Allowed files to modify:
- backend/app/compiler/error_parser.py

Fix the parser. Write a unit test with the exact stderr sample above. Run pytest.

STOP.
```

---

# AI Agent Failures

---

## DB-15 — Fireworks AI API Error / Rate Limit

```
The Fireworks AI client is returning an error or being rate-limited.

Error:
[PASTE]

Read: docs/09_AI_AGENTS.md

Before fixing:
1. Check the error type (auth error, rate limit, timeout, bad request).
2. For rate limits: verify the exponential backoff is implemented per docs/09_AI_AGENTS.md.
3. For auth errors: check FIREWORKS_API_KEY is loaded from the environment correctly.
4. Do not change the agent prompt templates.

Allowed files to modify:
- backend/app/agents/ (base client / retry logic only)

Fix the client. Run the failing agent test again and confirm it succeeds.

STOP.
```

---

## DB-16 — AI Agent Returns Malformed Output

```
An AI agent is returning output that does not match the expected schema.

Agent: [Analysis Agent / Patch Agent / Research Agent]
Expected output schema (from docs/09_AI_AGENTS.md): [DESCRIBE]
Actual output: [PASTE]

Read: docs/09_AI_AGENTS.md

Before fixing:
1. Check whether the model response is structured JSON or free text.
2. Check the output parser in the agent file.
3. Do not change the prompt template — fix the output parser.

Allowed files to modify:
- backend/app/agents/[specific_agent].py (output parser only)

Fix the parser. Run the agent with the same input and confirm the output schema is correct.

STOP.
```

---

# Frontend Failures

---

## DB-17 — Upload Page Not Submitting / API Call Failing

```
The file upload or job submission in the browser is not working.

Error (from browser console or network tab):
[PASTE]

Read:
- docs/14_FRONTEND.md
- docs/16_API_SPECIFICATION.md

Before fixing:
1. Check the API client call in frontend/services/.
2. Verify the request format matches docs/16_API_SPECIFICATION.md.
3. Check CORS configuration on the backend.
4. Do not change the UI component layout.

Allowed files to modify:
- frontend/services/ (API client)
- frontend/app/ (upload page logic only — no layout changes)

Fix the submission. Upload a test file and confirm a migration_id is returned.

STOP.
```

---

## DB-18 — Progress Timeline Not Updating

```
The live timeline in the browser is not animating or updating.

Symptom: [DESCRIBE — e.g., "stuck at QUEUED", "events arrive but UI doesn't update"]
Browser console errors: [PASTE]
Network tab WebSocket frames: [PASTE a sample]

Read:
- docs/14_FRONTEND.md
- docs/26_JOB_LIFECYCLE.md

Before fixing:
1. Check whether events are arriving in the browser (Network tab → WS frames).
2. If events arrive but UI doesn't update: check the state update logic in the Timeline component.
3. If events don't arrive: use DB-9 (WebSocket Failures) instead.

Allowed files to modify:
- frontend/components/Timeline (or equivalent per docs/03_PROJECT_STRUCTURE.md)
- frontend/hooks/ (WebSocket hook only)

Fix the component. Watch a live migration and confirm all 10 states animate correctly.

STOP.
```

---

# Race Conditions & Async Failures

---

## DB-19 — Race Condition: Job Processed Twice / Queue Duplication

```
A migration job appears to be running twice simultaneously.

Symptom: [DESCRIBE]
Redis active queue contents: [PASTE redis-cli LRANGE output]

Read:
- docs/24_SCALABILITY.md
- docs/08_REDIS_ARCHITECTURE.md

Before fixing:
1. Check whether mark_active() is called atomically before the job starts.
2. Check whether multiple worker processes are racing on the same job.
3. Do not add locks that change the queue design.

Allowed files to modify:
- backend/app/workers/migration_worker.py
- backend/app/redis/manager.py (queue operations only)

Fix the race condition. Run two workers simultaneously and confirm no job is processed twice.

STOP.
```

---

## DB-20 — Worker Crashes Mid-Job / Job Lost

```
The Migration Worker crashed partway through a job and the job is now orphaned.

Symptoms:
- Worker logs end abruptly during state: [STATE NAME]
- Redis status key shows: [VALUE]
- Job is no longer in the active queue

Read:
- docs/24_SCALABILITY.md
- docs/26_JOB_LIFECYCLE.md

Before fixing:
1. Check the crash traceback in worker logs.
2. Determine whether cleanup (mark_done, FAILED transition) ran before the crash.
3. Add a try/finally block to ensure cleanup always runs on worker crash.

Allowed files to modify:
- backend/app/workers/migration_worker.py
- backend/app/workflow_engine/state_machine.py (cleanup only)

Fix the crash handling. Simulate a crash mid-job and confirm the job transitions to FAILED cleanly.

STOP.
```
