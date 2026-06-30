# HIPForge — System Specification

Version: 1.0

Status: Pending

---

# 1. Purpose

This document defines the complete architecture, philosophy, goals, and technical vision of HIPForge.

It is the single source of truth for every architectural decision made throughout the project.

Every implementation document, AI prompt, and software component must comply with this specification.

If any future documentation contradicts this document, this document takes priority.

---

# 2. Project Overview

HIPForge is an autonomous AI-powered engineering platform that assists developers in migrating NVIDIA CUDA applications to the AMD ROCm ecosystem.

Unlike traditional code converters, HIPForge performs deterministic migration first, validates every change using the HIP compiler, and only invokes AI when compilation fails.

The compiler—not the AI—is the source of truth.

HIPForge behaves like a GPU migration engineer rather than a code generator.

---

# 3. Problem Statement

CUDA is the dominant GPU programming platform.

Many organizations have invested years into CUDA applications.

Migrating those projects to AMD ROCm is difficult because:

- Automatic conversion tools cannot fix every incompatibility.
- Compiler errors often require extensive manual debugging.
- Engineers spend hours reading documentation.
- Migration becomes expensive and slow.

HIPForge reduces this effort through an evidence-driven AI workflow.

---

# 4. Vision

HIPForge should become the easiest and most trustworthy way to migrate CUDA projects to AMD GPUs.

The system should feel less like an AI chatbot and more like an experienced GPU engineer working alongside the developer.

---

# 5. Design Philosophy

HIPForge follows several core principles.

## 5.1 Compiler First

The compiler is always correct.

AI suggestions are never assumed to be correct until verified by compilation.

---

## 5.2 Local First

Compilation, translation, and workspace management happen locally.

AI is only used when deterministic tooling fails.

---

## 5.3 Explainability

Every modification made by AI must be explainable.

Users should understand:

- what changed
- why it changed
- where it changed
- which documentation supports the change

---

## 5.4 Small Specialized Components

Every component has one responsibility.

Example:

Analysis Agent
→ Finds problems.

Patch Agent
→ Writes fixes.

Research Agent
→ Finds external knowledge.

Workflow Engine
→ Validates fixes.

No component should perform multiple unrelated responsibilities.

---

## 5.5 Evidence-Based AI

AI decisions must always be grounded in:

- compiler diagnostics
- previous attempts
- workspace context
- official documentation

The system must avoid speculative code generation.

---

## 5.6 Deterministic Before Intelligent

Always attempt deterministic solutions before invoking AI.

Examples:

✓ hipify

✓ compiler

✓ syntax validation

before

AI

---

# 6. High-Level Workflow

Upload CUDA Project

↓

hipify-clang

↓

Compile using hipcc

↓

Compilation Successful?

├── YES

│ ↓

│ Generate Report

│ ↓

│ Download Results

│

└── NO

↓

Analysis Agent

↓

Patch Agent

↓

Compile Again

↓

Successful?

├── YES

│ ↓

│ Report

│

└── NO

↓

Research Agent

↓

Update Migration Journal

↓

Retry

---

# 7. Major Components

The system consists of the following subsystems.

Frontend

Backend

Workspace

Redis

Workflow Engine

AI Agent System

Compiler Pipeline

Report Generator

Security Layer

Testing Layer

Deployment Layer

Each subsystem has its own dedicated documentation.

---

# 8. Technology Stack

Frontend

Next.js

Backend

FastAPI

Programming Language

Python

State Storage

Redis

Containerization

Docker Compose

AI Provider

Fireworks AI

Compiler

HIPCC

Translator

hipify-clang

Version Control

Git

---

# 9. Project Goals

Primary goals

- Reduce CUDA migration effort.

- Keep AI costs low.

- Minimize hallucinations.

- Produce compilable HIP code.

- Explain every migration.

Secondary goals

- Professional UI.

- Easy local deployment.

- Modular architecture.

- Future extensibility.

---

# 10. Non Goals

HIPForge is NOT intended to:

- replace GPU engineers

- optimize GPU kernels automatically

- guarantee perfect migration

- become a general AI coding assistant

The system focuses specifically on CUDA → ROCm migration.

---

# 11. Guiding Rules

The following rules are mandatory.

Rule 1

The compiler is the source of truth.

Rule 2

AI is only invoked after deterministic tools fail.

Rule 3

Every AI decision must be explainable.

Rule 4

Redis is the single shared memory.

Rule 5

The Workflow Engine controls workflow.

Rule 6

Workspace files are the canonical source for code.

Rule 7

Every retry must learn from previous attempts.

Rule 8

Every component owns one responsibility.

Rule 9

The system must remain Docker-first.

Rule 10

Security is mandatory, not optional.

---

# 12. Documentation Structure

All project documentation is located inside /docs.

Each document owns exactly one subject.

No duplication should exist between documents.

---

# 13. Success Criteria

HIPForge is considered successful if it can:

- accept CUDA source code

- perform deterministic translation

- compile HIP code

- invoke AI only when needed

- retry intelligently

- generate a migration report

- package the final project

- run locally with one Docker command

---

# 14. Future Vision

Future versions may support:

- Multi-file projects

- Batch migration

- Performance optimization

- Automatic benchmarking

- Cloud execution

- Additional programming models

These features are intentionally outside Version 1.

---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.

---

END OF DOCUMENT