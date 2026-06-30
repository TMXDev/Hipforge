# 09_AI_AGENTS.md

Version: 1.0

Status: Pending

---

# Purpose

This document defines every AI agent used by HIPForge.

Each agent has a single responsibility and communicates exclusively through the Workflow Engine and Redis.

Agents never communicate directly with one another.

---

# Goals

The AI system must:

- Be deterministic.
- Minimize token usage.
- Produce structured outputs.
- Never overwrite working code.
- Avoid repeated mistakes.
- Support automated execution.

---

# AI Architecture

HIPForge uses three specialized AI agents.

```
Analysis Agent

↓

Patch Agent

↓

Compiler

↓

Research Agent (only if necessary)
```

The compiler is the final authority.

If the compiler succeeds, the workflow ends.

---

# General Rules

Every AI agent must:

- Perform only its assigned responsibility.
- Return structured JSON.
- Never invent missing information.
- Use the Migration Journal as context.
- Respect compiler diagnostics.
- Preserve working code whenever possible.

Agents do not decide workflow execution.

Only the Workflow Engine controls execution.

---

# Analysis Agent

## Purpose

The Analysis Agent determines **why** compilation failed.

It does not modify code.

---

## Inputs

- Current HIP source code
- Compiler stdout
- Compiler stderr
- Current attempt number
- Migration Journal
- Previous research (if available)

---

## Responsibilities

The Analysis Agent must:

- Identify the root cause.
- Locate affected files.
- Locate affected line numbers.
- Determine whether the error is syntax, API, compiler, or architecture related.
- Produce a repair strategy.

---

## Output Format

```json
{
  "summary": "...",
  "root_cause": "...",
  "affected_files": [],
  "affected_lines": [],
  "confidence": 0.95,
  "repair_plan": [
    "...",
    "..."
  ]
}
```

---

## Restrictions

The Analysis Agent must NOT:

- Modify source code.
- Guess missing APIs.
- Ignore compiler diagnostics.
- Repeat previous failed strategies.

---

# Patch Agent

## Purpose

The Patch Agent applies targeted modifications based on the Analysis Agent's repair plan.

---

## Inputs

- Current HIP source
- Analysis JSON
- Migration Journal
- Previous patches

---

## Responsibilities

The Patch Agent must:

- Modify only affected code.
- Preserve formatting.
- Preserve unrelated logic.
- Generate minimal patches.
- Explain every modification.

---

## Output Format

```json
{
  "summary":"...",
  "modified_files":[
    "kernel.hip"
  ],
  "changes":[
    {
      "file":"kernel.hip",
      "reason":"Replace unsupported warpSize usage",
      "lines":[42,43]
    }
  ]
}
```

---

## Restrictions

The Patch Agent must NOT:

- Rewrite entire files unnecessarily.
- Remove working functionality.
- Introduce unrelated optimizations.
- Ignore the repair plan.

---

# Research Agent

## Purpose

The Research Agent provides external technical knowledge when deterministic repair attempts fail.

The Research Agent is only activated after a failed repair cycle.

---

## Inputs

- Latest compiler diagnostics
- Analysis output
- Previous patches
- Migration Journal

---

## Responsibilities

Search:

- Official ROCm documentation
- HIP documentation
- AMD examples
- GitHub issues
- ROCm migration guides

Then produce:

- Relevant findings
- Recommended strategy
- Supporting references

---

## Output Format

```json
{
  "summary":"...",
  "findings":[
    "...",
    "..."
  ],
  "recommended_actions":[
    "...",
    "..."
  ]
}
```

---

## Restrictions

The Research Agent must NOT:

- Generate source code.
- Apply patches.
- Ignore official documentation.
- Recommend duplicate solutions already recorded in the Migration Journal.

---

# Compiler Authority

The compiler is the final validator.

AI agents may believe a solution is correct.

Only the compiler determines success.

Compiler decisions always override AI output.

---

# Migration Journal Usage

Every AI agent receives the current Migration Journal.

Before producing output, each agent must review:

- Previous compiler failures
- Previous repair attempts
- Previous research
- Previous patches

The objective is to avoid repeating failed solutions.

---

# Failure Handling

If an AI provider returns:

- Invalid JSON
- Empty output
- Timeout
- API error

The Workflow Engine records the failure and retries according to the configured retry budget.

---

# Prompting Strategy

Every AI request consists of:

1. System Prompt
2. Current Task
3. Source Code
4. Compiler Diagnostics
5. Migration Journal
6. Expected JSON Schema

Responses outside the expected schema are considered invalid.

---

# Design Principles

Every AI agent should be:

- Predictable
- Focused
- Explainable
- Stateless
- Easy to test

---

# Responsibilities

Analysis Agent

- Explain problems

Patch Agent

- Modify code

Research Agent

- Gather external knowledge

Compiler

- Validate correctness

Workflow Engine

- Coordinate everything

---

# Non-Responsibilities

AI agents do NOT:

- Manage retries
- Execute shell commands
- Store files
- Update Redis directly
- Generate reports

---

# Dependencies

07_WORKFLOW_ENGINE.md

08_REDIS_ARCHITECTURE.md

12_MIGRATION_JOURNAL.md

---

# Used By

10_COMPILATION_PIPELINE.md

13_BACKEND.md

17_API_REFERENCE.md

---

# Acceptance Criteria

✓ Three specialized AI agents are defined.

✓ Inputs and outputs are standardized.

✓ JSON schemas are specified.

✓ Responsibilities are isolated.

✓ Compiler remains the source of truth.

✓ Migration Journal is integrated.

---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.