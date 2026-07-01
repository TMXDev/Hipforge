# .agent/PROJECT_CONTEXT.md

> **Read this file first at the start of every session.**
> It gives you enough context to work on HIPForge without reading all 29 specification documents.

---

## Folder Structure

```
HIPForge/
├── docs/      ← Architecture specs (00–28, 30–31) — READ ONLY during implementation
└── .agent/    ← AI governance files — read/write every session
    ├── .agent/AGENT_RULES.md
    ├── .agent/SESSION_STATE.json      ← AI memory — updated after every gate
    ├── .agent/PROJECT_CONTEXT.md
    ├── .agent/IMPLEMENTATION_PROMPTS.md
    ├── .agent/IMPLEMENTATION_ORDER.md
    ├── .agent/DEBUGGING_PROMPTS.md
    ├── .agent/MOCK_SERVICES.md
    └── .agent/ARCHITECTURE_LOCK.md
```

---

## Current Development Phase

**Mode**: Hackathon (external APIs and compiler tools are connected/ready)

| Service | Available | How to Use |
|---------|-----------|------------|
| Redis | YES (Docker) | Use directly |
| Fireworks AI | NO | Use mock — see `.agent/MOCK_SERVICES.md` |
| hipify-clang | NO | Use mock — see `.agent/MOCK_SERVICES.md` |
| hipcc | NO | Use mock — see `.agent/MOCK_SERVICES.md` |

When the hackathon starts: set `USE_MOCK_AI=false` and `USE_MOCK_COMPILER=false` in `.env`. No code changes needed.

**Current session**: Check `.agent/SESSION_STATE.json` for exact position.

---


## What Is HIPForge?

HIPForge is an AI-powered CUDA-to-ROCm migration platform built for a hackathon.

It automatically translates NVIDIA CUDA GPU code to AMD HIP/ROCm code, compiles it, detects errors, and uses AI agents to repair those errors in a self-healing loop — producing a complete migration with a full audit trail and downloadable output package.

---

## The Problem It Solves

Migrating CUDA code to ROCm is painful:
- `hipify-clang` handles ~70% of translations automatically.
- The remaining 30% requires manual debugging of subtle API mismatches, incorrect memory patterns, and undocumented behavior differences.
- For large codebases this takes days or weeks.

HIPForge automates the full pipeline — including the hard 30%.

---

## How It Works (One Paragraph)

A user uploads a CUDA project via the Next.js frontend. The FastAPI backend creates a workspace, enqueues the job in Redis, and returns `202 Accepted` immediately. A standalone Migration Worker process dequeues the job and runs a 10-state Workflow Engine: `hipify-clang` translates the code, the Semantic Compatibility Analyzer checks for deep mismatches, `hipcc` compiles it, and if errors appear, an AI repair loop (Analysis Agent → Patch Agent → Research Agent) generates fixes and recompiles. Every state transition is broadcast in real-time to the frontend via WebSockets. When complete, a report package (Markdown, JSON, Git patch, ZIP) is generated and available for download.

---

## Architecture at a Glance

```
User (Browser)
    ↓ HTTP upload
Next.js Frontend
    ↓ POST /migrate          ↑ WebSocket events
FastAPI Backend ──── LPUSH ──→ Redis Queue ←─ BRPOP ── Migration Worker
                                                              ↓
                                                      Workflow Engine
                                                      ↓            ↓
                                                 hipify/hipcc    AI Agents
                                                      ↓
                                                  Reports + ZIP
```

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js (TypeScript) |
| Backend | FastAPI (Python) |
| Worker | Python standalone process |
| Queue | Redis (`LPUSH` / `BRPOP`) |
| Events | Redis Pub/Sub → WebSocket |
| Translation | `hipify-clang` (subprocess) |
| Compilation | `hipcc` (subprocess) |
| AI | Fireworks AI API |
| Containers | Docker + Docker Compose |

---

## The 10 Job States

Every migration travels through exactly these states in order:

```
QUEUED → PREPARING → HIPIFY → SCA → COMPILING
→ ANALYZING → PATCHING → RESEARCHING → COMPILING (retry)
→ GENERATING_REPORT → COMPLETED  (or FAILED at any point)
```

Full state machine: `docs/26_JOB_LIFECYCLE.md`

---

## Key Design Principles

1. **The architecture is frozen.** See `.agent/ARCHITECTURE_LOCK.md`. Do not redesign subsystems.
2. **Redis keys are centralized.** All keys and channels are in `docs/08_REDIS_ARCHITECTURE.md`. Never invent a key.
3. **Workers are single-job.** Each Migration Worker handles exactly one job at a time.
4. **One source of truth.** Code follows specs. If they conflict, stop and report it.
5. **No placeholders.** Production code must be complete and working.

---

## What Is Out of Scope (Version 1)

Do not build any of the following:
- User authentication / accounts
- Migration Replay feature
- Team workspaces
- Usage dashboards
- Subscription management

---

## Where to Find the Specifications

**Spec documents are in `docs/`:**

| Topic | File |
|-------|------|
| System overview | `docs/00_SYSTEM_SPECIFICATION.md` |
| Architecture diagram | `docs/02_SYSTEM_ARCHITECTURE.md` |
| Project file layout | `docs/03_PROJECT_STRUCTURE.md` |
| Tech decisions | `docs/04_TECHNOLOGY_DECISIONS.md` |
| Workspace structure | `docs/06_WORKSPACE_ARCHITECTURE.md` |
| Workflow Engine | `docs/07_WORKFLOW_ENGINE.md` |
| Redis keys & channels | `docs/08_REDIS_ARCHITECTURE.md` |
| AI Agents | `docs/09_AI_AGENTS.md` |
| Compilation pipeline | `docs/10_COMPILATION_PIPELINE.md` |
| Research Agent | `docs/11_RESEARCH_AGENT.md` |
| Migration Journal | `docs/12_MIGRATION_JOURNAL.md` |
| Backend | `docs/13_BACKEND.md` |
| Frontend | `docs/14_FRONTEND.md` |
| Docker setup | `docs/15_DOCKER_SETUP.md` |
| API endpoints | `docs/16_API_SPECIFICATION.md` |
| Reports | `docs/17_REPORT_GENERATOR.md` |
| Testing | `docs/20_TESTING.md` |
| Job lifecycle states | `docs/26_JOB_LIFECYCLE.md` |
| Scalability / worker | `docs/24_SCALABILITY.md` |
| Progress tracker | `docs/30_IMPLEMENTATION_TRACKER.md` |
| Demo script | `docs/31_DEMO_SCRIPT.md` |

**Governance files are in `.agent/`:**

| Purpose | File |
|---------|------|
| Implementation rules | `.agent/AGENT_RULES.md` |
| Build order | `.agent/IMPLEMENTATION_ORDER.md` |
| Coding prompts | `.agent/IMPLEMENTATION_PROMPTS.md` |
| Debug playbook | `.agent/DEBUGGING_PROMPTS.md` |
| Mock services guide | `.agent/MOCK_SERVICES.md` |
| Architecture freeze | `.agent/ARCHITECTURE_LOCK.md` |
| AI memory / progress | `.agent/SESSION_STATE.json` |

