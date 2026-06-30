# ARCHITECTURE_LOCK.md

---

**Status: LOCKED**

---

The HIPForge architecture is frozen as of **2026-06-30**.

All numbered specification documents (`00` through `28`) represent the final, authoritative design of the system. No subsystem redesigns may occur during the implementation phase.

---

## Permitted Changes During Implementation

The following narrow categories of changes are allowed:

- **Bug fixes** — Correcting implementation errors that contradict the existing spec.
- **Documentation corrections** — Fixing typos, broken links, or outdated cross-references.
- **Security fixes** — Addressing security vulnerabilities discovered during implementation or testing.
- **Performance optimizations** — Tuning that does not alter the architecture or system contracts.

---

## Prohibited Changes During Implementation

The following are **not permitted** without a formal architecture review:

- Replacing any named subsystem (Workflow Engine, Migration Worker, Migration Journal, etc.)
- Changing the Redis key schema defined in `08_REDIS_ARCHITECTURE.md`
- Adding or removing job lifecycle states defined in `26_JOB_LIFECYCLE.md`
- Introducing new third-party frameworks not listed in `04_TECHNOLOGY_DECISIONS.md`
- Restructuring the workspace layout defined in `06_WORKSPACE_ARCHITECTURE.md`
- Redesigning API contracts in `16_API_SPECIFICATION.md`

---

## Frozen Subsystems

| Subsystem                    | Spec Document                 |
| ---------------------------- | ----------------------------- |
| Workflow Engine              | `07_WORKFLOW_ENGINE.md`       |
| Migration Worker             | `24_SCALABILITY.md`           |
| Redis Architecture           | `08_REDIS_ARCHITECTURE.md`    |
| Migration Journal            | `12_MIGRATION_JOURNAL.md`     |
| Semantic Compatibility Analyzer | `10_COMPILATION_PIPELINE.md` |
| Analysis, Patch & Research Agents | `09_AI_AGENTS.md`        |
| Docker Architecture          | `15_DOCKER_SETUP.md`          |
| Job Lifecycle States         | `26_JOB_LIFECYCLE.md`         |
| Workspace Layout             | `06_WORKSPACE_ARCHITECTURE.md` |
| Report Generator             | `17_REPORT_GENERATOR.md`      |
| Scalability Model            | `24_SCALABILITY.md`           |

---

## Implementation Directive

> Begin building. Every hour spent coding from this point is likely to add more value than another hour refining the design.

Refer to `30_IMPLEMENTATION_TRACKER.md` for task tracking and `31_DEMO_SCRIPT.md` for the demo presentation order.
