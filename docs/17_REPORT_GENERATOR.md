# 17_REPORT_GENERATOR.md

Version: 1.0

Status: Pending

---

# Purpose

This document defines the architecture and responsibilities of the HIPForge Report Generator. The Report Generator is responsible for compiling all relevant information from a completed or failed migration into a human-readable summary. This includes details from the Migration Journal, compiler outputs, AI agent analyses, and overall migration statistics. The generated report serves as a comprehensive record for the user, providing transparency and aiding in debugging.

---

# Goals

The Report Generator must:

- Provide a clear and concise summary of the migration.
- Include all critical information for debugging and understanding.
- Be easily readable by developers.
- Support multiple output formats (Markdown in V1, PDF in future).
- Be generated automatically upon migration completion or failure.
- Ensure data integrity and accuracy.

---

# Scope

This document covers:

- The types of information included in the report.
- The structure and sections of the report.
- Data sources for report generation.
- Output formats and their characteristics.
- Integration points with the Workflow Engine.

This document does NOT define:

- Specific UI/UX for viewing reports (covered in `14_FRONTEND.md`).
- Database schemas.
- AI prompt engineering for report content (AI agents provide summaries).
- Long-term storage solutions for reports (covered in `06_WORKSPACE_ARCHITECTURE.md`).

---

# Report Philosophy

The migration report is the definitive summary of the HIPForge process. It should answer the question: "What happened during this migration, and why?" It prioritizes clarity, completeness, and actionable insights, enabling users to quickly grasp the outcome and any issues encountered.

---

# Report Contents

The generated report will include the following sections:

## 1. Migration Summary

- **Migration ID**: Unique identifier for the migration session.
- **Status**: `SUCCESS`, `FAILED`, `CANCELLED`.
- **Start Time**: Timestamp of when the migration began.
- **End Time**: Timestamp of when the migration completed or failed.
- **Duration**: Total time taken for the migration.
- **Input Method**: How the project was provided (e.g., `paste`, `single_file`, `zip_archive`).
- **Target GPU Architecture**: The AMD GPU architecture targeted for migration.
- **Retry Budget**: Configured maximum number of AI repair attempts.
- **Actual Retries**: Number of AI repair attempts made.
- **Migration Mode**: `Strict`, `Balanced`, `Experimental`.

## 2. Input Project Details

- **Original Files**: List of original CUDA files uploaded.
- **File Hashes**: Hashes of original files to ensure integrity.

## 3. Translation Summary

- **`hipify-clang` Status**: Success or failure of the initial translation.
- **Semantic Compatibility Analysis (SCA) Findings**: Summary of `migration_risks.json`.
  - List of detected CUDA constructs with potential behavioral differences.

## 4. Compilation History

- **Attempt-by-Attempt Breakdown**: For each compilation attempt:
  - Attempt number.
  - Compiler command executed.
  - Exit code.
  - Summary of `stdout` and `stderr` (truncated for brevity).
  - Link to full compiler log file.

## 5. AI Agent Activity

- **Analysis Agent Summaries**: For each analysis:
  - Root cause identified.
  - Affected files and lines.
  - Repair plan proposed.
  - AI confidence score.
- **Patch Agent Summaries**: For each patch application:
  - Summary of changes made.
  - List of modified files.
  - Reason for the patch.
- **Research Agent Summaries**: For each research phase:
  - Problem identified.
  - Search queries used.
  - Key findings and sources.
  - Recommended actions.

## 6. Migration Journal Excerpt

- A condensed view of the `migration_journal.json`, highlighting key events and decisions.
- Reference to the full `migration_journal.json` file.

## 7. Generated Artifacts

- List of all files included in the final downloadable package, with their paths within the package.
  - `converted_project/`
  - `migration_report.md`
  - `migration_journal.json`
  - `compatibility_report.md`
  - `migration_risks.json`
  - `build.sh`
  - `CMakeLists.txt`
  - `git_patch.diff`
  - `README.md`
  - `logs/`

## 8. Performance Profiling (if enabled)

- Summary of `rocprof` output, including key performance metrics and bottlenecks.

---

# Data Sources

The Report Generator pulls information from:

- **Workflow Context**: Runtime parameters and metadata.
- **Migration Journal**: Comprehensive history of attempts, AI actions, and compiler results.
- **Workspace Files**: Directly reads `migration_risks.json`, compiler logs, patch files, and generated source code.
- **Redis**: Current status and real-time data (though most historical data is in the Journal).

---

# Output Formats

## Version 1: Markdown (`.md`)

- The primary output format for the report will be Markdown, stored as `migration_report.md` within the workspace.
- Markdown allows for easy readability, version control, and conversion to other formats.

## Future Versions: PDF (`.pdf`)

- Future iterations may support PDF generation for more formal, immutable reports.

---

# Integration with Workflow Engine

The Report Generator is invoked by the Workflow Engine as the final step of a migration, regardless of success or failure. It receives the complete Workflow Context and accesses the workspace to gather all necessary data.

---

# Dependencies

- `05_USER_FLOW.md`
- `06_WORKSPACE_ARCHITECTURE.md`
- `07_WORKFLOW_ENGINE.md`
- `09_AI_AGENTS.md`
- `10_COMPILATION_PIPELINE.md`
- `12_MIGRATION_JOURNAL.md`

---

# Used By

- `13_BACKEND.md`
- `14_FRONTEND.md`
- `18_OBSERVABILITY.md`
- `20_TESTING.md`

---

# Acceptance Criteria

✓ Report accurately reflects the entire migration process.
✓ All critical events and decisions are summarized.
✓ Report is generated in Markdown format.
✓ Information from AI agents and compiler is included.
✓ Report is clear, concise, and easy to understand.

---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.