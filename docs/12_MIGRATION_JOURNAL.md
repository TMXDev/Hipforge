# 12_MIGRATION_JOURNAL.md

Version: 1.0

Status: Pending

---

# Purpose

The Migration Journal is the permanent record of everything that happens during a migration.

It records every important event, decision, compiler result, AI action, and research finding from the beginning of the migration until completion.

The journal acts as the memory of the migration and provides transparency, traceability, and reproducibility.

---

# Goals

The Migration Journal must:

- Record every important action.
- Prevent repeated failures.
- Explain AI decisions.
- Improve debugging.
- Support report generation.
- Preserve migration history.

---

# Scope

The Migration Journal records:

- Workflow states
- Compiler executions
- AI analyses
- Code patches
- Research findings
- Retry history
- Final outcome

It does NOT replace Redis or the Migration Workspace.

---

# Philosophy

The Migration Journal answers one question:

> "If another engineer opens this migration six months later, can they understand exactly what happened?"

If the answer is yes, the journal has done its job.

---

# Storage

The journal is stored in two forms.

## Runtime

During execution:

Redis List

```
migration:{id}:journal
```

---

## Permanent

After migration:

```
workspace/

reports/

migration_journal.json
```

The permanent journal is included in the export package.

---

# Journal Structure

Each migration attempt creates one journal entry.

Example

```json
{
  "attempt": 2,
  "timestamp": "2026-07-02T14:32:18Z",
  "workflow_state": "PATCH",
  "compiler_result": "FAILED",
  "analysis_summary": "...",
  "patch_summary": "...",
  "research_summary": "...",
  "files_modified": [
    "kernel.hip"
  ],
  "compiler_error_hash": "c19f98...",
  "prompt_versions": {
    "analysis": "analysis_v1",
    "patch": "patch_v1",
    "research": "research_v1"
  }
}
```

---

# Recorded Information

Each journal entry should include:

- Attempt number
- Timestamp
- Workflow state
- Compiler exit code
- Compiler error summary
- Error hash
- Analysis summary
- Patch summary
- Research summary
- Modified files
- AI confidence (if available)
- Prompt versions

---

# Error Hashing

Every compiler error generates a stable hash.

Example

```
SHA256(stderr)
```

The Workflow Engine uses this hash to detect duplicate failures.

If the same error hash appears repeatedly, the Workflow Engine can:

- Skip identical repair strategies.
- Trigger the Research Engine.
- Record duplicate attempts.

---

# Duplicate Prevention

Before launching the Patch Agent:

The Workflow Engine compares:

Current compiler error hash

↓

Previous journal entries

If a matching hash already exists:

- Do not repeat the same repair plan.
- Escalate to Research if appropriate.

---

# Prompt Version Tracking

Every AI response records the prompt version that generated it.

Example

```json
{
  "analysis": "analysis_v1",
  "patch": "patch_v1",
  "research": "research_v1"
}
```

This allows:

- Prompt improvements
- Regression analysis
- Debugging
- A/B testing

---

# AI Confidence

When available, AI agents may provide a confidence score.

Example

```
0.94
```

Confidence values are recorded for analysis only.

The compiler always determines correctness.

---

# Workflow Timeline

The journal also records workflow events.

Example

```
Workspace Created

↓

hipify Started

↓

hipify Completed

↓

Compilation Failed

↓

Analysis Started

↓

Patch Applied

↓

Compilation Failed

↓

Research Started

↓

Compilation Success

↓

Report Generated
```

---

# Report Integration

The Migration Report summarizes the journal.

The full journal remains available separately for advanced users.

---

# Export

The export package includes:

```
migration_report.md

migration_journal.json
```

This allows future review without requiring Redis.

---

# Responsibilities

The Migration Journal is responsible for:

- Recording history.
- Tracking retries.
- Preventing repeated failures.
- Supporting reports.
- Supporting debugging.

---

# Non-Responsibilities

The Migration Journal does NOT:

- Coordinate workflow.
- Store source files.
- Replace Redis.
- Execute AI.

---

# Dependencies

07_WORKFLOW_ENGINE.md

08_REDIS_ARCHITECTURE.md

09_AI_AGENTS.md

11_RESEARCH_AGENT.md

---

# Used By

13_BACKEND.md

17_REPORT_GENERATOR.md

20_TESTING.md

---

# Acceptance Criteria

✓ Every attempt creates a journal entry.

✓ Compiler errors are hashed.

✓ Prompt versions are recorded.

✓ Duplicate failures are detectable.

✓ Timeline is preserved.

✓ Journal is exported.

---

# Design Principles

The Migration Journal should be:

- Transparent
- Immutable
- Explainable
- Structured
- Easy to inspect

---

# Future Evolution

Future versions may support:

- Cross-project analytics.
- Organizational migration history.
- Prompt performance dashboards.
- Anonymous telemetry (optional).

These features extend the journal without changing its core structure.

---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.