# 11_RESEARCH_AGENT.md

Version: 1.0

Status: Pending

---

# Purpose

This document defines the behavior of the HIPForge Research Engine.

The Research Engine provides external technical knowledge when deterministic repair attempts are no longer sufficient.

Rather than generating code, it gathers reliable information that helps the Patch Agent produce better fixes.

---

# Goals

The Research Engine must:

- Improve repair quality.
- Avoid repeated failures.
- Reduce unnecessary retries.
- Prefer official AMD documentation.
- Produce structured research summaries.
- Keep AI context focused.

---

# Scope

This document defines:

- Research workflow
- Information sources
- Search strategy
- Output format
- Quality rules

It does NOT define:

- AI prompts
- Compiler behavior
- Redis schema

---

# Research Philosophy

The Research Engine behaves like a senior GPU engineer performing technical investigation.

Its role is not to solve the problem directly.

Its role is to collect trustworthy evidence that enables better decisions.

---

# Activation Rules

The Research Engine is activated when:

- A repair attempt fails.
- Duplicate compiler errors are detected.
- The Workflow Engine identifies architecture-specific problems.
- Unsupported CUDA features are encountered.

The Workflow Engine decides when research begins.

---

# Research Sources

Research should prioritize sources in the following order.

Priority 1

Official AMD Documentation

Examples

- ROCm Documentation
- HIP Documentation
- AMD GPU Programming Guides

Priority 2

Official AMD GitHub repositories

Priority 3

Official migration examples

Priority 4

High-quality GitHub Issues

Priority 5

Trusted community resources

Lower-priority sources should only be used when official documentation provides no answer.

---

# Research Process

The Research Engine performs the following steps.

1. Read compiler diagnostics.

2. Read the latest Analysis output.

3. Read the Migration Journal.

4. Identify the technical problem.

5. Generate focused search queries.

6. Retrieve relevant information.

7. Filter duplicate findings.

8. Produce a structured research summary.

---

# Search Strategy

Search queries should include:

- CUDA API names
- HIP equivalents
- Compiler error messages
- ROCm version
- GPU architecture (if provided)

Example

Instead of searching:

```
warpSize
```

Search:

```
HIP warpSize ROCm wavefrontSize migration
```

Focused queries improve result quality.

---

# Research Output

The Research Engine returns structured JSON.

```json
{
  "summary":"...",
  "problem":"...",
  "sources":[
    "...",
    "..."
  ],
  "findings":[
    "...",
    "..."
  ],
  "recommended_actions":[
    "...",
    "..."
  ],
  "confidence":0.92
}
```

---

# Duplicate Prevention

Before returning results, the Research Engine compares new findings against the Migration Journal.

Previously attempted solutions should not be recommended again unless new supporting evidence is discovered.

---

# Evidence Quality

The Research Engine should prefer:

- Official documentation
- API references
- Verified migration examples

It should avoid:

- Speculation
- Unverified forum posts
- Outdated documentation
- Conflicting advice

---

# Integration

The Research Engine does not modify source code.

Its output becomes additional context for:

- Analysis Agent
- Patch Agent

The Workflow Engine remains responsible for coordinating execution.

---

# Failure Handling

If research cannot be completed:

- Record the failure.
- Continue according to the Workflow Engine.
- Preserve all logs.

Research failure must never corrupt the migration process.

---

# Design Principles

The Research Engine must be:

- Evidence-driven
- Deterministic
- Explainable
- Focused
- Reproducible

---

# Responsibilities

The Research Engine is responsible for:

- Technical investigation
- Evidence collection
- Source prioritization
- Recommendation generation

---

# Non-Responsibilities

The Research Engine does NOT:

- Patch code
- Compile code
- Modify Redis directly
- Control workflow execution

---

# Dependencies

07_WORKFLOW_ENGINE.md

09_AI_AGENTS.md

10_COMPILATION_PIPELINE.md

---

# Used By

12_MIGRATION_JOURNAL.md

13_BACKEND.md

17_REPORT_GENERATOR.md

---

# Acceptance Criteria

✓ Activation rules are defined.

✓ Search sources are prioritized.

✓ Structured JSON output is specified.

✓ Duplicate recommendations are prevented.

✓ Official AMD documentation is prioritized.

✓ Research integrates with the Workflow Engine.

---

# Startup Notes

Future versions may include:

- Local documentation indexing.
- Cached research results.
- Organization-specific knowledge bases.
- Offline search capabilities.

These enhancements should extend the Research Engine without changing its core responsibilities.

---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.