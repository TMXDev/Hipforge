# 04_TECHNOLOGY_DECISIONS.md

Version: 1.0

Status: Pending

---

# Purpose

This document records every major technology decision made during the design of HIPForge.

Each decision includes the selected technology, alternatives that were considered, and the reasoning behind the final choice.

The goal is to ensure future contributors understand not only **what** technologies were chosen, but **why** they were chosen.

---

# Goals

This document aims to:

- Document architectural decisions.
- Explain trade-offs.
- Prevent unnecessary technology changes.
- Provide consistency during development.
- Serve as a reference during future scaling.

---

# Scope

This document covers:

- Programming languages
- Frameworks
- AI infrastructure
- Workflow Engine
- State management
- Containerization
- Development philosophy

This document does NOT define implementation details.

---

# Decision Philosophy

Every technology used by HIPForge must satisfy the following principles:

- Production-ready
- Well documented
- Widely adopted
- Easy to maintain
- Compatible with future scaling
- Suitable for startup growth

Technologies are selected for reliability rather than popularity.

---

# Frontend

## Selected

Next.js (TypeScript)

### Why

- Excellent developer experience.
- Modern React framework.
- Strong ecosystem.
- Easy deployment.
- Built-in routing.
- Type safety through TypeScript.

### Alternatives Considered

React + Vite

Rejected because Next.js provides a more complete framework for future SaaS development.

Vue.js

Rejected because the team has stronger React experience.

---

# Backend

## Selected

FastAPI

### Why

- High performance.
- Native async support.
- Excellent API documentation.
- Strong Python ecosystem.
- Easy integration with AI libraries.

### Alternatives Considered

Flask

Rejected due to weaker async capabilities.

Django

Rejected because HIPForge does not require a full web framework.

---

# Programming Language

## Selected

Python

### Why

- Excellent AI ecosystem.
- Native support for subprocess execution.
- Mature tooling.
- Strong developer productivity.

---

# AI Provider

## Selected

Fireworks AI

### Why

- Official hackathon credits.
- High-quality hosted models.
- Simple API integration.
- Eliminates the need to self-host large language models.

### Future Consideration

Support multiple AI providers through a pluggable provider interface.

---

# AI Models

## Analysis Agent

Qwen

Reason:

Excellent reasoning capabilities.

Strong technical understanding.

---

## Patch Agent

Kimi K2.7 Code

Reason:

Optimized for code generation and editing.

---

## Research Agent

Purpose

The Research Agent is activated only after deterministic repair attempts fail.

Responsibilities

- Search official ROCm documentation.
- Search GitHub issues.
- Search AMD migration guides.
- Summarize research findings.
- Suggest new repair strategies.

The Research Agent minimizes repeated failures by introducing external technical knowledge into the workflow.

---

# Workflow Engine

## Selected

Custom Python State Machine

### Why

HIPForge follows a deterministic workflow.

A custom state machine provides:

- Full control over execution.
- Easier debugging.
- Framework independence.
- Simple testing.
- No external workflow_engine dependencies.

### Alternatives Considered

LangGraph

Advantages:

- Built-in agent workflow support.
- Graph visualization.
- Mature workflow_engine features.

Reasons Rejected:

- Adds unnecessary abstraction for V1.
- Additional dependency to maintain.
- Workflow is simple enough to implement ourselves.
- Less control over internal execution.
- Increases project complexity.

---

# Shared State

## Selected

Redis

### Why

Redis acts as the shared memory of HIPForge.

Responsibilities include:

- Migration status.
- Agent communication.
- Compiler logs.
- Retry tracking.
- Migration Journal.
- Progress streaming.

Redis is fast, lightweight, and widely adopted.

### Alternatives Considered

SQLite

Rejected because it is not optimized for real-time shared state.

PostgreSQL

Rejected because persistent relational storage is unnecessary for V1.

---

# Containerization

## Selected

Docker Compose

### Why

- One-command startup.
- Consistent environments.
- Easy local development.
- Simple hackathon deployment.

### Future Consideration

Migrate to Kubernetes for large-scale cloud deployments.

---

# Compiler

## Selected

hipify-clang

hipcc

### Why

These are the official ROCm migration and compilation tools provided by AMD.

The compiler serves as the source of truth for validating generated HIP code.

---

# API Framework

## Selected

REST API + WebSocket

### REST Responsibilities

- File uploads.
- Download reports.
- Migration control.
- Status queries.

### WebSocket Responsibilities

- Live logs.
- Progress updates.
- Agent activity.
- Compiler output.

---

# Workspace Strategy

## Selected

Local isolated workspaces

Each migration receives a dedicated workspace containing:

- Input files.
- Generated code.
- Logs.
- Reports.
- Patches.

This simplifies debugging and ensures migrations do not interfere with each other.

---

# Migration Journal

## Selected

Session-based Migration Journal

### Purpose

The Migration Journal records every migration attempt performed during a session.

Each entry contains:

- Attempt number
- Compiler errors
- Analysis summary
- Generated patch
- Search findings
- Final result

The journal allows future attempts to learn from previous failures while preventing duplicate fixes.

The journal exists only during the migration session.

It is included in the final migration report for transparency.
---

# Security Philosophy

HIPForge follows a "least privilege" philosophy.

The system should:

- Validate all uploaded files.
- Restrict workspace access.
- Prevent arbitrary command execution.
- Isolate compiler processes.
- Keep secrets in environment variables.

Detailed implementation is defined in `19_SECURITY.md`.

---

# Startup Considerations

HIPForge is designed as the foundation of a commercial product.

Architectural decisions prioritize:

- Maintainability.
- Scalability.
- Modularity.
- Low operational cost.

The V1 hackathon implementation intentionally excludes enterprise features such as authentication, billing, and multi-user collaboration.

---

# Future Technology Roadmap

Potential future additions include:

- PostgreSQL for user accounts.
- Object storage for project archives.
- Kubernetes deployment.
- Multiple AI providers.
- Team collaboration features.
- Authentication and authorization.
- Usage analytics.

These features are outside the scope of Version 1.

---

# Responsibilities

This document explains the reasoning behind every technology selection.

---

# Non-Responsibilities

This document does not describe implementation details or code structure.

---

# Dependencies

- 00_SYSTEM_SPECIFICATION.md
- 01_PRODUCT_VISION.md
- 02_SYSTEM_ARCHITECTURE.md
- 03_PROJECT_STRUCTURE.md

---

# Used By

All implementation documents and prompts.

---

# Acceptance Criteria

✓ Every major technology has been selected.

✓ Alternatives have been evaluated.

✓ Trade-offs are documented.

✓ Future scalability has been considered.

✓ Decisions align with HIPForge's long-term vision.

---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.